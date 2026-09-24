---
description: Interview the user and personalize this template's preferences.yaml
---

Walk the user through personalizing this fork of the Jobber template. Do this
conversationally (use AskUserQuestion for the discrete choices, plain text for
free-form ones) rather than shelling out to `scripts/setup.py` — that script
exists for non-Claude-Code use; here you can just ask and write the file
directly with fewer round trips.

Ask for, in this order (skip a question if the user already told you the
answer earlier in the conversation):

1. **Home city, country, and a region label** for remote-eligibility matching
   (e.g. "Lagos, Nigeria, Africa" or "São Paulo, Brazil, LatAm"). Required —
   everything else in `geo` keys off this.
2. **Target job titles** (a short list, e.g. "Senior Backend Engineer, Staff
   Backend Engineer").
3. **Locations to search** — concrete JobSpy query strings (countries/cities,
   or "Remote"). These must line up with the welcome regions in step 5: every
   welcome region needs at least one matching entry here.
4. **Seniority levels**, **boards to query** (indeed/linkedin/glassdoor/google),
   and **max posting age in days** — offer the defaults from
   `preferences.yaml`'s comments and accept a quick "sounds good."
5. **Geo rules**: countries to hard-exclude, welcome regions (conceptual
   buckets like UK/Ireland/EU/Australia/Middle East/Singapore/India/Canada/US),
   words that make a remote role eligible from their home region beyond
   "worldwide/global/anywhere", and regions where onsite/hybrid is a hard drop
   (e.g. US, Canada) — only if applicable, most people leave this empty.
6. **Salary band** in USD (min/max).

Then:

- Read the current `preferences.yaml` for the exact schema/comment style to
  preserve (don't invent new keys or drop the explanatory comments).
- Write the new `preferences.yaml` with the user's answers, keeping every
  section and comment from the original, updating `geo.country_hints` to
  include their home city/country plus entries for each welcome region (see
  the existing table for the country -> region mapping convention).
- Remind them what's still manual, in one short list:
  - `cp .env.example .env` and fill in `DEEPSEEK_API_KEY` / `NOTION_TOKEN` /
    `NOTION_DATABASE_ID` (README has the Notion database setup steps).
  - Building `data/master_cv.json` via `scripts/import_cv.py` from a Notion
    page holding their resume.
  - Adding the four secrets to GitHub Actions (Settings → Secrets and
    variables → Actions) before the scheduled workflow can run.
- Do not run the pipeline, touch git, or fill in secrets yourself — this
  command only edits `preferences.yaml`.
