# Jobber — daily job-search pipeline

If this saves you time, consider leaving a star on the repo — it helps other
job-seekers find it.

A lightweight **scheduled pipeline** (no web app, no server, no UI) that runs once
each morning on GitHub Actions and:

1. Finds ~10 postings matching your criteria across the consumer job boards
   (LinkedIn / Indeed / Glassdoor / Google, via JobSpy).
2. Deduplicates, drops roles that don't match your location/sponsorship rules, and ranks the rest.
3. Tailors your CV to each new posting (via any OpenAI-compatible LLM API — DeepSeek by default).
4. Drafts answers to each posting's application questions, if any.
5. Writes one row per job into a Notion database, with the tailored CV on its own
   linked page and any drafted answers in the row's page body.
6. Sends a single ntfy.sh push when the run finishes.

You review and apply manually. **The pipeline never auto-applies.** Disabling the
GitHub Actions workflow stops the entire system.

---

## Using this template

This is a [template repository](../../generate) — click **Use this template**
above (or fork it) to get your own copy, then:

1. **Clone your copy** and install deps:
   ```bash
   uv sync
   ```
2. **Personalize `preferences.yaml`** — your job titles, locations, geo
   eligibility rules, and salary band. Fastest way:
   ```bash
   uv run python scripts/setup.py
   ```
   Answers a handful of questions and writes the file for you. (Using Claude
   Code? Run `/setup` instead and it'll interview you conversationally.) You
   can also hand-edit `preferences.yaml` directly — see the
   [Configuration](#configuration-preferencesyaml--configyaml) section below
   for what every field does.
3. **Set up secrets**: `cp .env.example .env` and fill it in locally; add the
   same four values as GitHub Actions repo secrets before you rely on the
   scheduled run (see [step 5](#5-github-actions-secrets) below).
4. **Create the Notion database** and **import your CV** — one-time setup,
   covered in detail in [Setup](#setup) below.
5. **Try it safely first**:
   ```bash
   uv run python -m src.main --dry-run
   ```
   This writes nothing and sends nothing — it just prints what the pipeline
   would do with your current `preferences.yaml`.
6. Once you're happy, push to GitHub and either wait for the daily schedule or
   trigger the `daily-job-search` workflow manually from the Actions tab.

The rest of this README covers each of those steps in depth, plus the
pipeline's internals if you want to modify the logic.

---

## How it fits together

```
acquire → max-age filter → classify → dedup (ids + collapse) → drop already-seen
  → score (master_match) → viability (drop/label) → rank + clamp → budget preflight
  → tailor (LLM, kept N only) → score (tailored_match) → Notion (row + CV page + answers)
  → rollover → ntfy
```

- **`data/master_cv.json`** is the single source of truth and the one input you
  cannot regenerate. The daily run reads only this file and never fetches your CV
  over the network during the daily run. `scripts/import_cv.py` builds it from a
  Notion page (one-time).
- The **viability filter runs before any LLM call**, so dead-end roles cost no
  tokens.
- Only **new** rows are ever tailored; existing rows are never re-tailored.

---

## Setup

### 0. Python (uv)

This project uses [uv](https://docs.astral.sh/uv/). Dependencies live in
`pyproject.toml` and are pinned in `uv.lock` (both committed).

```bash
uv sync                   # creates .venv and installs the locked deps
cp .env.example .env      # fill in real values for local runs
```

Run anything with `uv run …` (it uses the project venv automatically). You don't
activate a venv or `pip install` manually.

### 1. Notion database + integration

1. Create a new **database** (full-page) in Notion with **exactly these
   properties** (name and type must match):

   | Property | Type |
   |---|---|
   | Company | Title |
   | Job title | Text |
   | Country | Select |
   | Master match % | Number |
   | Tailored match % | Number |
   | Job type | Select |
   | Sponsorship | Select |
   | Relocation support | Select |
   | Viability | Select |
   | Fit note | Text |
   | Status | Select (New / Applying / Applied / Uninterested / Archived) |
   | Tailored CV | URL |
   | Has questions | Select (yes / no) |
   | Job ID | Text |
   | Source | Select |
   | Posted date | Date |
   | Date first seen | Date |
   | Seniority | Select |
   | Salary | Text |

   Select options are created automatically the first time a value appears, so
   you don't have to pre-fill them (except that you may want to add `Applied` and
   `Uninterested` yourself for manual use).

2. Create an **internal integration** at
   <https://www.notion.so/my-integrations>, copy its token (`NOTION_TOKEN`).
3. **Scope the token to this one database only:** open the database → `•••` →
   *Connections* → add your integration. Do **not** share your whole workspace
   with it.
4. Copy the database id from its URL (the 32-char id before `?v=`) into
   `NOTION_DATABASE_ID`.
5. Keep your default view filtered to `Status is New or Applying` — Applied,
   Uninterested, and Archived rows stay on record but drop out of sight.

**Exporting a tailored CV:** each job's tailored CV lives on its own child page,
linked from the row's `Tailored CV` column. Open it → `•••` → *Export* → PDF /
HTML / Markdown. Single-page export works on the Notion free plan.

### 2. LLM provider key

The tailoring/answer-drafting calls go through a plain OpenAI-compatible
client, so any provider that speaks that API works — DeepSeek, OpenAI,
Anthropic's OpenAI-compatible endpoint, Groq, a local vLLM/Ollama server, and
so on. Swapping providers is a `config.yaml` edit, never a code change; see
the commented examples in `config.yaml → llm`.

The template defaults to **DeepSeek** (cheap, and its `thinking` toggle is
wired in explicitly): create a key at <https://platform.deepseek.com> and set
`LLM_API_KEY`. Whichever provider you pick, the env var name is always
`LLM_API_KEY` — only `config.yaml`'s `llm.provider` / `llm.model` /
`llm.base_url` change.

### 3. Master CV (one-time)

Your resume lives as a normal Notion page — headings for sections, bullet lists
for highlights, whatever structure you already use. An LLM pass does the
structuring, not a rigid parser, so formatting doesn't need to be exact. The
runtime itself stays offline and deterministic: it only ever reads the
resulting `data/master_cv.json`, never Notion, during a daily run.

1. Write or paste your resume into a Notion page.
2. Share that page with the **same integration** from step 1: page → `•••` →
   *Connections* → add your integration. (It's the only extra grant beyond the
   jobs database — the integration still touches nothing else in your workspace.)
3. Copy the page id from its URL (the 32-char id, e.g.
   `https://notion.so/Your-Resume-<PAGE_ID>`).
4. Run:
   ```bash
   export CV_NOTION_PAGE_ID=<PAGE_ID>
   export NOTION_TOKEN=ntn_...
   export LLM_API_KEY=sk-...
   uv run python scripts/import_cv.py     # prints the JSON for review
   ```
5. Review the printed JSON, then **commit `data/master_cv.json` by hand.**

Re-run this whenever you update your resume. (`data/master_cv.example.json` shows
the schema if you'd rather write it directly.)

### 4. ntfy topic

Pick a topic name only you're likely to guess (set in `config.yaml →
notify.ntfy_topic`, or override with the `NTFY_TOPIC` env/secret) and
subscribe to `https://ntfy.sh/<your-topic>` in the ntfy app or web. You'll get
one push per run (and a high-priority push if a run fails). ntfy topics are a
public global namespace, not an account you own — treat the topic name as a
notification channel, not a secret.

### 5. GitHub Actions secrets

In the repo: *Settings → Secrets and variables → Actions → New repository secret*,
add all four:

- `LLM_API_KEY`
- `NOTION_TOKEN`
- `NOTION_DATABASE_ID`
- `NTFY_TOPIC`

Nothing secret is ever committed. `.env` is gitignored. The workflow injects these
as env vars. Leave GitHub's built-in failure email on — it's the backstop under
ntfy.

---

## Running

- **Locally, safe (writes nothing, sends nothing):**
  ```bash
  uv run python -m src.main --dry-run
  ```
  Prints the full plan: every kept role with its viability label, and **every
  dropped role with the reason**. Tailoring runs if `LLM_API_KEY` is present;
  otherwise it's skipped with a warning.

- **Locally, for real:**
  ```bash
  uv run python -m src.main
  ```

- **In CI:** runs daily at 04:00 UTC by default — edit the cron expression in
  `.github/workflows/daily.yml` to suit your timezone. Trigger manually from
  the Actions tab (`workflow_dispatch`).

---

## Development

```bash
uv sync --group dev        # installs pytest, ruff, pyright alongside the app deps
uv run pytest -q           # unit tests — deterministic modules only, no network/LLM calls
uv run ruff check .
uv run pyright
```

`.github/workflows/ci.yml` runs all three on every push to `main` and every PR
(separate from `daily.yml`, the scheduled pipeline run — CI needs no secrets).
Tests live in `tests/`, one file per `src/` module; `tests/conftest.py` has
`make_cfg`/`make_job` fixtures so a test only states the config/job fields it
cares about. Things intentionally **not** unit-tested: `acquire_boards` (live
JobSpy/network), `tailor.py`/`llm.py` (live LLM calls), `notion_store.py`/
`notify.py` (live Notion/ntfy calls) — exercise those with `--dry-run` or a
real run instead.

---

## Configuration (`preferences.yaml` + `config.yaml`)

Two committed YAML files, both no-secrets. **`preferences.yaml`** is the one file
you edit when you clone this repo — it holds *your* job-search criteria and
where you're searching from. **`config.yaml`** holds pipeline/ops settings you
rarely need to touch.

Generate `preferences.yaml` by answering a few questions instead of hand-editing
YAML: `uv run python scripts/setup.py`, or the `/setup` command if you're using
Claude Code.

`preferences.yaml`:

- `candidate.home_base` / `candidate.home_base_code` — free text, used only in
  human-readable drop-reason strings (e.g. "won't hire/sponsor from <home_base>").
  Purely cosmetic, doesn't drive any decision.
- `search.*` — titles, locations, count (10), `hard_max` (15 absolute ceiling),
  seniority, `max_age_days`, which boards to query.
- `geo.*` — `exclude_countries` (hard drop), `welcome_regions` (conceptual buckets
  the viability step labels against), `onsite_dead_regions`,
  `remote_home_signals` (words that make a remote role eligible from your home
  base even outside `welcome_regions`), `country_hints` (location text →
  country/region, used to classify each posting's geo — add an entry for any
  place you search that isn't already covered), and `unlisted_region`
  (`low` | `drop`) for regions in none of the lists. **Two layers:**
  `search.locations` is the concrete strings JobSpy actually queries;
  `geo.welcome_regions` is the conceptual buckets — keep every welcome region
  reachable from a `search.locations` entry (e.g. Middle East → United Arab
  Emirates), or it's never fetched.
- `salary.*` — USD band and a **manually refreshed** FX map.

`config.yaml`:

- `source.prefer_direct` — rank postings whose apply URL resolves to a company
  ATS (Greenhouse/Lever/Ashby) above plain board listings.
- `llm.*` — provider/model/base_url, token caps, and the budget guard
  (`rough_tokens_per_job`, `budget_ceiling_tokens`).
- `rollover.archive_new_after_days` — stale `New` rows move to `Archived` (never
  `Applying`).

Both accept a path override on the CLI: `--preferences` / `--config`.

---

## Viability rules (the "don't waste my time" gate)

Deterministic, reproducible, every decision carries a human-readable reason. The
model is never the judge here. All thresholds and lists below come from
`preferences.yaml`; the values checked into this template are a worked
*example* to illustrate the shape, not a real candidate's rules — run
`uv run python scripts/setup.py` (or the `/setup` Claude Code command) to
replace them with yours, or edit `preferences.yaml` by hand.

**Hard drops:** excluded country; onsite/hybrid in an `onsite_dead_regions`
region; remote roles locked to a place you can't work from; salary present and
outside the USD band (missing salary does *not* drop).

**Labels on survivors:**
- `high` — remote role eligible from your home base (`remote_home_signals`), or a
  welcome region with sponsorship stated `yes`.
- `medium` — welcome region, sponsorship undefined.
- `low` — welcome region with sponsorship `no`; an `onsite_dead_regions` remote
  role with a genuinely global scope; or an unlisted region when
  `geo.unlisted_region: low`.

Ranking: viability tier → source type (direct above board) → deterministic
match %. Only the top `search.count` survive to tailoring.

---

## Cost & safety guards

1. Explicit `max_tokens` on every LLM call.
2. Thinking mode off.
3. LLM only for new rows; existing rows never re-tailored.
4. Job count clamped to `search.hard_max` before the LLM loop.
5. Bounded retries (≤3), transient-only, capped backoff, never on 4xx.
6. Concurrency group + 10-minute job timeout.
7. Pre-flight budget check aborts the run if `rows × rough_per_job` exceeds the
   ceiling.
8. Token usage logged to stdout (visible in the Actions log).
9. Viability filter runs before tailoring — a dropped role never reaches an LLM
   call.

---

## Non-goals

No auto-apply, no form submission, no logging into boards. No pre-rendered PDFs
(the tailored CV is Markdown; render a PDF on demand from the Notion page only for
jobs you choose to apply to). No database beyond Notion, no frontend, no hosted
service.
