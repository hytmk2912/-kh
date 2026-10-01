import os

import pytest

import control
from control import free_models, guard, integrity, kill_switch, network, spend_limit, whitelist
from control.paths import ROOT


def test_integrity_sealed():
    assert integrity.problems() == []


@pytest.mark.parametrize("mod,attr", [
    (spend_limit, "DAILY_LIMIT_WEI"), (kill_switch, "check"), (whitelist, "ALLOWED_INDUSTRIES"),
    (free_models, "ALLOWED"), (network, "ALLOWED_HOSTS"), (guard, "write_text"), (control, "guard"),
])
def test_control_attributes_read_only(mod, attr):
    with pytest.raises(PermissionError):
        setattr(mod, attr, None)
    with pytest.raises(PermissionError):
        delattr(mod, attr)


@pytest.mark.parametrize("path", [
    "control/kill_switch.py", "control/new.py", "control/MANIFEST.sha256", "config.yaml", ".env", "KILL",
    "SOUL.md", "main.py", "skills/../config.yaml", "skills/translate.md", "skills/x.py", "skills/sub/x.md",
    "/etc/passwd",
])
def test_guard_denies(path):
    with pytest.raises(guard.WriteDenied):
        guard.write_text(ROOT / path if not path.startswith("/") else path, "x")


def test_guard_allows_new_skill_only_once():
    p = ROOT / "skills" / "zz_pytest_skill.md"
    p.unlink(missing_ok=True)
    try:
        guard.write_text(p, "# ok\n")
        with pytest.raises(guard.WriteDenied):
            guard.write_text(p, "# overwrite\n")
    finally:
        p.unlink(missing_ok=True)


def test_soul_header_protected():
    with pytest.raises(guard.WriteDenied):
        guard.append_soul(integrity.SOUL_HEADER_END)
    text = (ROOT / "SOUL.md").read_text()
    assert integrity.soul_header_ok(text)
    assert not integrity.soul_header_ok(text.replace("testnet", "mainnet", 1))


def test_kill_switch_env(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_KILL", "1")
    with pytest.raises(kill_switch.KillSwitchEngaged):
        kill_switch.check()
    monkeypatch.delenv("SOVEREIGN_KILL")
    kill_switch.check()


def test_spend_limit():
    spend_limit.check(0, spend_limit.DAILY_LIMIT_WEI)
    with pytest.raises(spend_limit.SpendLimitExceeded):
        spend_limit.check(1, spend_limit.DAILY_LIMIT_WEI)


def test_whitelist():
    whitelist.check("translate", "travel")
    for t, i in [("write", "gambling"), ("code", "education"), ("write", "politics")]:
        with pytest.raises(whitelist.NotWhitelisted):
            whitelist.check(t, i)


@pytest.mark.parametrize("prov,model,ok", [
    ("gemini", "gemini-2.5-flash", True), ("gemini", "gemini-2.5-pro", False),
    ("groq", "llama-3.1-8b-instant", True), ("openrouter", "x/y:free", True),
    ("openrouter", "openai/gpt-4o", False), ("openai", "gpt-4o", False), ("anthropic", "any", False),
])
def test_free_models(prov, model, ok):
    assert free_models.is_free(prov, model) is ok


@pytest.mark.parametrize("url", [
    "https://api.namecheap.com/x", "https://api.digitalocean.com/v2/droplets", "https://eth.llamarpc.com",
    "http://sepolia.base.org", "https://api.openai.com/v1/chat/completions",
])
def test_network_blocks(url):
    with pytest.raises(network.HostNotAllowed):
        network.check_url(url)


def test_config_models_are_all_free(cfg):
    for provider, tiers in cfg["llm"]["models"].items():
        for model in tiers.values():
            assert free_models.is_free(provider, model), (provider, model)


def test_configured_chains_allowed(cfg):
    for chain in cfg["chains"].values():
        network.check_chain(chain["chain_id"], chain["rpc_url"])
        network.check_url(chain["rpc_url"])


@pytest.mark.parametrize("chain_id,rpc", [
    (8453, "https://sepolia.base.org"), (84532, "https://mainnet.base.org"),
    (1, "https://mainnet.base.org"), (8453, "https://evil.example/rpc"),
])
def test_chain_rpc_pairs_refused(chain_id, rpc):
    with pytest.raises(network.HostNotAllowed):
        network.check_chain(chain_id, rpc)


def test_no_signing_code_in_agent():
    """Receive-only: nothing in agent/ may sign or broadcast a transaction."""
    for path in (ROOT / "agent").glob("*.py"):
        src = path.read_text()
        for needle in ("sign_transaction", "eth_sendRawTransaction", "eth_sendTransaction", "WALLET_PRIVATE_KEY"):
            assert needle not in src, (path.name, needle)
