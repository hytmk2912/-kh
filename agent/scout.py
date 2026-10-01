"""Find paid work on the internet (read-only public job boards, no accounts),
classify it, filter out illegal/abusive gigs, rank it by learned profit, and
draft proposals for the best leads.

Job-board text is UNTRUSTED: it is only parsed and passed to the LLM as
quoted data, never executed, and it can never pick a payment destination.
Submitting a proposal needs a platform account, so drafts go to
output/proposals/ for the owner to send (the agent does not sign up anywhere).
"""
import html
import logging
import re
import time

from control import guard, network
from control.paths import OUTPUT_DIR
from agent import llm, skills, soul
from agent.memory import Memory, score

log = logging.getLogger("sovereign")

# Work the agent can actually deliver with free LLMs.
CATEGORY_RULES = (
    ("proofread", re.compile(r"proofread|copy ?edit|grammar", re.I)),
    ("translate", re.compile(r"translat|localiz|subtitl|interpret", re.I)),
    ("write", re.compile(r"writ|article|blog|content|copy|seo|description|newsletter|ghostwrit", re.I)),
)
# Legal-only filter: academic cheating, fake reviews, spam, adult, gambling,
# account/identity abuse, regulated advice.
BLOCK = re.compile(
    r"essay|homework|assignment|thesis|dissertation|exam|coursework|"
    r"fake review|write reviews?|review(s)? for (amazon|google|trustpilot)|5[- ]star|"
    r"spam|mass (email|dm|message)|cold email list|backlink farm|"
    r"adult|nsfw|porn|onlyfans|escort|casino|gambl|betting|"
    r"captcha|create accounts?|phone verif|kyc|identity|"
    r"crypto (pump|signal)|airdrop|pump and dump|"
    r"medical advice|legal advice|"
    r"plagiari|rewrite to avoid detection|ai detect",
    re.I,
)


# Legal but not deliverable by an AI writer/translator.
UNFIT = re.compile(
    r"certified|sworn|notari|apostille|photograph|videograph|video edit|on-?site|in[- ]person|"
    r"phone call|voice ?over|investigat|coordinator|manager|mentor|tutor|data entry|social media manag|"
    r"pdf to word|typing|transcri|design",
    re.I,
)


def classify(title: str, tags: str = "", text: str = "") -> str | None:
    """Category from the title first, then the board's own tags. The full text
    is only used for the legality filter (descriptions mention 'writing' too often)."""
    if BLOCK.search(f"{title} {tags} {text}") or UNFIT.search(title):
        return None
    for field in (title, tags):
        for name, rx in CATEGORY_RULES:
            if rx.search(field):
                return name
    return None


def _clean(text: str, n: int = 1500) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()[:n]


def fetch_freelancer(query: str, limit: int) -> list:
    data = network.get_json(
        "https://www.freelancer.com/api/projects/0.1/projects/active/",
        {"query": query, "limit": limit, "full_description": "true", "job_details": "true",
         "sort_field": "time_updated"},
    )
    out = []
    for p in data.get("result", {}).get("projects", []):
        cur = p.get("currency") or {}
        rate = float(cur.get("exchange_rate") or 0)
        b = p.get("budget") or {}
        lo, hi = float(b.get("minimum") or 0), float(b.get("maximum") or b.get("minimum") or 0)
        budget = (lo + hi) / 2 * rate if rate else None
        if p.get("type") == "hourly" and budget:
            budget *= 3  # assume ~3 paid hours for an hourly gig
        jobs = " ".join(j.get("name", "") for j in p.get("jobs") or [])
        out.append({
            "id": f"freelancer:{p['id']}", "source": "freelancer",
            "title": p.get("title", ""), "url": f"https://www.freelancer.com/projects/{p.get('seo_url', p['id'])}",
            "tags": jobs,
            "text": _clean(f"{p.get('title', '')}. {jobs}. {p.get('description') or p.get('preview_description') or ''}"),
            "budget_usd": round(budget, 2) if budget else None,
            "competition": (p.get("bid_stats") or {}).get("bid_count") or 0,
            "posted_ts": p.get("time_submitted") or p.get("time_updated"),
            "language": p.get("language"),
        })
    return out


