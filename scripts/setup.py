"""Interactive setup wizard: asks a few questions and writes preferences.yaml.

Not called by the daily pipeline — a one-time (or whenever-you-want-to-redo-it)
convenience for filling in preferences.yaml without hand-editing YAML. Doesn't
touch secrets (.env) or data/master_cv.json; see the README for those steps.

Every prompt's default comes from whatever is already in preferences.yaml (the
committed example on a fresh clone, or your own answers on a re-run) — there's
no separate copy of "the defaults" to keep in sync with that file.

Usage:
    uv run python scripts/setup.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PREFERENCES_PATH = REPO_ROOT / "preferences.yaml"


def _load_existing() -> dict[str, Any]:
    if not PREFERENCES_PATH.exists():
        return {}
    try:
        return yaml.safe_load(PREFERENCES_PATH.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


def ask(prompt: str, default: str) -> str:
    raw = input(f"{prompt} [{default}]: ").strip()
    return raw or default


def ask_list(prompt: str, default: list[str]) -> list[str]:
    shown = ", ".join(default)
    raw = input(f"{prompt} (comma-separated) [{shown}]: ").strip()
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def ask_bool(prompt: str, default: bool) -> bool:
    shown = "Y/n" if default else "y/N"
    raw = input(f"{prompt} [{shown}]: ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes")


def ask_int(prompt: str, default: int) -> int:
    raw = input(f"{prompt} [{default}]: ").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"  not a number, keeping default {default}")
        return default


def ask_required(prompt: str, example: str) -> str:
    while True:
        raw = input(f"{prompt} (e.g. {example}): ").strip()
        if raw:
            return raw
        print("  this one's required — it drives the geo-eligibility rules below.")


def yaml_flow_list(items: list[str]) -> str:
    return "[" + ", ".join(items) + "]"


def yaml_block_list(items: list[str], indent: str = "    ") -> str:
    return "\n".join(f"{indent}- {item}" for item in items)


def build_country_hints(
    existing_hints: dict[str, Any], welcome_regions: list[str],
    home_city: str, home_country: str, home_region: str,
) -> str:
    """Keep every existing hint whose region is one of welcome_regions, plus
    the candidate's own home entry. Sourced from preferences.yaml's own
    country_hints (not a second, separately-maintained table), so it can
    never drift from it."""
    wanted_regions = {r.strip().lower() for r in welcome_regions}
    lines: list[str] = []
    seen_keys: set[str] = set()
    for key, value in (existing_hints or {}).items():
        region = str(value.get("region", "")) if isinstance(value, dict) else ""
        if region.strip().lower() not in wanted_regions:
            continue
        country = value.get("country", "") if isinstance(value, dict) else ""
        lines.append(f"    {key}: {{country: {country}, region: {region}}}")
        seen_keys.add(str(key).lower())

    if home_city and home_city.lower() not in seen_keys:
        lines.append(f"    {home_city.lower()}: {{country: {home_country}, region: {home_region}}}")
    if not lines:
        lines.append("    # add entries here, e.g. london: {country: UK, region: UK}")
    return "\n".join(lines)


def main() -> int:
    print("Jobber setup — answers get written to preferences.yaml.")
    print("Press Enter to accept the bracketed default for any question.\n")

    if PREFERENCES_PATH.exists() and not ask_bool(
        f"{PREFERENCES_PATH.name} already exists — overwrite it", False
    ):
        print("Aborted, nothing written.")
        return 0

    existing = _load_existing()
    existing_candidate = existing.get("candidate") or {}
    existing_search = existing.get("search") or {}
    existing_geo = existing.get("geo") or {}
    existing_salary = existing.get("salary") or {}
    existing_fx = existing_salary.get("fx") or {"USD": 1.0, "GBP": 1.27, "EUR": 1.08,
                                                 "AUD": 0.66, "SGD": 0.74, "CAD": 0.73}

    home_city = ask_required("Your city (used only in human-readable drop reasons)", "Lagos")
    home_country = ask_required("Your country", "Nigeria")
    home_region = ask_required(
        "Your region label (used in remote-eligibility matching)", "Africa, LatAm, EMEA"
    )
    home_base_code = ask("Short country code tag (cosmetic only)",
                          existing_candidate.get("home_base_code") or home_country[:2].upper())

    titles = ask_list("Job titles you're targeting",
                       existing_search.get("titles") or ["Senior Backend Engineer"])
    locations = ask_list("Locations to search (JobSpy query strings)",
                          existing_search.get("locations") or ["Remote"])
    seniority = ask_list("Seniority levels", existing_search.get("seniority") or ["mid-level", "senior"])
    boards = ask_list("Job boards to query",
                       existing_search.get("boards") or ["indeed", "linkedin", "glassdoor", "google"])
    country_indeed = ask(
        "country_indeed (drives Indeed/Glassdoor regional endpoint)",
        existing_search.get("country_indeed") or (locations[0] if locations else "United Kingdom"),
    )
    max_age_days = ask_int("Skip postings older than N days", int(existing_search.get("max_age_days") or 30))
    count = ask_int("Target roles to tailor + write per run", int(existing_search.get("count") or 10))
    hard_max = ask_int("Absolute ceiling per run", int(existing_search.get("hard_max") or 15))

    exclude_countries = ask_list("Countries to hard-exclude (never surface)",
                                  existing_geo.get("exclude_countries") or [])
    welcome_regions = ask_list(
        "Welcome regions (conceptual buckets, e.g. UK, Ireland, EU, Australia, Middle East, Singapore, India, Canada, US)",
        existing_geo.get("welcome_regions") or ["UK", "Ireland", "EU"],
    )
    default_signals = existing_geo.get("remote_home_signals") or ["worldwide", "global", "anywhere"]
    remote_home_signals = ask_list(
        "Words that make a remote role eligible from your home region (e.g. worldwide, global, anywhere, your region name)",
        [*default_signals, home_region] if home_region.lower() not in [s.lower() for s in default_signals] else default_signals,
    )
    onsite_dead_regions = ask_list("Regions where onsite/hybrid is a hard drop for you (e.g. US, Canada)",
                                    existing_geo.get("onsite_dead_regions") or [])
    unlisted_region = ask("Unlisted-region handling: low (rank last) or drop",
                           existing_geo.get("unlisted_region") or "low")
    hard_sponsorship_filter = ask_bool("Hard-drop roles explicitly marked no-sponsorship",
                                        bool(existing_geo.get("hard_sponsorship_filter", False)))

    min_usd = ask_int("Minimum salary, USD", int(existing_salary.get("min_usd") or 40000))
    max_usd = ask_int("Maximum salary, USD", int(existing_salary.get("max_usd") or 200000))

    country_hints_block = build_country_hints(
        existing_geo.get("country_hints") or {}, welcome_regions, home_city, home_country, home_region
    )
    fx_block = "\n".join(f"    {code}: {rate}" for code, rate in existing_fx.items())

    content = f"""# Your job-search preferences — generated by scripts/setup.py.
