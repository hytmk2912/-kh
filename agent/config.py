"""Load config.yaml and .env (read-only)."""
import os
from decimal import Decimal

import yaml

from control.paths import CONFIG_FILE, ENV_FILE

WEI = 10**18


def eth_to_wei(value) -> int:
    return int(Decimal(str(value)) * WEI)


def wei_to_eth(value: int) -> str:
    return f"{Decimal(int(value)) / WEI:.6f}"


def load_env() -> None:
    """Minimal .env loader (no python-dotenv needed; works on a-Shell/iPhone)."""
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(chain: str | None = None) -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    name = chain or os.environ.get("CHAIN") or cfg["active_chain"]
    if name not in cfg["chains"]:
        raise ValueError(f"unknown chain {name!r}; choose from {sorted(cfg['chains'])}")
    cfg["chain"] = cfg["chains"][name]
    return cfg
