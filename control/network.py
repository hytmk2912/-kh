"""Outbound network allowlist. All agent HTTP goes through `post_json`.

Only free-tier LLM endpoints and the public Base RPCs are reachable. No
registrar, cloud/VM, or sign-up endpoints are on the list.
"""
from types import MappingProxyType
from urllib.parse import urlparse

from control._frozen import freeze

ALLOWED_HOSTS = frozenset({
    "generativelanguage.googleapis.com",  # Gemini
    "api.groq.com",                        # Groq
    "openrouter.ai",                       # OpenRouter (":free" models only)
    "mainnet.base.org",                    # Base mainnet public RPC (REAL ETH)
    "sepolia.base.org",                    # Base Sepolia public RPC (testnet)
})

# chain_id -> the only RPC host allowed for it.
CHAIN_RPC_HOSTS = MappingProxyType({
    8453: "mainnet.base.org",   # Base mainnet (owner-approved, receive-only)
    84532: "sepolia.base.org",  # Base Sepolia (testnet)
})
MAINNET_CHAIN_IDS = frozenset({8453})
TESTNET_CHAIN_IDS = frozenset({84532})


class HostNotAllowed(PermissionError):
    pass


def check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise HostNotAllowed(f"outbound request to {parsed.hostname!r} blocked by control.network")


def check_chain(chain_id: int, rpc_url: str) -> None:
    host = urlparse(rpc_url).hostname
    if CHAIN_RPC_HOSTS.get(int(chain_id)) != host:
        raise HostNotAllowed(f"chain {chain_id} via {host!r} is not an allowed (chain, RPC) pair")


def post_json(url: str, payload: dict, headers: dict | None = None, timeout: float = 60.0) -> dict:
    check_url(url)
    import requests  # imported lazily so control/ has no hard dependency

    resp = requests.post(url, json=payload, headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


freeze(__name__)
