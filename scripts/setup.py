"""Interactive setup wizard: asks a few questions and writes preferences.yaml.

Not called by the daily pipeline — a one-time (or whenever-you-want-to-redo-it)
convenience for filling in preferences.yaml without hand-editing YAML. Doesn't
touch secrets (.env) or data/master_cv.json; see the README for those steps.

Usage:
    uv run python scripts/setup.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PREFERENCES_PATH = REPO_ROOT / "preferences.yaml"

DEFAULT_TITLES = ["Senior Backend Engineer", "Staff Backend Engineer", "Senior Software Engineer"]
DEFAULT_LOCATIONS = ["United Kingdom", "Ireland", "Netherlands", "Germany", "Remote"]
DEFAULT_SENIORITY = ["mid-level", "senior"]
DEFAULT_BOARDS = ["indeed", "linkedin", "glassdoor", "google"]
DEFAULT_WELCOME_REGIONS = ["UK", "Ireland", "EU"]
DEFAULT_REMOTE_HOME_SIGNALS = ["worldwide", "global", "anywhere"]

# Region label -> known country_hints entries this wizard can offer to include.
KNOWN_REGIONS: dict[str, list[tuple[str, str, str]]] = {
    "UK": [("united kingdom", "UK", "UK"), ("uk", "UK", "UK"), ("london", "UK", "UK")],
    "Ireland": [("ireland", "Ireland", "Ireland"), ("dublin", "Ireland", "Ireland")],
    "EU": [
        ("germany", "Germany", "EU"), ("berlin", "Germany", "EU"),
        ("netherlands", "Netherlands", "EU"), ("amsterdam", "Netherlands", "EU"),
        ("france", "France", "EU"), ("spain", "Spain", "EU"), ("portugal", "Portugal", "EU"),
    ],
    "Canada": [("canada", "Canada", "Canada"), ("toronto", "Canada", "Canada")],
    "US": [
        ("united states", "US", "US"), ("usa", "US", "US"),
        ("new york", "US", "US"), ("san francisco", "US", "US"), ("remote us", "US", "US"),
    ],
    "Australia": [
        ("australia", "Australia", "Australia"),
        ("sydney", "Australia", "Australia"), ("melbourne", "Australia", "Australia"),
    ],
    "New Zealand": [("new zealand", "New Zealand", "New Zealand")],
    "Singapore": [("singapore", "Singapore", "Singapore")],
    "Middle East": [
        ("united arab emirates", "UAE", "Middle East"),
        ("uae", "UAE", "Middle East"), ("dubai", "UAE", "Middle East"),
    ],
    "India": [("india", "India", "India")],
}


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


def build_country_hints(welcome_regions: list[str], home_city: str, home_country: str, home_region: str) -> str:
    lines: list[str] = []
    seen_regions = set()
    for region in welcome_regions:
        entries = KNOWN_REGIONS.get(region)
        if not entries or region in seen_regions:
            continue
        seen_regions.add(region)
        for key, country, hint_region in entries:
            lines.append(f"    {key}: {{country: {country}, region: {hint_region}}}")
    if home_city:
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

    home_city = ask_required("Your city (used only in human-readable drop reasons)", "Lagos")
    home_country = ask_required("Your country", "Nigeria")
    home_region = ask_required(
        "Your region label (used in remote-eligibility matching)", "Africa, LatAm, EMEA"
    )
    home_base_code = ask("Short country code tag (cosmetic only)", home_country[:2].upper())

    titles = ask_list("Job titles you're targeting", DEFAULT_TITLES)
    locations = ask_list("Locations to search (JobSpy query strings)", DEFAULT_LOCATIONS)
    seniority = ask_list("Seniority levels", DEFAULT_SENIORITY)
    boards = ask_list("Job boards to query", DEFAULT_BOARDS)
    country_indeed = ask("country_indeed (drives Indeed/Glassdoor regional endpoint)", locations[0] if locations else "United Kingdom")
    max_age_days = ask_int("Skip postings older than N days", 30)
    count = ask_int("Target roles to tailor + write per run", 10)
    hard_max = ask_int("Absolute ceiling per run", 15)

    exclude_countries = ask_list("Countries to hard-exclude (never surface)", [])
    welcome_regions = ask_list("Welcome regions (conceptual buckets, e.g. UK, Ireland, EU, Australia, Middle East, Singapore, India, Canada, US)", DEFAULT_WELCOME_REGIONS)
    remote_home_signals = ask_list(
        "Words that make a remote role eligible from your home region (e.g. worldwide, global, anywhere, your region name)",
        DEFAULT_REMOTE_HOME_SIGNALS + ([home_region] if home_region not in DEFAULT_REMOTE_HOME_SIGNALS else []),
    )
    onsite_dead_regions = ask_list("Regions where onsite/hybrid is a hard drop for you (e.g. US, Canada)", [])
    unlisted_region = ask("Unlisted-region handling: low (rank last) or drop", "low")
    hard_sponsorship_filter = ask_bool("Hard-drop roles explicitly marked no-sponsorship", False)

    min_usd = ask_int("Minimum salary, USD", 40000)
    max_usd = ask_int("Maximum salary, USD", 200000)

    country_hints_block = build_country_hints(welcome_regions, home_city, home_country, home_region)

    content = f"""# Your job-search preferences — generated by scripts/setup.py.
# Re-run the wizard any time, or hand-edit this file directly.
# config.yaml holds pipeline/ops settings (LLM provider, budget caps, rollover);
# this file holds *your* search criteria and where you're searching from.

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
    USD: 1.0
    GBP: 1.27
    EUR: 1.08
    AUD: 0.66
    SGD: 0.74
    CAD: 0.73
"""

    PREFERENCES_PATH.write_text(content, encoding="utf-8")
    print(f"\nWrote {PREFERENCES_PATH}.")
    print("Next: cp .env.example .env and fill in your secrets, then see the README")
    print("for the Notion database + CV import steps.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
