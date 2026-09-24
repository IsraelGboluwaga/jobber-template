# Jobber — daily job-search pipeline

If this saves you time, consider leaving a star on the repo — it helps other
job-seekers find it.

A small **scheduled pipeline** — no server, no web app, no UI. Once a day,
GitHub Actions runs it and it:

1. **Searches** LinkedIn, Indeed, Glassdoor, and Google Jobs (via
   JobSpy) for your target titles and
   locations.
2. **Filters and ranks** the results: drops duplicates, roles you've already
   seen, and roles you can't realistically get (location, sponsorship,
   salary), then keeps the best ~10.
3. **Tailors your CV** to each kept posting with an LLM — DeepSeek, OpenAI,
   and Anthropic work out of the box, and any other OpenAI-compatible
   endpoint works with one config line.
4. **Drafts answers** to the posting's application questions, if it has any.
5. **Writes one row per job** to a Notion database, with the tailored CV on a
   linked page and any drafted answers in the row's body.
6. **Sends one push notification** via [ntfy](https://ntfy.sh) when it's done
   (or if it fails).

You review in Notion and apply yourself. Three guarantees:

- **It never applies for you.** It only writes to Notion — no form
  submission, no logging into job boards.
- **It never invents experience.** The LLM may reorder, reweight, and
  rephrase what's in your master CV, but is instructed never to add
  employers, titles, dates, metrics, or skills you don't have.
- **Your API keys are never committed.** They live in `.env` locally and in
  GitHub Actions secrets in CI. (Your CV *is* committed — so keep your copy
  of the repo private.)

To stop everything, disable the `daily-job-search` workflow.

---

## Quick start

This is a [template repository](../../generate) — click **Use this template**
to get your own copy, and **make it private**: you'll commit your real CV to
it. (A fork of a public repo can't be made private.) Then:

1. **Install** — `uv sync` ([details](#0-python-uv)).
2. **Personalize `preferences.yaml`** — your titles, locations, geo rules, and
   salary band:
   ```bash
   uv run python scripts/setup.py
   ```
   It asks a handful of questions and writes the file. In Claude Code, run
   `/setup` instead for a conversational version. Or hand-edit the file —
   see [Configuration](#configuration).
3. **Create the Notion database** and integration ([step 1](#1-notion-database--integration)).
4. **Get an LLM API key** ([step 2](#2-llm-provider-key)).
5. **Fill in `.env`** — `cp .env.example .env`, then add your keys
   ([reference](#environment-variables)).
6. **Import your CV** into `data/master_cv.json` ([step 3](#3-master-cv)).
7. **Pick an ntfy topic** ([step 4](#4-ntfy-topic)).
8. **Try it safely** — writes nothing, sends nothing, just prints the plan:
   ```bash
   uv run python -m src.main --dry-run
   ```
9. **Add your GitHub Actions secrets** ([step 5](#5-github-actions-secrets)),
   push, and either wait for the daily schedule or run the `daily-job-search`
   workflow manually from the Actions tab.

---

## How it works

```
acquire → max-age filter → classify → dedup (ids + collapse) → drop already-seen
  → score (master_match) → viability (drop/label) → rank + clamp → budget preflight
  → tailor (LLM, kept N only) → score (tailored_match) → Notion (row + CV page + answers)
  → rollover → ntfy
```

- **Everything before "tailor" is deterministic** — plain rules, no LLM. Roles
  that fail your viability rules are dropped before any LLM call, so they cost
  no tokens.
- **Only new postings are tailored.** Anything already in your Notion
  database (in any status) is skipped, so rows are never re-tailored.
- **`data/master_cv.json` is the one input you can't regenerate from the
  repo.** The daily run reads your CV from this local file only — it never
  fetches it over the network. `scripts/import_cv.py` builds it once from a
  Notion page.
- **Match %** is the share of the job description's skill terms that appear
  in your CV — deterministic, no LLM — `Master match %` for your master CV (used for ranking),
  `Tailored match %` for the tailored one.
- **Rollover:** `New` rows older than 14 days (configurable) are moved to
  `Archived` so your working view stays short. `Applying` rows are never
  touched.

---

## Setup

### 0. Python (uv)

This project uses [uv](https://docs.astral.sh/uv/). Dependencies are declared
in `pyproject.toml` and pinned in `uv.lock`.

```bash
uv sync                   # creates .venv and installs the locked deps
cp .env.example .env      # then fill in real values for local runs
```

Run everything with `uv run …` — no need to activate a venv or `pip install`.

### 1. Notion database + integration

1. Create a new full-page **database** in Notion with **exactly these
   properties** (names and types must match):

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
   | Status | Select |
   | Tailored CV | URL |
   | Has questions | Select |
   | Job ID | Text |
   | Source | Select |
   | Posted date | Date |
   | Date first seen | Date |
   | Seniority | Select |
   | Salary | Text |

   You don't need to pre-create select options — Notion adds them the first
   time the pipeline writes a value. The pipeline itself only uses the
   `Status` values `New` and `Archived`; add `Applying`, `Applied`, and
   `Uninterested` yourself to track your progress.

2. Create an **internal integration** at
   <https://www.notion.so/my-integrations> and copy its token — this is
   `NOTION_TOKEN`.
3. **Give the integration access to this database only:** open the database →
   `•••` → *Connections* → add your integration. Don't share your whole
   workspace with it.
4. Copy the database id from its URL (the 32-character id before `?v=`) —
   this is `NOTION_DATABASE_ID`.
5. *(Recommended)* Filter your default view to `Status is New or Applying`, so
   Applied, Uninterested, and Archived rows stay on record but out of sight.

The `Job title` cell links to the posting. Each job's tailored CV is on its
own page, linked from the `Tailored CV` column. To get a PDF, open that page →
`•••` → *Export* → PDF (works on Notion's free plan).

### 2. LLM provider key

LLM calls go through a standard OpenAI-compatible client, so switching
providers never needs a code change. The API key always goes in
**`LLM_API_KEY`**, whichever provider you use.

The default provider is **DeepSeek** (inexpensive; its "thinking" mode is
switched off to keep calls cheap). Create a key at
<https://platform.deepseek.com> and you're done.

**To use a different provider or model**, the settings are resolved in this
order (first match wins):

1. The `LLM_PROVIDER` / `LLM_MODEL` environment variables — in `.env`
   locally, or as GitHub Actions repo **Variables** (not Secrets; they aren't
   sensitive). This is the easiest way — no file edits, no commits.
2. `llm.provider` / `llm.model` in `config.yaml`.
3. A built-in default model for `deepseek`, `openai`, and `anthropic` — see
   `PROVIDER_DEFAULTS` in `src/llm.py` for the current values.

For example, to try Anthropic, set `LLM_PROVIDER=anthropic` and put your
Anthropic key in `LLM_API_KEY`.

Two things to know:

- **Other providers** (Groq, a local vLLM/Ollama server, …) have no built-in
  default, so set `llm.base_url` (and `llm.model`) in `config.yaml`.
  `base_url` can't be set from an environment variable.
- **`config.yaml`'s `llm.model` / `llm.base_url` only apply to the provider
  `config.yaml` names** (DeepSeek if it names none). If `LLM_PROVIDER` picks a
  different provider, those values are ignored, so a DeepSeek model name is
  never sent to Anthropic.

> Anthropic describes its OpenAI-compatible endpoint as intended for testing
> and comparison rather than production, and it doesn't support prompt
> caching. It works fine here — just worth knowing before you rely on it for
> the unattended daily run.

### 3. Master CV

Your resume lives in an ordinary Notion page — headings, bullets, whatever
structure you already use. A one-time LLM pass turns it into structured JSON,
so the formatting doesn't need to be exact.

1. Write or paste your resume into a Notion page.
2. Share it with the **same integration** from step 1: page → `•••` →
   *Connections* → add your integration. This page and the jobs database are
   the only things the integration can see.
3. Copy the page id from its URL (the 32-character id at the end of
   `https://notion.so/Your-Resume-<PAGE_ID>`) into `CV_NOTION_PAGE_ID` in
   `.env`. `NOTION_TOKEN` and `LLM_API_KEY` must be set there too.
4. Run the import:
   ```bash
   uv run python scripts/import_cv.py       # or: --page-id <PAGE_ID>
   ```
   This writes `data/master_cv.json` and prints it — **read it through** to
   check nothing was lost or garbled.
5. Commit it — the scheduled run on GitHub Actions reads it from the repo:
   ```bash
   git add data/master_cv.json && git commit -m "Update master CV"
   ```

This is your real resume, so **only commit it to a private repo**. Repeat
steps 4–5 whenever you update your resume. If you'd rather write the JSON by
hand, `data/master_cv.example.json` shows the schema.

### 4. ntfy topic

[ntfy](https://ntfy.sh) topics are a public, shared namespace — anyone who
knows a topic name can read it. So:

1. Pick an obscure topic name (e.g. `jobber-<random-string>`) and treat it as
   a notification channel, not a secret.
2. Set it as `notify.ntfy_topic` in `config.yaml`, or as `NTFY_TOPIC` in
   `.env` / GitHub Actions secrets. **Change the committed placeholder** —
   everyone who forgets shares it.
3. Subscribe to it in the ntfy app, or at `https://ntfy.sh/<your-topic>`.

You'll get one push per run, and a high-priority push if a run fails.
Dry runs never notify.

### 5. GitHub Actions secrets

In your repo, go to *Settings → Secrets and variables → Actions*.

**Secrets** tab:

- `LLM_API_KEY`, `NOTION_TOKEN`, `NOTION_DATABASE_ID` — required.
- `NTFY_TOPIC` — only if you didn't set your topic in `config.yaml`.

**Variables** tab (optional):

- `LLM_PROVIDER` / `LLM_MODEL` — to switch LLM provider or model without a
  commit.

The workflow passes these to the run as environment variables. Also leave
GitHub's built-in "workflow failed" email turned on as a backup for ntfy.

---

## Environment variables

For local runs, all of these go in `.env` (`cp .env.example .env`). For GitHub
Actions, see [step 5](#5-github-actions-secrets).

| Variable | Required? | In GitHub Actions | Purpose |
|---|---|---|---|
| `LLM_API_KEY` | Yes | Secret | API key for your LLM provider — see [step 2](#2-llm-provider-key). |
| `LLM_PROVIDER` | No | Variable | LLM provider (default: `deepseek`). |
| `LLM_MODEL` | No | Variable | Model (default: the provider's built-in default). |
| `NOTION_TOKEN` | Yes | Secret | Notion integration token, with access to the jobs database only. |
| `NOTION_DATABASE_ID` | Yes | Secret | The jobs database's id, from its URL. |
| `NTFY_TOPIC` | No | Secret | Overrides `config.yaml`'s `notify.ntfy_topic`. |
| `CV_NOTION_PAGE_ID` | Only for `scripts/import_cv.py` | Not needed | Id of the Notion page holding your resume. |

---

## Running

**Dry run** — writes nothing to Notion, sends no notification:

```bash
uv run python -m src.main --dry-run
```

Prints the full plan: every kept role with its viability label, and **every
dropped role with the reason it was dropped**. If `LLM_API_KEY` is set, it
also runs the tailoring (and spends tokens) so you can see the output;
otherwise tailoring is skipped with a warning. If Notion credentials are set,
it reads the database to skip roles you've already seen.

**Real run, locally:**

```bash
uv run python -m src.main
```

**On GitHub Actions:** `.github/workflows/daily.yml` runs daily at 04:00 UTC —
edit its `cron` line to suit your timezone. To run it on demand, open the
Actions tab → `daily-job-search` → *Run workflow*.

Both commands accept `--preferences <path>` and `--config <path>` to use
files other than the defaults.

---

## Configuration

There are two committed YAML files. Neither holds secrets.

- **`preferences.yaml`** — *your* job-search criteria. This is the file you
  personalize (via `scripts/setup.py`, `/setup`, or by hand). The values
  committed in the template are a worked example, not a real candidate's.
- **`config.yaml`** — pipeline and ops settings. Most people never need to
  change it apart from the ntfy topic.

If both files set the same top-level key, `config.yaml` wins.

### `preferences.yaml`

- **`candidate.home_base` / `home_base_code`** — where you live. Only appears
  in the text of drop reasons (e.g. "won't hire/sponsor from XX"); it doesn't
  affect any decision.
- **`search.*`**
  - `titles`, `locations` — what JobSpy searches for. Every location is
    searched for every title.
  - `count` — how many roles to tailor and write per run (default 10).
    `hard_max` — an absolute cap enforced in code (default 15).
  - `seniority`, `max_age_days` (skip older postings), `boards` (which job
    boards to query), `country_indeed` (which regional Indeed/Glassdoor site
    to use for non-remote searches).
- **`geo.*`** — the inputs to the [viability rules](#viability-rules):
  - `exclude_countries` — always dropped.
  - `welcome_regions` — regions you're happy to work in (e.g. `UK`, `EU`).
  - `onsite_dead_regions` — regions where onsite/hybrid roles are dropped
    (e.g. because they won't sponsor you).
  - `remote_home_signals` — words that make a remote role count as open to
    you (e.g. `worldwide`, or your country or continent).
  - `unlisted_region` — what to do with a region in none of the lists:
    `low` (keep, rank last) or `drop`.
  - `hard_sponsorship_filter` — if `true`, drop any role that explicitly says
    it won't sponsor visas.
  - `country_hints` — maps location text (e.g. `berlin`) to a country and
    region. Add entries for your home and for anywhere you search that isn't
    already covered.
- **`salary.*`** — your band in USD (`min_usd`, `max_usd`), plus an `fx` table
  of conversion rates to USD. **Update `fx` yourself** — it's never fetched.

> **Keep `search.locations` and `geo.welcome_regions` in sync.**
> `search.locations` are the literal strings sent to the job boards;
> `welcome_regions` are the buckets used to judge results. A welcome region
> with no matching search location is never searched — e.g. to welcome
> `Middle East`, add `United Arab Emirates` (or similar) to `search.locations`.

### `config.yaml`

- **`source.prefer_direct`** — rank postings whose apply link goes to a
  company's own applicant-tracking system (Greenhouse, Lever, Ashby, Workday)
  above plain job-board listings.
- **`llm.*`** — `provider` / `model` / `base_url` (see
  [step 2](#2-llm-provider-key) for how they're resolved), `thinking`,
  per-call token caps (`max_tokens_cv`, `max_tokens_answers`), and the budget
  guard (`rough_tokens_per_job`, `budget_ceiling_tokens`).
- **`rollover.archive_new_after_days`** — how long a `New` row stays before
  it's moved to `Archived` (default 14). `Applying` rows are never touched.
- **`notify.ntfy_topic`** — your ntfy topic ([step 4](#4-ntfy-topic)).

---

## Viability rules

This is the "don't waste my time" filter. It runs before any LLM call, uses
fixed rules (never the LLM), and every decision comes with a human-readable
reason — run `--dry-run` to see them. All the lists below come from
`preferences.yaml`.

**Dropped:**

- the country is in `exclude_countries`;
- an onsite or hybrid role in an `onsite_dead_regions` region;
- a remote role restricted to a country or region you can't work from;
- a salary is listed and falls outside your USD band (no salary listed is
  *not* dropped);
- the role says it won't sponsor, and `hard_sponsorship_filter` is on;
- the region is in none of your lists, and `unlisted_region: drop`.

**Everything else gets a label:**

| Label | When |
|---|---|
| `high` | A remote role open to you — worldwide or EMEA scope, or matching `remote_home_signals`. Or a welcome region that says it sponsors. |
| `medium` | A welcome region that doesn't mention sponsorship. |
| `low` | A welcome region that says it won't sponsor; a worldwide-remote role based in an `onsite_dead_regions` region; or an unlisted region with `unlisted_region: low`. |

**Ranking:** label (`high` first) → direct company postings before job-board
listings (if `prefer_direct`) → master match %. The top `search.count` roles
are tailored and written to Notion.

---

## Cost & safety guards

1. Every LLM call has an explicit `max_tokens` cap.
2. DeepSeek's thinking mode is turned off (`llm.thinking: false`).
3. Only new rows are tailored; existing rows are never re-tailored.
4. The job count is capped at `search.hard_max` before any LLM call.
5. Failed LLM calls get at most 3 attempts, with capped backoff — and only
   for rate limits, server errors, and timeouts. Other 4xx errors are never
   retried.
6. On GitHub Actions, a new run cancels any still-running one, and every run
   is killed after 10 minutes.
7. A pre-flight check aborts the run before any LLM call if
   `roles × rough_tokens_per_job` exceeds `budget_ceiling_tokens`.
8. Token usage is printed at the end of every run (visible in the Actions
   log).
9. Viability filtering runs before tailoring — a dropped role never reaches
   the LLM.

---

## Development

```bash
uv sync --group dev        # adds pytest, ruff, and pyright
uv run pytest -q           # unit tests — no network or LLM calls
uv run ruff check .
uv run pyright
```

`.github/workflows/ci.yml` runs all three on every push to `main` and on every
pull request. It's separate from the scheduled `daily.yml` and needs no
secrets.

Tests live in `tests/`, one file per `src/` module. `tests/conftest.py`
provides `make_cfg` / `make_job` fixtures, so each test only sets the fields
it cares about. Code that needs a live service is deliberately **not**
unit-tested — test it with `--dry-run` or a real run instead:

- `acquire_boards` — live JobSpy/network;
- the LLM calls in `tailor.py` / `llm.py` — `resolve_llm` is the exception,
  covered by `tests/test_llm.py`;
- `notion_store.py` / `notify.py` — live Notion/ntfy.

---

## Non-goals

- No auto-apply, no form submission, no logging into job boards.
- No pre-rendered PDFs — the tailored CV is Markdown in Notion; export a PDF
  only for the jobs you actually apply to.
- No database other than Notion, no frontend, no hosted service.
