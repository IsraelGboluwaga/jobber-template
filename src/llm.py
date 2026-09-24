"""Provider-agnostic LLM client (text generation).

Exposes one function, `complete(system, user, max_tokens)`. It's a plain
OpenAI-compatible client, so any provider that speaks that API works —
DeepSeek, OpenAI, Anthropic's OpenAI-compatible endpoint, Groq, a local
vLLM/Ollama server, etc. Swapping provider is a config/env change, never a
code change. The API key itself always comes from the single LLM_API_KEY env
var (see config.py's Secrets) regardless of which provider it's for.

Provider/model/base_url resolution (see `resolve_llm`), in priority order:
  1. LLM_PROVIDER / LLM_MODEL env vars
  2. config.yaml's llm.provider / llm.model / llm.base_url
  3. PROVIDER_DEFAULTS below, keyed by the resolved provider
`base_url` has no env override — providers not in PROVIDER_DEFAULTS (Groq, a
local server, ...) must set it explicitly in config.yaml.

Per call:
  * max_tokens set explicitly from config.
  * thinking/reasoning mode off by default for providers that support toggling
    it (currently: DeepSeek, via extra_body={"thinking": {"type": "disabled"}},
    verified against api-docs.deepseek.com). Gated on the resolved provider
    being "deepseek"; other providers just don't get the extra_body.
  * bounded retries: <=3, only on 429/5xx/timeouts, capped exponential backoff.
    Never retry a 4xx. No retry logic nested inside another retrying loop.
  * static system prompt + master CV go first so providers with automatic
    prefix/prompt caching on this endpoint shape (e.g. DeepSeek) can reuse
    that prefix across calls. Note: Anthropic's own SDK supports prompt
    caching, but its OpenAI-compatible endpoint (used here if you point
    base_url at it) explicitly does not — see platform.claude.com's
    OpenAI SDK compatibility docs.
"""
from __future__ import annotations

import logging
import time
from typing import NamedTuple

log = logging.getLogger(__name__)

# Built-in fallback for each known provider, used only where config.yaml /
# LLM_MODEL don't already say. Not an exhaustive provider list — anything
# else just needs config.yaml -> llm.base_url (and usually llm.model) set
# explicitly. Keep these current: a stale default here is worse than none.
PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-flash"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-6-luna"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1/", "model": "claude-haiku-4-5-20251001"},
}

DEFAULT_PROVIDER = "deepseek"

# token accounting for the run (logged to stdout by main)
_USAGE = {"prompt": 0, "completion": 0, "total": 0, "calls": 0}


def usage() -> dict:
    return dict(_USAGE)


def reset_usage() -> None:
    for k in _USAGE:
        _USAGE[k] = 0


class ResolvedLLM(NamedTuple):
    provider: str
    model: str
    base_url: str


def resolve_llm(cfg) -> ResolvedLLM:
    """Resolve provider/model/base_url per the module docstring's priority
    order. Pure function — no network, no client construction — so it's unit
    tested directly rather than through a live call.

    config.yaml's llm.model/llm.base_url are scoped to whichever provider
    config.yaml itself implies — its own llm.provider, or DEFAULT_PROVIDER if
    it doesn't set one — and only apply when that matches the resolved
    provider. Otherwise an LLM_PROVIDER override would silently inherit
    values tuned for a different provider (e.g. DeepSeek's model name sent to
    Anthropic), whether or not config.yaml bothered to spell out `provider:`.
    """
    config_provider_raw = cfg.llm.get("provider")
    provider = (cfg.secrets.llm_provider or config_provider_raw or DEFAULT_PROVIDER).strip().lower()
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    implied_config_provider = str(config_provider_raw or DEFAULT_PROVIDER).strip().lower()
    provider_matches_config = implied_config_provider == provider

    base_url = (cfg.llm.get("base_url") if provider_matches_config else None) or defaults.get("base_url")
    if not base_url:
        raise RuntimeError(
            f"No base_url for LLM provider '{provider}' — it has no built-in default, "
            "so set config.yaml -> llm.base_url explicitly."
        )

    model = (
        cfg.secrets.llm_model
        or (cfg.llm.get("model") if provider_matches_config else None)
        or defaults.get("model")
    )
    if not model:
        raise RuntimeError(
            f"No model for LLM provider '{provider}' — set the LLM_MODEL env var, "
            "config.yaml -> llm.model, or use a provider with a built-in default "
            f"({', '.join(sorted(PROVIDER_DEFAULTS))})."
        )

    return ResolvedLLM(provider=provider, model=model, base_url=base_url)


def make_client(cfg):
    """Build the OpenAI-compatible client from config + secrets."""
    from openai import OpenAI

    key = cfg.secrets.llm_api_key
    if not key:
        raise RuntimeError("LLM_API_KEY is not set.")
    resolved = resolve_llm(cfg)
    return OpenAI(api_key=key, base_url=resolved.base_url)


def _thinking_extra_body(provider: str, thinking: bool) -> dict:
    """extra_body to disable thinking for DeepSeek. Empty for providers that
    don't understand it (harmless — OpenAI SDK forwards nothing)."""
    if provider == "deepseek" and not thinking:
        return {"thinking": {"type": "disabled"}}
    return {}


_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def complete(system: str, user: str, max_tokens: int, *, client=None, cfg=None) -> str:
    """One completion. `client` and `cfg` are passed by the caller so the client
    is built once per run. Retries transient failures only, up to 3 times."""
    if client is None or cfg is None:
        raise ValueError("complete() requires client and cfg (build once per run).")

    from openai import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        RateLimitError,
    )

    resolved = resolve_llm(cfg)
    extra_body = _thinking_extra_body(resolved.provider, cfg.llm.get("thinking", False))
    # System prompt first => stable prefix for providers with automatic
    # prompt/prefix caching on this endpoint shape (e.g. DeepSeek). Not
    # Anthropic's OpenAI-compatible endpoint — see module docstring.
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=resolved.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.4,
                extra_body=extra_body or None,
            )
            _account(resp)
            return (resp.choices[0].message.content or "").strip()
        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            last_exc = exc
        except APIStatusError as exc:
            if exc.status_code in _RETRYABLE_STATUS:
                last_exc = exc
            else:
                raise  # never retry a 4xx
        if attempt < 2:
            log.warning("LLM transient failure (attempt %d): %s — backing off %.1fs",
                        attempt + 1, last_exc, delay)
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
    raise RuntimeError(f"LLM call failed after retries: {last_exc}")


def _account(resp) -> None:
    _USAGE["calls"] += 1
    u = getattr(resp, "usage", None)
    if not u:
        return
    _USAGE["prompt"] += getattr(u, "prompt_tokens", 0) or 0
    _USAGE["completion"] += getattr(u, "completion_tokens", 0) or 0
    _USAGE["total"] += getattr(u, "total_tokens", 0) or 0
