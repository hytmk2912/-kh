"""Free-tier LLM clients. Every call is checked against control.free_models
and goes through control.network (host allowlist)."""
import os

from control import free_models, network

KEY_ENV = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "openrouter": "OPENROUTER_API_KEY"}


class LLMError(RuntimeError):
    pass


def _gemini(model, prompt, max_tokens):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    out = network.post_json(
        url,
        {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": max_tokens}},
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
    )
    return "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"])


def _openai_compatible(url, key_env, model, prompt, max_tokens):
    out = network.post_json(
        url,
        {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
        headers={"Authorization": f"Bearer {os.environ[key_env]}"},
    )
    return out["choices"][0]["message"]["content"]


def _offline(model, prompt, max_tokens):
    body = prompt.split("### INPUT", 1)[-1].strip()
    return "[OFFLINE STUB - no free API key configured]\n\n" + body[: max_tokens * 4]


CALLERS = {
    "gemini": _gemini,
    "groq": lambda m, p, n: _openai_compatible("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", m, p, n),
    "openrouter": lambda m, p, n: _openai_compatible("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", m, p, n),
    "offline": _offline,
}


def available_providers(cfg: dict, offline_only: bool = False) -> list:
    order = cfg["llm"]["provider_order"]
    if offline_only:
        return ["offline"]
    return [p for p in order if p == "offline" or os.environ.get(KEY_ENV.get(p, ""), "").strip()]


def generate(cfg: dict, prompt: str, tier: str, max_tokens: int, offline_only: bool = False):
    """Return (text, provider, model). Tries providers in configured order."""
    errors = []
    for provider in available_providers(cfg, offline_only):
        model = cfg["llm"]["models"][provider][tier]
        free_models.check(provider, model)  # hard stop on paid models
        try:
            return CALLERS[provider](model, prompt, max_tokens), provider, model
        except Exception as exc:  # fall through to next free provider
            errors.append(f"{provider}/{model}: {type(exc).__name__}: {str(exc)[:200]}")
    raise LLMError("all free providers failed: " + " | ".join(errors))
