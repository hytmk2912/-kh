"""Main agent loop for one job."""
import json
import logging
from dataclasses import dataclass, field

from control import guard, integrity, kill_switch, spend_limit, whitelist
from control.paths import OUTPUT_DIR
from agent import llm, skills, soul
from agent.config import eth_to_wei, wei_to_eth
from agent.ledger import Ledger
from agent.states import policy_for, state_for_balance

log = logging.getLogger("sovereign")

SKILL_FOR_TYPE = {"write": "write_content", "translate": "translate", "proofread": "proofread"}


@dataclass
class JobResult:
    job_id: str
    status: str  # done | refused | halted
    state: str
    reason: str = ""
    price_wei: int = 0
    paid_wei: int = 0
    cost_wei: int = 0
    provider: str = ""
    model: str = ""
    output_path: str = ""
    extra: dict = field(default_factory=dict)


def quote(job: dict, cfg: dict) -> int:
    chars = len(job.get("source_text", "")) + len(job.get("brief", ""))
    p = cfg["pricing"]
    return max(eth_to_wei(p["min_price_eth"]), eth_to_wei(p["price_per_1k_chars_eth"]) * chars // 1000)


def build_prompt(job: dict) -> str:
    template = skills.load(SKILL_FOR_TYPE[job["type"]])
    learned = f"learned_{job['type']}_{job['industry']}"
    notes = skills.load(learned) if skills.exists(learned) else "(none yet)"
    return skills.render(
        template,
        industry=job["industry"],
        target_lang=job.get("target_lang", "vi"),
        brief=job.get("brief", ""),
        source_text=job.get("source_text", ""),
        learned_notes=notes,
    )


def maybe_learn_skill(job: dict) -> str:
    """Normal state only: record a NEW skill note for this (type, industry) pair."""
    name = f"learned_{job['type']}_{job['industry']}"
    if skills.exists(name):
        return ""
    content = (
        f"# Learned notes: {job['type']} / {job['industry']}\n\n"
        f"- Created by agent after job `{job['id']}`.\n"
        f"- Keep terminology consistent for the {job['industry']} domain.\n"
        f"- Target language seen: {job.get('target_lang', 'vi')}.\n"
    )
    skills.create(name, content)
    return name


def refuse(job_id, state, reason, **kw) -> JobResult:
    soul.log("REFUSED", job=job_id, state=state, reason=reason)
    log.warning("job %s refused in %s: %s", job_id, state, reason)
    return JobResult(job_id=job_id, status="refused", state=state, reason=reason, **kw)


def run_job(job: dict, cfg: dict, wallet, ledger: Ledger | None = None, offline: bool = False) -> JobResult:
    ledger = ledger or Ledger.for_wallet(wallet)
    job_id = job.get("id", "job")

    # Layer 0: control integrity + kill switch.
    integrity.verify()
    try:
        kill_switch.check()
    except kill_switch.KillSwitchEngaged as exc:
        soul.log("HALTED", job=job_id, reason="kill switch")
        return JobResult(job_id=job_id, status="halted", state="-", reason=str(exc))

    balance = wallet.balance()
    state = state_for_balance(balance, cfg)
    policy = policy_for(state, cfg)
    log.info("job %s | balance=%s ETH | state=%s", job_id, wei_to_eth(balance), state)

    if not policy.accept_jobs:
        soul.log("NO_WORK", job=job_id, state=state, balance_eth=wei_to_eth(balance))
        return JobResult(job_id=job_id, status="refused", state=state, reason=f"{state}: policy accepts no jobs")
    if policy.zero_cost_only and policy.compute_cost_wei:
        raise RuntimeError("zero_cost_only policy with non-zero compute cost")  # config error, never spend

    try:
        whitelist.check(job.get("type", ""), job.get("industry", ""))
    except whitelist.NotWhitelisted as exc:
        return refuse(job_id, state, str(exc))

    price = quote(job, cfg)
    paid = 0
    if job.get("payment_tx"):
        try:
            paid = wallet.verify_payment(job["payment_tx"], price)
            ledger.record("income", paid, f"job {job_id} tx {job['payment_tx']}")
        except Exception as exc:
            return refuse(job_id, state, f"payment invalid: {exc}", price_wei=price)
    if policy.require_prepayment and not paid:
        return refuse(job_id, state, f"{state}: prepayment of {wei_to_eth(price)} ETH required", price_wei=price)

    cost = policy.compute_cost_wei
    try:
        spend_limit.check(ledger.spent_today(), cost)
    except spend_limit.SpendLimitExceeded as exc:
        return refuse(job_id, state, str(exc), price_wei=price)

    text, provider, model = llm.generate(cfg, build_prompt(job), policy.model_tier, policy.max_output_tokens, offline_only=offline)
    wallet.debit(cost, f"compute {job_id}")
    ledger.record("spend", cost, f"compute {job_id} {provider}/{model}")

    out = guard.write_text(OUTPUT_DIR / f"{job_id}.md", text)
    if not paid:
        invoice = {"job": job_id, "pay_to": wallet.address, "amount_wei": price,
                   "amount_eth": wei_to_eth(price), "chain": cfg["chain"]["name"], "chain_id": cfg["chain"]["chain_id"]}
        guard.write_text(OUTPUT_DIR / f"{job_id}.invoice.json", json.dumps(invoice, indent=2))

    learned = maybe_learn_skill(job) if policy.may_write_skills else ""
    after = wallet.balance()
    soul.log(
        "JOB_DONE", job=job_id, type=job["type"], industry=job["industry"], state=state,
        model=f"{provider}/{model}", price_eth=wei_to_eth(price), paid_eth=wei_to_eth(paid),
        cost_eth=wei_to_eth(cost), balance_eth=f"{wei_to_eth(balance)}->{wei_to_eth(after)}",
        new_state=state_for_balance(after, cfg), learned_skill=learned or "-",
    )
    return JobResult(job_id=job_id, status="done", state=state, price_wei=price, paid_wei=paid, cost_wei=cost,
                     provider=provider, model=model, output_path=str(out), extra={"learned_skill": learned})