# Re-run the wizard any time, or hand-edit this file directly.
# config.yaml holds pipeline/ops settings (LLM provider/model overrides,
# budget caps, rollover); this file holds *your* search criteria and where
# you're searching from.

candidate:
  # Free text, used only in human-readable drop-reason strings (e.g. "won't
  # hire/sponsor from {home_city}, {home_country}"). Purely cosmetic.
  home_base: {home_city}, {home_country}
  home_base_code: {home_base_code}

search:
  titles:
{yaml_block_list(titles)}
  # Concrete query strings JobSpy actually fetches. Kept in sync with
  # geo.welcome_regions below: every welcomed region should map to at least one
  # searchable location string here, or it is never fetched.
  locations:
{yaml_block_list(locations)}
  count: {count}            # target roles to tailor + write per run
  hard_max: {hard_max}         # absolute ceiling per run, enforced in code before the LLM loop
  seniority:
{yaml_block_list(seniority)}
  max_age_days: {max_age_days}     # skip postings older than this
  # JobSpy consumer boards to query. Drop LinkedIn if it rate-limits you.
  boards:
{yaml_block_list(boards)}
  # country_indeed drives Indeed/Glassdoor regional endpoints for non-remote searches.
  country_indeed: {country_indeed}

geo:
  exclude_countries: {yaml_flow_list(exclude_countries)}   # hard drop, never surface
  # Conceptual buckets the viability step labels against. Keep every entry
  # reachable from search.locations above.
  welcome_regions: {yaml_flow_list(welcome_regions)}
  # Signal words that make a remote role eligible from where you live, even if
  # its region isn't in welcome_regions (e.g. a "worldwide" remote role).
  remote_home_signals: {yaml_flow_list(remote_home_signals)}
  onsite_dead_regions: {yaml_flow_list(onsite_dead_regions)}   # onsite/hybrid here = drop
  # A region in NONE of the lists above and not remote_home_signals-eligible
  # follows this rule: low = surface ranked last, drop = remove. Never left
  # unhandled.
  unlisted_region: {unlisted_region}                     # low | drop
  # When true, drop any row whose classified sponsorship == "no".
  hard_sponsorship_filter: {str(hard_sponsorship_filter).lower()}
  # Location text -> (country, region) hints used to classify a posting's geo.
  # Add an entry for any place you search that isn't already covered; matched
  # as a substring against the posting's lowercased location text.
  country_hints:
{country_hints_block}

salary:
  min_usd: {min_usd}
  max_usd: {max_usd}
  # Manual FX refresh. Multiply local amount by factor to get USD.
  fx:
{fx_block}
"""

    PREFERENCES_PATH.write_text(content, encoding="utf-8")
    print(f"\nWrote {PREFERENCES_PATH}.")
    print("Next: cp .env.example .env and fill in your secrets, then see the README")
    print("for the Notion database + CV import steps.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
