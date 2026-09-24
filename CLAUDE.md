# Jobber

A scheduled GitHub Actions pipeline (no server, no UI) that finds job
postings, filters/ranks them against one candidate's criteria, tailors their
CV per posting via an LLM, and writes results to a Notion database for manual
review. See `README.md` for the full setup flow and architecture.

## Hard invariants — don't break these

- **Never auto-applies.** The pipeline only ever writes to Notion; it never
  submits a form or logs into a job board.
- **Never commit secrets or personal data.** `.env` and `data/master_cv.json`
  (the user's real resume) are both gitignored — keep it that way. Secrets
  come from environment variables only, loaded via `python-dotenv` locally and
  injected by GitHub Actions in CI.
- **The daily run never touches the network for config or CV.** It reads only
  `data/master_cv.json`, `preferences.yaml`, and `config.yaml`. Rebuilding the
  CV from Notion (`scripts/import_cv.py`) is a separate, manual, one-time step.
- **Viability filtering runs before any LLM call.** Don't reorder the pipeline
  so a dropped role reaches `tailor.py`/`llm.py` — that's a cost/latency
  regression, not just a style issue.

## Config split

- `preferences.yaml` — the file a user (or the `/setup` command / `scripts/setup.py`
  wizard) edits: search titles/locations, geo eligibility rules, salary band.
- `config.yaml` — pipeline/ops settings (LLM provider/model, token budgets,
  rollover). Rarely touched by an end user.
- Both are committed and secret-free by design; `src/config.py` merges them
  (`config.yaml` wins on key collisions) plus `Secrets.from_env()`.
- LLM provider/model resolve through `src/llm.py`'s `resolve_llm`:
  `LLM_PROVIDER`/`LLM_MODEL` env vars → `config.yaml`'s `llm.provider`/`model` →
  `PROVIDER_DEFAULTS` (built-in per-provider fallback). `base_url` has no env
  override. Keep `PROVIDER_DEFAULTS` current — a stale hardcoded model id is
  worse than requiring explicit config.

## Pipeline order (`src/main.py`)

```
acquire → max-age filter → classify → dedup (ids + collapse) → drop already-seen
  → score (master_match) → viability (drop/label) → rank + clamp → budget preflight
  → tailor (LLM, kept N only) → score (tailored_match) → Notion (row + CV page + answers)
  → rollover → ntfy
```

## Testing

```bash
uv sync --group dev
uv run pytest -q      # unit tests: deterministic modules only
uv run ruff check .
uv run pyright
```

One test file per `src/` module. `tests/conftest.py` has `make_cfg`/`make_job`
fixtures. Intentionally **not** unit-tested — these need a live network/LLM
and are exercised via `--dry-run` or a real run instead:
`acquire_boards`, the actual LLM call in `tailor.py`/`llm.py`,
`notion_store.py`/`notify.py`. The exception within `llm.py` is
`resolve_llm` — pure, no network — which has its own `tests/test_llm.py`.

Run `uv run python -m src.main --dry-run` to see the full plan (every kept
role plus every dropped role with its reason) without writing to Notion or
sending a notification.

## Onboarding a fresh fork

This repo is a template. A person who forks it needs `preferences.yaml`
personalized (their titles/locations/geo rules/salary band), a `.env` filled
from `.env.example`, and `data/master_cv.json` built via
`scripts/import_cv.py`. The `/setup` slash command (`.claude/commands/setup.md`)
handles the `preferences.yaml` part conversationally — prefer pointing a user
at that (or the equivalent `uv run python scripts/setup.py` for non-Claude-Code
use) over hand-editing the YAML for them.