def fetch_remotive(query: str, limit: int) -> list:
    data = network.get_json("https://remotive.com/api/remote-jobs", {"search": query, "limit": limit})
    out = []
    for j in data.get("jobs", []):
        if j.get("job_type") not in ("contract", "freelance"):
            continue  # full-time employment needs a human employee
        try:
            posted = int(time.mktime(time.strptime(j["publication_date"][:19], "%Y-%m-%dT%H:%M:%S")))
        except (KeyError, ValueError):
            posted = None
        out.append({
            "id": f"remotive:{j['id']}", "source": "remotive", "title": j.get("title", ""), "url": j.get("url", ""),
            "tags": " ".join(j.get("tags") or []),
            "text": _clean(f"{j.get('title', '')}. {j.get('category', '')}. {j.get('description', '')}"),
            "budget_usd": None, "competition": 0, "posted_ts": posted, "language": "en",
        })
    return out


FETCHERS = {"freelancer": fetch_freelancer, "remotive": fetch_remotive}


def collect(cfg: dict) -> list:
    sc = cfg["scout"]
    leads, seen = [], set()
    for source in sc["sources"]:
        for q in sc["queries"]:
            try:
                batch = FETCHERS[source](q, sc["max_leads_per_source"])
            except Exception as exc:
                log.warning("scout %s/%r failed: %s", source, q, exc)
                continue
            for lead in batch:
                if lead["id"] not in seen:
                    seen.add(lead["id"])
                    leads.append(lead)
    return leads


def draft_proposal(cfg: dict, lead: dict, why: str, offline: bool) -> str:
    prompt = skills.render(skills.load("proposal"), title=lead["title"], category=lead["category"],
                           budget=f"${lead['budget_usd']:.0f}" if lead.get("budget_usd") else "not stated",
                           post=lead["text"])
    text, provider, model = llm.generate(cfg, prompt, "light", 600, offline_only=offline)
    body = (f"# {lead['title']}\n\n- Link: {lead['url']}\n- Category: {lead['category']}\n"
            f"- Budget (USD est.): {lead.get('budget_usd')}\n- Bids so far: {lead.get('competition')}\n"
            f"- Score: {why}\n- Drafted by: {provider}/{model}\n\n"
            f"> Owner: review, then submit from your own account. Record the result with\n"
            f"> `python3 main.py outcome --lead {lead['id']} --won --revenue-usd N --hours H` (or `--lost`).\n\n"
            f"---\n\n{text}\n")
    path = OUTPUT_DIR / "proposals" / f"{lead['id'].replace(':', '_')}.md"
    guard.write_text(path, body)
    return str(path)


def run(cfg: dict, memory: Memory | None = None, offline: bool = False, leads: list | None = None) -> dict:
    memory = memory or Memory()
    stats = memory.stats()
    max_age = cfg["scout"]["max_age_hours"] * 3600
    fresh, skipped = [], {"known": 0, "blocked_or_unfit": 0, "old": 0, "avoid": 0}
    for lead in (leads if leads is not None else collect(cfg)):
        if memory.known(lead["id"]):
            skipped["known"] += 1
            continue
        lead["category"] = classify(lead["title"], lead.get("tags", ""), lead["text"]) or "skip"
        if lead["category"] == "skip":
            memory.add_lead(lead, -1, status="skipped")
            skipped["blocked_or_unfit"] += 1
            continue
        if lead.get("posted_ts") and time.time() - lead["posted_ts"] > max_age:
            memory.add_lead(lead, -1, status="skipped")
            skipped["old"] += 1
            continue
        value, why = score(lead, stats)
        if value < 0:
            memory.add_lead(lead, value, status="avoided")
            skipped["avoid"] += 1
            continue
        memory.add_lead(lead, value)
        fresh.append((value, why, lead))

    fresh.sort(key=lambda t: t[0], reverse=True)
    drafted = []
    for value, why, lead in fresh[: cfg["scout"]["draft_top"]]:
        try:
            path = draft_proposal(cfg, lead, why, offline)
        except Exception as exc:
            log.warning("draft for %s failed: %s", lead["id"], exc)
            continue
        memory.set_lead(lead["id"], status="proposed", proposal_path=path)
        drafted.append({"id": lead["id"], "score": value, "why": why, "title": lead["title"][:80], "proposal": path})
    summary = {"new_leads": len(fresh), "skipped": skipped, "drafted": drafted}
    soul.log("SCOUT", new=len(fresh), drafted=len(drafted), skipped=skipped,
             best=(drafted[0]["id"] + f" ${drafted[0]['score']}/h") if drafted else "-")
    return summary
