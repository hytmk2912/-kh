"""Free-tier LLM clients. Every call is checked against control.free_models
and goes through control.network (host allowlist)."""
import logging
import os

from control import free_models, network

log = logging.getLogger("sovereign")

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
    parts = out["candidates"][0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise LLMError(f"empty Gemini answer (finishReason={out['candidates'][0].get('finishReason')})")
    return text


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
    """Real runs never fall back to the offline stub: a stub must not reach a client."""
    if offline_only:
        return ["offline"]
    return [p for p in cfg["llm"]["provider_order"] if p != "offline" and os.environ.get(KEY_ENV.get(p, ""), "").strip()]


def _transient(exc) -> bool:
    code = getattr(getattr(exc, "response", None), "status_code", None)
    return code in (429, 500, 502, 503, 504)


def generate(cfg: dict, prompt: str, tier: str, max_tokens: int, offline_only: bool = False):
    """Return (text, provider, model). Per provider: requested tier (one retry on
    overload), then the other tier; then the next provider. Raises LLMError if
    every free option fails, so callers keep the work for a later retry."""
    import time

    errors = []
    providers = available_providers(cfg, offline_only)
    if not providers:
        raise LLMError("no free LLM API key in .env (GEMINI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY)")
    for provider in providers:
        tiers = cfg["llm"]["models"][provider]
        models = list(dict.fromkeys([tiers[tier], tiers["light" if tier == "strong" else "strong"]]))
        for model in models:
            free_models.check(provider, model)  # hard stop on paid models
            for attempt in range(2):
                try:
                    return CALLERS[provider](model, prompt, max_tokens), provider, model
                except Exception as exc:
                    detail = getattr(getattr(exc, "response", None), "text", "") or str(exc)
                    errors.append(f"{provider}/{model}: {type(exc).__name__}: {' '.join(detail.split())[:160]}")
                    log.warning("LLM %s/%s failed (attempt %d): %s", provider, model, attempt + 1, errors[-1])
                    if attempt == 0 and _transient(exc):
                        time.sleep(3)
                        continue
                    break
    raise LLMError("all free providers failed: " + " | ".join(errors))
