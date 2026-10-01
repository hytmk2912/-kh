"""Outbound network allowlist. All agent HTTP goes through `post_json`.

Only LLM free-tier endpoints and public testnet RPCs are reachable. No
registrar, cloud/VM, or sign-up endpoints are on the list.
"""
from urllib.parse import urlparse

from control._frozen import freeze

ALLOWED_HOSTS = frozenset({
    "generativelanguage.googleapis.com",  # Gemini
    "api.groq.com",                        # Groq
    "openrouter.ai",                       # OpenRouter (":free" models only)
    "sepolia.base.org",                    # Base Sepolia public RPC (testnet)
})
TESTNET_CHAIN_IDS = frozenset({84532})     # Base Sepolia


class HostNotAllowed(PermissionError):
    pass


def check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise HostNotAllowed(f"outbound request to {parsed.hostname!r} blocked by control.network")


def post_json(url: str, payload: dict, headers: dict | None = None, timeout: float = 60.0) -> dict:
    check_url(url)
    import requests  # imported lazily so control/ has no hard dependency

    resp = requests.post(url, json=payload, headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


freeze(__name__)
