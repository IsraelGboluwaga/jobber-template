"""Shared fixtures: a fake Config (no disk I/O) and a Job factory."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.acquire import Job
from src.config import Config, Secrets

REPO_ROOT = Path(__file__).resolve().parent.parent

# Mirrors preferences.yaml + config.yaml's shape, trimmed to what tests need.
# Individual tests override only the keys they care about via make_cfg(**overrides).
# Note: llm.provider/model/base_url are set here even though the real,
# committed config.yaml deliberately leaves them unset (env-var driven) — a
# fully-specified llm section is what most tests want to override pieces of;
# see test_llm.py for cases that specifically test the unset/env-driven paths.
DEFAULT_RAW: dict[str, Any] = {
    "candidate": {"home_base": "Nigeria", "home_base_code": "NG"},
    "search": {
        "titles": ["Senior Backend Engineer"],
        "locations": ["United Kingdom", "Remote"],
        "count": 10,
        "hard_max": 15,
        "seniority": ["mid-level", "senior", "staff"],
        "max_age_days": 30,
        "boards": ["indeed"],
        "country_indeed": "United Kingdom",
    },
    "geo": {
        "exclude_countries": ["India"],
        "welcome_regions": ["UK", "Ireland", "EU", "Australia", "New Zealand",
                             "Middle East", "Singapore"],
        "remote_home_signals": ["worldwide", "global", "anywhere", "emea",
                                 "africa", "nigeria"],
        "onsite_dead_regions": ["US", "Canada"],
        "unlisted_region": "low",
        "hard_sponsorship_filter": False,
        "country_hints": {
            "united kingdom": {"country": "UK", "region": "UK"},
            "uk": {"country": "UK", "region": "UK"},
            "nigeria": {"country": "Nigeria", "region": "Africa"},
            "united states": {"country": "US", "region": "US"},
            "canada": {"country": "Canada", "region": "Canada"},
        },
    },
    "salary": {
        "min_usd": 30000,
        "max_usd": 200000,
        "fx": {"USD": 1.0, "GBP": 1.27, "EUR": 1.08},
    },
    "source": {"prefer_direct": True},
    "llm": {
        "provider": "deepseek",
        "model": "deepseek-flash",
        "base_url": "https://api.deepseek.com",
        "thinking": False,
        "max_tokens_cv": 1500,
        "max_tokens_answers": 800,
        "rough_tokens_per_job": 4000,
        "budget_ceiling_tokens": 80000,
    },
    "rollover": {"archive_new_after_days": 14},
    "notify": {"ntfy_topic": "jobba-alert"},
}


def _deep_merge(base: dict, overrides: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@pytest.fixture
def make_cfg():
    """make_cfg(geo={"exclude_countries": [...]}) -> Config, deep-merged over
    DEFAULT_RAW so each test only states what it cares about."""
    def _make(**overrides: Any) -> Config:
        return Config(raw=_deep_merge(DEFAULT_RAW, overrides), secrets=Secrets())
    return _make


@pytest.fixture
def make_job():
    def _make(**overrides: Any) -> Job:
        base: dict[str, Any] = {
            "company": "Acme", "title": "Senior Backend Engineer",
            "url": "https://example.com/job/1", "source": "indeed", "source_type": "board",
        }
        base.update(overrides)
        return Job(**base)
    return _make
