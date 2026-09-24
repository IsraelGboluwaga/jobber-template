from __future__ import annotations

import datetime as dt

import pytest

from src.main import _budget_preflight, _filter_max_age

# --- _filter_max_age -----------------------------------------------------------

def test_filter_max_age_drops_old_keeps_recent(make_job):
    today = dt.datetime.now(tz=dt.UTC).date()
    recent = make_job(posted_date=(today - dt.timedelta(days=5)).isoformat())
    old = make_job(posted_date=(today - dt.timedelta(days=40)).isoformat())

    kept = _filter_max_age([recent, old], 30)

    assert kept == [recent]


def test_filter_max_age_keeps_missing_date():
    from src.acquire import Job
    job = Job(company="A", title="T", url="u", source="indeed", source_type="board", posted_date=None)

    assert _filter_max_age([job], 30) == [job]


def test_filter_max_age_keeps_unparseable_date():
    from src.acquire import Job
    job = Job(company="A", title="T", url="u", source="indeed", source_type="board",
              posted_date="not-a-date")

    assert _filter_max_age([job], 30) == [job]


def test_filter_max_age_zero_is_noop(make_job):
    job = make_job(posted_date="2000-01-01")
    assert _filter_max_age([job], 0) == [job]


# --- _budget_preflight -----------------------------------------------------------

def test_budget_preflight_passes_under_ceiling(make_cfg):
    cfg = make_cfg(llm={"rough_tokens_per_job": 100, "budget_ceiling_tokens": 1000})
    _budget_preflight(cfg, n_rows=5)  # 500 <= 1000, no raise


def test_budget_preflight_raises_over_ceiling(make_cfg):
    cfg = make_cfg(llm={"rough_tokens_per_job": 100, "budget_ceiling_tokens": 1000})
    with pytest.raises(RuntimeError):
        _budget_preflight(cfg, n_rows=20)  # 2000 > 1000
