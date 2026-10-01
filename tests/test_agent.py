import json

import pytest

from agent.config import eth_to_wei
from agent.core import run_job
from agent.replicate import replicate
from agent.states import CRITICAL, DEAD, LOW, NORMAL, state_for_balance

JOB = {"id": "t1", "type": "translate", "industry": "travel", "target_lang": "en", "source_text": "Xin chào"}


@pytest.mark.parametrize("eth,state", [(1, NORMAL), (0.01, NORMAL), (0.009, LOW), (0.003, LOW),
                                       (0.002, CRITICAL), (0.0005, CRITICAL), (0.0004, DEAD), (0, DEAD)])
def test_state_thresholds(cfg, eth, state):
    assert state_for_balance(eth_to_wei(eth), cfg) == state


def test_normal_job_done_and_debits(cfg, mock_env, journal):
    wallet, ledger = mock_env
    from agent import skills
    had_skill = skills.exists("learned_translate_travel")
    wallet.set_balance(eth_to_wei(0.02))
    r = run_job(dict(JOB), cfg, wallet, ledger, offline=True)
    assert r.status == "done" and r.state == NORMAL
    assert wallet.balance() == eth_to_wei(0.02) - r.cost_wei
    assert ledger.spent_today() == r.cost_wei
    assert journal[-1][0] == "JOB_DONE"
    # Normal may add a NEW skill (never overwrites one that exists)
    assert r.extra["learned_skill"] == ("" if had_skill else "learned_translate_travel")


def test_low_compute_uses_light_tier_and_fewer_tokens(cfg, mock_env, journal):
    from agent.states import policy_for
    assert policy_for(LOW, cfg).max_output_tokens < policy_for(NORMAL, cfg).max_output_tokens
    wallet, ledger = mock_env
    wallet.set_balance(eth_to_wei(0.005))
    r = run_job(dict(JOB), cfg, wallet, ledger, offline=True)
    assert r.status == "done" and r.state == LOW and not r.extra["learned_skill"]


def test_critical_requires_prepayment(cfg, mock_env, journal):
    wallet, ledger = mock_env
    wallet.set_balance(eth_to_wei(0.001))
    assert run_job(dict(JOB), cfg, wallet, ledger, offline=True).status == "refused"
    r = run_job(dict(JOB, payment_tx="0xmock-1"), cfg, wallet, ledger, offline=True)
    assert r.status == "done" and r.paid_wei == r.price_wei
    # replaying the same payment is refused
    assert run_job(dict(JOB, payment_tx="0xmock-1"), cfg, wallet, ledger, offline=True).status == "refused"


def test_dead_refuses(cfg, mock_env, journal):
    wallet, ledger = mock_env
    wallet.set_balance(0)
    r = run_job(dict(JOB), cfg, wallet, ledger, offline=True)
    assert r.status == "refused" and r.state == DEAD and journal[-1][0] == "DEAD"


def test_whitelist_refusal(cfg, mock_env, journal):
    wallet, ledger = mock_env
    r = run_job(dict(JOB, industry="gambling"), cfg, wallet, ledger, offline=True)
    assert r.status == "refused" and "gambling" in r.reason


def test_daily_cap(cfg, mock_env, journal):
    from control import spend_limit
    wallet, ledger = mock_env
    ledger.record("spend", spend_limit.DAILY_LIMIT_WEI, "test")
    r = run_job(dict(JOB), cfg, wallet, ledger, offline=True)
    assert r.status == "refused" and "Daily cap" in r.reason


def test_kill_switch_halts(cfg, mock_env, journal, monkeypatch):
    monkeypatch.setenv("SOVEREIGN_KILL", "1")
    wallet, ledger = mock_env
    assert run_job(dict(JOB), cfg, wallet, ledger, offline=True).status == "halted"


def test_paid_model_in_config_is_refused(cfg, mock_env, journal):
    from control.free_models import PaidModelRefused
    wallet, ledger = mock_env
    bad = json.loads(json.dumps(cfg))
    bad["llm"]["models"]["offline"]["strong"] = "gpt-4o"
    with pytest.raises(PaidModelRefused):
        run_job(dict(JOB), bad, wallet, ledger, offline=True)
    assert wallet.balance() == eth_to_wei(cfg["wallet"]["mock_start_balance_eth"])  # nothing charged


def test_replicate_disabled():
    with pytest.raises(NotImplementedError, match="chủ duyệt tay"):
        replicate()


def test_invoice_written(cfg, mock_env, journal):
    from control.paths import OUTPUT_DIR
    wallet, ledger = mock_env
    wallet.set_balance(eth_to_wei(0.02))
    run_job(dict(JOB, id="t-invoice"), cfg, wallet, ledger, offline=True)
    inv = json.loads((OUTPUT_DIR / "t-invoice.invoice.json").read_text())
    assert inv["chain_id"] == cfg["chain"]["chain_id"] and inv["pay_to"] == wallet.address
