"""Unit tests for scripts/setup.py's pure helpers. The interactive main()
loop isn't tested here, same as scripts/import_cv.py's main()."""
from __future__ import annotations

from scripts.setup import build_country_hints


def test_keeps_only_hints_in_welcome_regions():
    existing = {
        "united kingdom": {"country": "UK", "region": "UK"},
        "germany": {"country": "Germany", "region": "EU"},
        "united states": {"country": "US", "region": "US"},
    }

    block = build_country_hints(existing, ["UK", "EU"], home_city="", home_country="", home_region="")

    assert "united kingdom" in block
    assert "germany" in block
    assert "united states" not in block


def test_region_matching_is_case_insensitive():
    existing = {"united kingdom": {"country": "UK", "region": "UK"}}

    block = build_country_hints(existing, ["uk"], home_city="", home_country="", home_region="")

    assert "united kingdom" in block


def test_adds_home_entry_when_not_already_covered():
    block = build_country_hints({}, [], home_city="Lagos", home_country="Nigeria", home_region="Africa")

    assert "lagos: {country: Nigeria, region: Africa}" in block


def test_does_not_duplicate_home_entry_already_present():
    existing = {"lagos": {"country": "Nigeria", "region": "Africa"}}

    block = build_country_hints(existing, ["Africa"], home_city="Lagos", home_country="Nigeria", home_region="Africa")

    assert block.count("lagos") == 1


def test_falls_back_to_placeholder_comment_when_nothing_matches():
    block = build_country_hints({}, [], home_city="", home_country="", home_region="")

    assert block.strip().startswith("#")
