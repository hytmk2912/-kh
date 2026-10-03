"""Survival states derived from wallet balance."""
from dataclasses import dataclass

from agent.config import eth_to_wei

NORMAL, LOW, CRITICAL, DEAD = "Normal", "Low_compute", "Critical", "Dead"
ORDER = (NORMAL, LOW, CRITICAL, DEAD)


@dataclass(frozen=True)
class Policy:
    state: str
    model_tier: str
    max_output_tokens: int
    accept_jobs: bool
    require_prepayment: bool
    may_write_skills: bool
    compute_cost_wei: int
    zero_cost_only: bool = False


def state_for_balance(balance_wei: int, cfg: dict) -> str:
    t = cfg["thresholds_eth"]
    if balance_wei >= eth_to_wei(t["normal"]):
        return NORMAL
    if balance_wei >= eth_to_wei(t["low_compute"]):
        return LOW
    if balance_wei >= eth_to_wei(t["critical"]):
        return CRITICAL
    return DEAD


def policy_for(state: str, cfg: dict) -> Policy:
    p = cfg["policies"][state]
    cost = cfg["compute_cost_eth"].get(state, 0)
    return Policy(
        state=state,
        model_tier=p["model_tier"],
        max_output_tokens=int(p["max_output_tokens"]),
        accept_jobs=bool(p["accept_jobs"]),
        require_prepayment=bool(p["require_prepayment"]),
        may_write_skills=bool(p["may_write_skills"]),
        compute_cost_wei=0 if p.get("zero_cost_only") else eth_to_wei(cost),
        zero_cost_only=bool(p.get("zero_cost_only", False)),
    )
