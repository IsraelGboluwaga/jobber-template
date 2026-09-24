from __future__ import annotations

from src.classify import (
    _country_hints,
    _derive_geo,
    classify,
    classify_job_type,
    classify_relocation,
    classify_remote_scope,
    classify_seniority,
    classify_sponsorship,
)

# --- classify_job_type ------------------------------------------------------

def test_job_type_hybrid_beats_remote_signal():
    assert classify_job_type("Hybrid role, 3 days in office", {"remote"}) == "hybrid"


def test_job_type_remote_from_geo_token():
    assert classify_job_type("Great opportunity", {"remote"}) == "remote"


def test_job_type_remote_from_text():
    assert classify_job_type("This is a fully remote position", set()) == "remote"


def test_job_type_onsite_from_text():
    assert classify_job_type("You must relocate to our HQ", set()) == "onsite"


def test_job_type_defaults_to_onsite_when_unstated():
    assert classify_job_type("Join our growing team", set()) == "onsite"


# --- classify_remote_scope ---------------------------------------------------

def test_remote_scope_is_na_when_not_remote():
    assert classify_remote_scope("worldwide remote", "onsite") == "n/a"


def test_remote_scope_worldwide():
    assert classify_remote_scope("Work from anywhere", "remote") == "worldwide"


def test_remote_scope_emea():
    assert classify_remote_scope("Remote (EMEA)", "remote") == "emea"


def test_remote_scope_country_locked():
    text = "Must be legally authorized to work in United Kingdom"
    assert classify_remote_scope(text, "remote") == "country-locked"


def test_remote_scope_region_locked():
    assert classify_remote_scope("Remote (Europe only)", "remote") == "region-locked"


def test_remote_scope_unclear_when_no_signal():
    assert classify_remote_scope("Remote position available", "remote") == "unclear"


# --- classify_sponsorship ----------------------------------------------------

def test_sponsorship_yes():
    assert classify_sponsorship("Visa sponsorship is available for this role") == "yes"


def test_sponsorship_no():
    assert classify_sponsorship("We do not sponsor work visas") == "no"


def test_sponsorship_undefined_by_default():
    assert classify_sponsorship("Come join our team") == "undefined"


# --- classify_relocation -----------------------------------------------------

def test_relocation_yes():
    assert classify_relocation("Relocation assistance provided") == "yes"


def test_relocation_no():
    assert classify_relocation("Relocation is not available") == "no"


def test_relocation_undefined_by_default():
    assert classify_relocation("Come join our team") == "undefined"


# --- classify_seniority -------------------------------------------------------

def test_seniority_matches_configured_level():
    levels = ["mid-level", "senior", "staff"]
    assert classify_seniority("Senior Backend Engineer", "", levels) == "senior"


def test_seniority_prefers_most_senior_configured_level():
    levels = ["mid-level", "senior", "staff"]
    # title mentions both staff and senior; staff outranks senior in `order`.
    assert classify_seniority("Staff / Senior Backend Engineer", "", levels) == "staff"


def test_seniority_falls_back_to_detected_level_even_if_unconfigured():
    # "principal" isn't in the configured levels, but it's still the most
    # senior term present, so it's returned rather than "".
    assert classify_seniority("Principal Engineer", "", ["mid-level", "senior"]) == "principal"


def test_seniority_empty_when_no_signal():
    assert classify_seniority("Backend Engineer", "", ["mid-level", "senior"]) == ""


# --- _country_hints / _derive_geo --------------------------------------------

def test_country_hints_reads_from_config(make_cfg):
    cfg = make_cfg()
    hints = _country_hints(cfg)

    assert hints["united kingdom"] == ("UK", "UK")
    assert hints["nigeria"] == ("Nigeria", "Africa")


def test_derive_geo_matches_from_geo_tokens(make_cfg, make_job):
    cfg = make_cfg()
    job = make_job(geo_tokens={"united kingdom"})

    _derive_geo(job, cfg)

    assert job.country == "UK"
    assert job.region == "UK"


def test_derive_geo_does_not_overwrite_existing_country(make_cfg, make_job):
    cfg = make_cfg()
    job = make_job(geo_tokens={"nigeria"}, country="Preset", region="Preset")

    _derive_geo(job, cfg)

    assert job.country == "Preset"
    assert job.region == "Preset"


def test_derive_geo_falls_back_to_authorization_text(make_cfg, make_job):
    cfg = make_cfg()
    job = make_job(
        geo_tokens={"remote"},
        description="Candidates must be authorized to work in Nigeria only.",
    )

    _derive_geo(job, cfg)

    assert job.country == "Nigeria"
    assert job.region == "Africa"


def test_derive_geo_leaves_unknown_when_no_hint_matches(make_cfg, make_job):
    cfg = make_cfg()
    job = make_job(geo_tokens={"atlantis"})

    _derive_geo(job, cfg)

    assert job.country == ""
    assert job.region == ""


# --- classify() integration ---------------------------------------------------

def test_classify_populates_all_categorical_fields(make_cfg, make_job):
    cfg = make_cfg()
    job = make_job(
        title="Staff Backend Engineer",
        description=(
            "Fully remote, work from anywhere. Visa sponsorship is available. "
            "Relocation assistance provided."
        ),
        geo_tokens={"remote"},
    )

    classify(job, cfg)

    assert job.job_type == "remote"
    assert job.remote_scope == "worldwide"
    assert job.sponsorship == "yes"
    assert job.relocation == "yes"
    assert job.seniority == "staff"


def test_classify_without_llm_client_leaves_unclear_fields_alone(make_cfg, make_job):
    cfg = make_cfg()
    job = make_job(description="Remote role.", geo_tokens={"remote"})

    classify(job, cfg, llm_client=None)

    assert job.remote_scope == "unclear"
    assert job.sponsorship == "undefined"
