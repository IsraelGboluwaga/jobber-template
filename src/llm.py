"""Provider-agnostic LLM client (text generation).

Exposes one function, `complete(system, user, max_tokens)`, driven entirely by
config.yaml's `llm.*` section: base_url, model, provider label. It's a plain
OpenAI-compatible client, so any provider that speaks that API works —
DeepSeek, OpenAI, Anthropic's OpenAI-compatible endpoint, Groq, a local
vLLM/Ollama server, etc. Swapping provider is a config change, never a code
change. The API key itself always comes from the single LLM_API_KEY env var
(see config.py's Secrets) regardless of which provider it's for.

Per call:
  * max_tokens set explicitly from config.
  * thinking/reasoning mode off by default for providers that support toggling
    it (currently: DeepSeek, via extra_body={"thinking": {"type": "disabled"}},
    verified against api-docs.deepseek.com). Gated on `llm.provider ==
    "deepseek"`; other providers just don't get the extra_body.
  * bounded retries: <=3, only on 429/5xx/timeouts, capped exponential backoff.
    Never retry a 4xx. No retry logic nested inside another retrying loop.
  * static system prompt + master CV go first so providers with prefix/prompt
    caching (DeepSeek, Anthropic, ...) can reuse that prefix across calls.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

# token accounting for the run (logged to stdout by main)
_USAGE = {"prompt": 0, "completion": 0, "total": 0, "calls": 0}


def usage() -> dict:
    return dict(_USAGE)


def reset_usage() -> None:
    for k in _USAGE:
        _USAGE[k] = 0


def make_client(cfg):
    """Build the OpenAI-compatible client from config + secrets."""
    from openai import OpenAI

    llm = cfg.llm
    key = cfg.secrets.llm_api_key
    if not key:
        raise RuntimeError("LLM_API_KEY is not set.")
    base_url = llm.get("base_url")
    if not base_url:
        raise RuntimeError("config.yaml -> llm.base_url is not set.")
    return OpenAI(api_key=key, base_url=base_url)


def _thinking_extra_body(cfg) -> dict:
    """extra_body to disable thinking for DeepSeek. Empty for providers that
    don't understand it (harmless — OpenAI SDK forwards nothing)."""
    if str(cfg.llm.get("provider", "")).lower() == "deepseek" and not cfg.llm.get("thinking", False):
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

    model = cfg.llm.get("model")
    if not model:
        raise ValueError("config.yaml -> llm.model is not set.")
    extra_body = _thinking_extra_body(cfg)
    # System prompt first => stable prefix for providers with automatic
    # prompt/prefix caching (e.g. DeepSeek, Anthropic).
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
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
