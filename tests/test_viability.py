from __future__ import annotations

from src.viability import _fx_to_usd, _home_eligible, _region_matches, evaluate, rank

# --- _fx_to_usd ---------------------------------------------------------------

def test_fx_to_usd_converts_known_currency(make_job):
    job = make_job(currency="GBP", salary_min=50000, salary_max=60000)
    lo, hi = _fx_to_usd(job, {"GBP": 1.27})
    assert lo == 50000 * 1.27
    assert hi == 60000 * 1.27


def test_fx_to_usd_unknown_currency_returns_none(make_job):
    job = make_job(currency="XYZ", salary_min=50000, salary_max=60000)
    assert _fx_to_usd(job, {"GBP": 1.27}) == (None, None)


# --- _region_matches / _home_eligible -----------------------------------------

def test_region_matches_is_case_insensitive():
    assert _region_matches("UK", {"uk", "ireland"})
    assert not _region_matches("US", {"uk", "ireland"})


def test_home_eligible_false_when_not_remote(make_job):
    job = make_job(job_type="onsite", remote_scope="worldwide")
    assert not _home_eligible(job, {"worldwide"})


def test_home_eligible_true_for_worldwide_or_emea(make_job):
    job = make_job(job_type="remote", remote_scope="worldwide")
    assert _home_eligible(job, set())


def test_home_eligible_true_on_signal_word_in_geo_tokens(make_job):
    job = make_job(job_type="remote", remote_scope="region-locked",
                    geo_tokens={"nigeria"}, region="")
    assert _home_eligible(job, {"nigeria"})


def test_home_eligible_false_without_any_signal(make_job):
    job = make_job(job_type="remote", remote_scope="country-locked", geo_tokens={"canada"})
    assert not _home_eligible(job, {"nigeria", "worldwide"})


# --- evaluate(): hard drops ----------------------------------------------------

def test_evaluate_drops_excluded_country(make_cfg, make_job):
    cfg = make_cfg()
    job = make_job(country="India", region="India", job_type="onsite")

    survivors, dropped = evaluate([job], cfg)

    assert survivors == []
    assert "Excluded country" in dropped[0].reason


def test_evaluate_drops_onsite_in_dead_region_with_home_base_in_reason(make_cfg, make_job):
    cfg = make_cfg(candidate={"home_base_code": "NG"})
    job = make_job(country="US", region="US", job_type="onsite")

    survivors, dropped = evaluate([job], cfg)

    assert survivors == []
    assert dropped[0].reason == "US onsite: won't hire/sponsor from NG"


def test_evaluate_drops_onsite_in_dead_region_uses_home_base_when_code_missing(make_cfg, make_job):
    cfg = make_cfg(candidate={"home_base": "Kenya", "home_base_code": ""})
    job = make_job(country="Canada", region="Canada", job_type="hybrid")

    _, dropped = evaluate([job], cfg)

    assert "won't hire/sponsor from Kenya" in dropped[0].reason


def test_evaluate_drops_remote_locked_role_with_no_home_eligibility(make_cfg, make_job):
    cfg = make_cfg()
    job = make_job(country="Canada", region="Canada", job_type="remote",
                    remote_scope="country-locked", geo_tokens={"canada"})

    survivors, dropped = evaluate([job], cfg)

    assert survivors == []
    assert "Remote locked" in dropped[0].reason


def test_evaluate_drops_salary_below_band(make_cfg, make_job):
    cfg = make_cfg()
    job = make_job(country="UK", region="UK", job_type="onsite",
                    currency="GBP", salary_min=10000, salary_max=15000)

    survivors, dropped = evaluate([job], cfg)

    assert survivors == []
    assert "Salary" in dropped[0].reason


def test_evaluate_missing_salary_does_not_drop(make_cfg, make_job):
    cfg = make_cfg()
    job = make_job(country="UK", region="UK", job_type="onsite", sponsorship="yes")

    survivors, dropped = evaluate([job], cfg)

    assert dropped == []
    assert survivors[0].viability == "high"


def test_evaluate_hard_sponsorship_filter_drops_explicit_no(make_cfg, make_job):
    cfg = make_cfg(geo={"hard_sponsorship_filter": True})
    job = make_job(country="UK", region="UK", job_type="onsite", sponsorship="no")

    survivors, dropped = evaluate([job], cfg)

    assert survivors == []
    assert "Sponsorship explicitly no" in dropped[0].reason


# --- evaluate(): labels on survivors -------------------------------------------

def test_evaluate_labels_home_eligible_remote_as_high(make_cfg, make_job):
    cfg = make_cfg()
    job = make_job(job_type="remote", remote_scope="worldwide")

    survivors, dropped = evaluate([job], cfg)

    assert dropped == []
    assert survivors[0].viability == "high"


def test_evaluate_labels_welcome_region_sponsorship_undefined_as_medium(make_cfg, make_job):
    cfg = make_cfg()
    job = make_job(country="UK", region="UK", job_type="onsite", sponsorship="undefined")

    survivors, _ = evaluate([job], cfg)

    assert survivors[0].viability == "medium"


def test_evaluate_labels_welcome_region_sponsorship_no_as_low(make_cfg, make_job):
    cfg = make_cfg()
    job = make_job(country="UK", region="UK", job_type="onsite", sponsorship="no")

    survivors, _ = evaluate([job], cfg)

    assert survivors[0].viability == "low"


def test_evaluate_unlisted_region_surfaced_last_when_configured_low(make_cfg, make_job):
    cfg = make_cfg(geo={"unlisted_region": "low"})
    job = make_job(country="Brazil", region="Brazil", job_type="onsite")

    survivors, dropped = evaluate([job], cfg)

    assert dropped == []
    assert survivors[0].viability == "low"


def test_evaluate_unlisted_region_dropped_when_configured_drop(make_cfg, make_job):
    cfg = make_cfg(geo={"unlisted_region": "drop"})
    job = make_job(country="Brazil", region="Brazil", job_type="onsite")

    survivors, dropped = evaluate([job], cfg)

    assert survivors == []
    assert "Unlisted region" in dropped[0].reason


# --- rank() ---------------------------------------------------------------------

def test_rank_orders_by_tier_then_direct_then_match(make_cfg, make_job):
    cfg = make_cfg()
    low = make_job(company="A", viability="low", master_match=90, source_type="board")
    high_board = make_job(company="B", viability="high", master_match=50, source_type="board")
    high_direct = make_job(company="C", viability="high", master_match=50, source_type="direct")

    ordered = rank([low, high_board, high_direct], cfg)

    assert [j.company for j in ordered] == ["C", "B", "A"]


def test_rank_breaks_ties_within_tier_by_master_match(make_cfg, make_job):
    cfg = make_cfg()
    lower = make_job(company="A", viability="medium", master_match=40, source_type="board")
    higher = make_job(company="B", viability="medium", master_match=80, source_type="board")

    ordered = rank([lower, higher], cfg)

    assert [j.company for j in ordered] == ["B", "A"]
