from __future__ import annotations

from src.dedup import (
    assign_ids,
    canonical_url,
    collapse_duplicates,
    drop_already_seen,
    stable_job_id,
)

# --- canonical_url --------------------------------------------------------

def test_canonical_url_strips_query_fragment_and_trailing_slash():
    url = "https://Example.com/jobs/123/?utm_source=x#frag"
    assert canonical_url(url) == "https://example.com/jobs/123"


def test_canonical_url_lowercases_host_only():
    assert canonical_url("https://EXAMPLE.com/Jobs/ABC") == "https://example.com/Jobs/ABC"


def test_canonical_url_empty_string():
    assert canonical_url("") == ""


# --- stable_job_id ----------------------------------------------------------

def test_stable_job_id_uses_native_id_when_present(make_job):
    job = make_job()
    assert stable_job_id(job, native_id="ATS-123") == "ATS-123"


def test_stable_job_id_is_deterministic_hash_without_native_id(make_job):
    job1 = make_job(company="Acme", title="Backend Engineer", url="https://x.com/1")
    job2 = make_job(company="Acme", title="Backend Engineer", url="https://x.com/1")
    assert stable_job_id(job1) == stable_job_id(job2)
    assert len(stable_job_id(job1)) == 16


def test_stable_job_id_differs_for_different_postings(make_job):
    job1 = make_job(company="Acme", title="Backend Engineer", url="https://x.com/1")
    job2 = make_job(company="Beta", title="Backend Engineer", url="https://x.com/1")
    assert stable_job_id(job1) != stable_job_id(job2)


# --- assign_ids ---------------------------------------------------------------

def test_assign_ids_fills_only_missing(make_job):
    with_id = make_job(job_id="already-set")
    without_id = make_job(url="https://x.com/2")

    assign_ids([with_id, without_id])

    assert with_id.job_id == "already-set"
    assert without_id.job_id != ""


# --- collapse_duplicates -------------------------------------------------------

def test_collapse_prefers_direct_over_board(make_job):
    board = make_job(company="Acme", title="Engineer", source_type="board", description="short")
    direct = make_job(company="Acme", title="Engineer", source_type="direct", description="short")

    collapsed = collapse_duplicates([board, direct])

    assert len(collapsed) == 1
    assert collapsed[0].source_type == "direct"


def test_collapse_prefers_longer_description_when_same_source_type(make_job):
    short = make_job(company="Acme", title="Engineer", description="short")
    long_ = make_job(company="Acme", title="Engineer", description="a much longer description here")

    collapsed = collapse_duplicates([short, long_])

    assert len(collapsed) == 1
    assert collapsed[0] is long_


def test_collapse_keeps_distinct_company_title_pairs(make_job):
    # job_id must be assigned first, same as the real pipeline order
    # (assign_ids runs before collapse_duplicates) — its second pass dedupes
    # by job_id, and two default-empty ids would collide otherwise.
    a = make_job(company="Acme", title="Engineer", job_id="id-a")
    b = make_job(company="Beta", title="Engineer", job_id="id-b")

    collapsed = collapse_duplicates([a, b])

    assert len(collapsed) == 2


def test_collapse_second_pass_dedupes_identical_job_ids(make_job):
    a = make_job(company="Acme", title="Engineer", job_id="same-id")
    b = make_job(company="Beta", title="Manager", job_id="same-id")

    collapsed = collapse_duplicates([a, b])

    assert len(collapsed) == 1


# --- drop_already_seen ----------------------------------------------------------

def test_assign_ids_then_collapse_keeps_distinct_postings(make_job):
    """Mirrors the real pipeline order (assign_ids before collapse_duplicates)."""
    a = make_job(company="Acme", title="Engineer", url="https://x.com/1")
    b = make_job(company="Beta", title="Engineer", url="https://x.com/2")

    assign_ids([a, b])
    collapsed = collapse_duplicates([a, b])

    assert len(collapsed) == 2


def test_drop_already_seen_filters_known_ids(make_job):
    seen = make_job(job_id="seen-1")
    fresh = make_job(job_id="fresh-1")

    kept = drop_already_seen([seen, fresh], {"seen-1"})

    assert kept == [fresh]
