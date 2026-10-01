import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def cfg():
    from agent.config import load_config
    return load_config()


@pytest.fixture
def journal(monkeypatch):
    """Capture SOUL entries instead of appending to the real SOUL.md."""
    import agent.soul
    from control.paths import SKILLS_DIR
    before = set(SKILLS_DIR.glob("learned_*.md"))
    entries = []
    monkeypatch.setattr(agent.soul, "log", lambda event, **f: entries.append((event, f)))
    yield entries
    for f in set(SKILLS_DIR.glob("learned_*.md")) - before:  # don't leave test-made skills behind
        f.unlink()


@pytest.fixture
def mock_env(tmp_path, cfg):
    from control.paths import STATE_DIR
    from agent.ledger import Ledger
    from agent.wallet import MockWallet
    d = STATE_DIR / "test"
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("*"):
        f.unlink()
    return MockWallet(cfg, path=d / "wallet.json"), Ledger(d / "ledger.jsonl")
