from __future__ import annotations

import datetime as dt

from src.acquire import _geo_tokens, _is_ats_url, _iso, _num, _salary_str

# --- _iso --------------------------------------------------------------------

def test_iso_none_and_sentinel_values_return_none():
    assert _iso(None) is None
    assert _iso("") is None
    assert _iso("NaT") is None


def test_iso_epoch_millis():
    # 2024-01-15T00:00:00Z in epoch millis
    millis = int(dt.datetime(2024, 1, 15, tzinfo=dt.UTC).timestamp() * 1000)
    assert _iso(millis) == "2024-01-15"


def test_iso_epoch_seconds():
    seconds = dt.datetime(2024, 1, 15, tzinfo=dt.UTC).timestamp()
    assert _iso(seconds) == "2024-01-15"


def test_iso_datetime_object():
    assert _iso(dt.datetime(2024, 1, 15, 10, 30, tzinfo=dt.UTC)) == "2024-01-15"


def test_iso_date_object():
    assert _iso(dt.date(2024, 1, 15)) == "2024-01-15"


def test_iso_date_string():
    assert _iso("2024-01-15") == "2024-01-15"


def test_iso_datetime_string_with_time():
    assert _iso("2024-01-15T10:00:00") == "2024-01-15"


def test_iso_regex_fallback_only_anchors_at_string_start():
    # The regex fallback is re.match, not re.search — it only catches a date
    # that leads the string, not one embedded further in.
    assert _iso("2024-02-01 (posted recently)") == "2024-02-01"
    assert _iso("posted on 2024-02-01 by recruiter") is None


def test_iso_unparseable_string_returns_none():
    assert _iso("not a date at all") is None


# --- _is_ats_url ---------------------------------------------------------------

def test_is_ats_url_true_for_known_hosts():
    assert _is_ats_url("https://boards.greenhouse.io/acme/jobs/123")
    assert _is_ats_url("https://jobs.lever.co/acme/abc")
    assert _is_ats_url("https://jobs.ashbyhq.com/acme/xyz")
    assert _is_ats_url("https://acme.myworkdayjobs.com/careers/job/1")


def test_is_ats_url_false_for_board_or_empty():
    assert not _is_ats_url("https://www.linkedin.com/jobs/view/123")
    assert not _is_ats_url("")
    assert not _is_ats_url(None)  # pyright: ignore[reportArgumentType] - defensive at runtime


# --- _geo_tokens -----------------------------------------------------------------

def test_geo_tokens_splits_and_lowercases():
    assert _geo_tokens("London, UK", False) == {"london", "uk"}


def test_geo_tokens_adds_remote_when_flagged():
    assert _geo_tokens("Anywhere", True) == {"anywhere", "remote"}


def test_geo_tokens_empty_location_still_flags_remote():
    assert _geo_tokens("", True) == {"remote"}


def test_geo_tokens_empty_location_not_remote():
    assert _geo_tokens("", False) == set()


# --- _num --------------------------------------------------------------------------

def test_num_accepts_positive_numbers():
    assert _num(5)
    assert _num(5.5)


def test_num_rejects_zero_negative_nan_none_and_strings():
    assert not _num(0)
    assert not _num(-5)
    assert not _num(float("nan"))
    assert not _num(None)
    assert not _num("5")


# --- _salary_str ---------------------------------------------------------------------

def test_salary_str_with_both_bounds():
    assert _salary_str(50000, 60000, "GBP", "yearly") == "GBP 50,000–60,000/yearly"


def test_salary_str_with_only_lower_bound():
    assert _salary_str(50000, None, "GBP", None) == "GBP 50,000–?"


def test_salary_str_empty_when_no_bounds():
    assert _salary_str(None, None, "GBP", None) == ""
