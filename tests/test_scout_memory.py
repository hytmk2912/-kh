import time

import pytest

from agent import scout
from agent.memory import Memory, score


@pytest.fixture
def mem():
    from control.paths import STATE_DIR
    p = STATE_DIR / "test" / "memory.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.unlink(missing_ok=True)
    return Memory(p)


@pytest.mark.parametrize("title,tags,text,cat", [
    ("Translate product page EN to VI", "", "", "translate"),
    ("Proofread my novel", "", "", "proofread"),
    ("Blog articles about travel", "", "", "write"),
    ("Logo needed", "Article Writing", "", "write"),
    ("Write my college essay", "", "", None),                  # academic cheating
    ("Write 50 Amazon reviews", "", "5-star reviews", None),   # fake reviews
    ("Casino blog posts", "", "", None),
    ("Certified legal translation", "", "", None),             # not deliverable
    ("Build a React app", "Javascript", "", None),
    ("Archival Research in Berlin", "Research Writing", "", None),
    ("Fourth Circuit Admission Counsel Needed", "Legal Writing", "", None),
    ("Freelance Software Sales Partner for SMEs", "Copywriting", "", None),
])
def test_classify(title, tags, text, cat):
    assert scout.classify(title, tags, text) == cat


def lead(i, budget, bids=0, cat_title="Translate a short text", source="freelancer"):
    return {"id": f"{source}:{i}", "source": source, "title": cat_title, "tags": "", "url": f"https://x/{i}",
            "text": cat_title, "budget_usd": budget, "competition": bids, "posted_ts": int(time.time())}


def test_ranking_prefers_profitable_low_competition(mem):
    stats = mem.stats()
    a, _ = score(dict(lead(1, 100, bids=0), category="translate"), stats)
    b, _ = score(dict(lead(2, 100, bids=60), category="translate"), stats)
    c, _ = score(dict(lead(3, 20, bids=0), category="translate"), stats)
    assert a > b and a > c


def test_memory_learns_and_avoids(mem):
    for i in range(6):
        mem.record_outcome(f"w{i}", "write", "freelancer", "lost")
    for i in range(3):
        mem.record_outcome(f"t{i}", "translate", "freelancer", "won", revenue_usd=80, hours=2)
    st = mem.stats()
    assert st[("write", "freelancer")]["avoid"] is True
    assert st[("translate", "freelancer")]["avoid"] is False
    assert st[("translate", "freelancer")]["profit_per_hour"] == 40
    assert st[("translate", "freelancer")]["win_rate"] > 0.15
    s_avoid, why = score(dict(lead(9, 500, cat_title="Blog post"), category="write"), st)
    assert s_avoid < 0 and "avoid" in why


def test_scout_run_offline(cfg, mem, journal, monkeypatch):
    leads = [lead(1, 100), lead(2, 300, bids=40), lead(3, 50, cat_title="Write my thesis"),
             dict(lead(4, 100), posted_ts=int(time.time()) - 10 * 86400)]
    cfg = dict(cfg, scout=dict(cfg["scout"], draft_top=1))
    out = scout.run(cfg, memory=mem, offline=True, leads=leads)
    assert out["new_leads"] == 2 and out["skipped"]["blocked_or_unfit"] == 1 and out["skipped"]["old"] == 1
    assert len(out["drafted"]) == 1 and mem.lead(out["drafted"][0]["id"])["status"] == "proposed"
    again = scout.run(cfg, memory=mem, offline=True, leads=leads)
    assert again["new_leads"] == 0 and again["skipped"]["known"] == 4
    assert journal[-1][0] == "SCOUT"


def test_proposal_prompt_marks_post_untrusted():
    from agent import skills
    assert "untrusted" in skills.load("proposal")
