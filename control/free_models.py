"""Free-model policy: the agent may only call models on this list.

Gemini: use an API key from a Google AI Studio project WITHOUT billing enabled
(free tier). Groq: free tier models. OpenRouter: only model ids ending in
":free". The `offline` provider is a local stub and costs nothing.
"""
from types import MappingProxyType

from control._frozen import freeze

ALLOWED = MappingProxyType({
    "gemini": frozenset({
        "gemini-2.5-flash", "gemini-2.5-flash-lite",
        "gemini-2.0-flash", "gemini-2.0-flash-lite",
    }),
    "groq": frozenset({
        "llama-3.1-8b-instant", "llama-3.3-70b-versatile", "gemma2-9b-it",
    }),
    "openrouter": None,  # any id ending with ":free"
    "offline": frozenset({"stub"}),
})


class PaidModelRefused(PermissionError):
    pass


def is_free(provider: str, model: str) -> bool:
    if provider not in ALLOWED:
        return False
    if provider == "openrouter":
        return model.endswith(":free")
    return model in ALLOWED[provider]


def check(provider: str, model: str) -> None:
    if not is_free(provider, model):
        raise PaidModelRefused(f"{provider}/{model} is not on the free-model allowlist")


freeze(__name__)
