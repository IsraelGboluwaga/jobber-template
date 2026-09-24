"""resolve_llm is the one part of llm.py that's pure (no network), so unlike
the rest of the module it's unit tested directly. See src/llm.py's docstring
for the full provider/model/base_url precedence order."""
from __future__ import annotations

import pytest

from src.config import Secrets, load_config
from src.llm import PROVIDER_DEFAULTS, resolve_llm


def test_uses_config_yaml_values_when_present(make_cfg):
    cfg = make_cfg()  # DEFAULT_RAW: provider=deepseek, model=deepseek-flash, base_url=deepseek's

    resolved = resolve_llm(cfg)

    assert resolved.provider == "deepseek"
    assert resolved.model == "deepseek-flash"          # config.yaml's override, not the built-in default
    assert resolved.base_url == "https://api.deepseek.com"


def test_falls_back_to_built_in_default_model_and_base_url(make_cfg):
    cfg = make_cfg(llm={"provider": "anthropic", "model": None, "base_url": None})

    resolved = resolve_llm(cfg)

    assert resolved.provider == "anthropic"
    assert resolved.model == PROVIDER_DEFAULTS["anthropic"]["model"]
    assert resolved.base_url == PROVIDER_DEFAULTS["anthropic"]["base_url"]


def test_env_provider_and_model_override_config_yaml(make_cfg):
    cfg = make_cfg()  # config.yaml says deepseek/deepseek-flash
    cfg.secrets = Secrets(llm_provider="anthropic", llm_model="claude-sonnet-5")

    resolved = resolve_llm(cfg)

    assert resolved.provider == "anthropic"
    assert resolved.model == "claude-sonnet-5"          # env wins over config.yaml and the built-in default
    # config.yaml's base_url was deepseek's — an env override to a different
    # provider must NOT inherit it; falls through to anthropic's built-in.
    assert resolved.base_url == PROVIDER_DEFAULTS["anthropic"]["base_url"]


def test_env_model_only_keeps_config_yaml_provider(make_cfg):
    cfg = make_cfg()  # provider=deepseek stays put
    cfg.secrets = Secrets(llm_model="deepseek-reasoner")

    resolved = resolve_llm(cfg)

    assert resolved.provider == "deepseek"
    assert resolved.model == "deepseek-reasoner"
    assert resolved.base_url == "https://api.deepseek.com"  # provider unchanged, so config.yaml's base_url still applies


def test_no_provider_configured_defaults_to_deepseek(make_cfg):
    cfg = make_cfg(llm={"provider": None, "model": None, "base_url": None})

    resolved = resolve_llm(cfg)

    assert resolved.provider == "deepseek"
    assert resolved.model == PROVIDER_DEFAULTS["deepseek"]["model"]
    assert resolved.base_url == PROVIDER_DEFAULTS["deepseek"]["base_url"]


def test_unknown_provider_without_base_url_raises(make_cfg):
    cfg = make_cfg(llm={"provider": "groq", "model": None, "base_url": None})

    with pytest.raises(RuntimeError, match="base_url"):
        resolve_llm(cfg)


def test_unknown_provider_with_explicit_base_url_still_needs_a_model(make_cfg):
    cfg = make_cfg(llm={"provider": "groq", "model": None, "base_url": "https://api.groq.com/openai/v1"})

    with pytest.raises(RuntimeError, match="model"):
        resolve_llm(cfg)


def test_unknown_provider_fully_configured_resolves(make_cfg):
    cfg = make_cfg(llm={
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1",
    })

    resolved = resolve_llm(cfg)

    assert resolved == ("groq", "llama-3.3-70b-versatile", "https://api.groq.com/openai/v1")


def test_env_provider_override_ignores_leftover_model_even_without_a_provider_key(make_cfg):
    """Regression: config.yaml can set llm.model without an explicit
    llm.provider line (the committed config.yaml itself does this — see its
    comments). An LLM_PROVIDER override must still not inherit that model,
    because it was implicitly scoped to DEFAULT_PROVIDER (deepseek), not to
    whatever provider ends up resolved."""
    cfg = make_cfg(llm={"provider": None, "model": "deepseek-flash", "base_url": None})
    cfg.secrets = Secrets(llm_provider="anthropic")

    resolved = resolve_llm(cfg)

    assert resolved.provider == "anthropic"
    assert resolved.model == PROVIDER_DEFAULTS["anthropic"]["model"]  # NOT "deepseek-flash"
    assert resolved.base_url == PROVIDER_DEFAULTS["anthropic"]["base_url"]


def test_resolves_against_real_config_yaml_with_no_env_set(monkeypatch):
    """Guard for the actual shipped config.yaml, which deliberately leaves
    llm.provider/model/base_url unset: a fresh clone with zero env vars must
    still resolve to a real, working default (currently DeepSeek)."""
    for var in ("LLM_PROVIDER", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)

    resolved = resolve_llm(load_config())

    assert resolved.provider
    assert resolved.model
    assert resolved.base_url
