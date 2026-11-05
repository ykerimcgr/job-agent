# Reusable AI Job Agent (UK + Istanbul)

This project searches job listings in one or more markets (by default the UK
and Istanbul), applies deterministic filters, scores
the remaining jobs with OpenAI, generates tailored application documents, and
sends the best new opportunities by email.

Each repository copy represents one candidate. A new candidate changes only:

1. `profile/master_cv.tex`
2. `profile/user_config.json`
3. The private service credentials used locally or in GitHub Actions

Candidate details, target roles, reject rules, score thresholds, document
preferences, and scheduling are not hardcoded in Python.

## Pipeline

```text
LaTeX CV + user_config.json
          ↓
JobSpy search, per market (UK, Istanbul, ...)
          ↓
Dedup → hard filters (incl. years of experience) → pre-score
          ↓
One structured OpenAI assessment per job → deterministic 0-100 rate
          ↓
Top jobs per market
          ↓
Tailored CV (master CV as template) + cover letter, unsupported claims reverted
          ↓
Gmail report + Supabase history
```

The agent prepares application material but never submits an application.

## 1. Candidate files

Copy the example configuration:

```bash
cp profile/user_config.example.json profile/user_config.json
```

Replace `profile/master_cv.tex` with the candidate's real LaTeX CV, then edit
`profile/user_config.json`.

Both real candidate files are ignored by Git. Only
`profile/user_config.example.json` is committed.

### Configuration sections

- `candidate.contact_overrides`: optional corrections for values extracted
  from the CV. Empty strings keep the extracted value.
- `search.target_roles`: roles the candidate wants.
- `search.level_terms`: terms such as `Graduate`, `Junior`, or `Entry-Level`.
- `search.extra_queries`: full additional JobSpy queries for every market.
- `search.sources`, `hours_old`, and `results_per_query`: search behaviour.
- `markets`: one entry per place to search. Each has its JobSpy
  `search_location` and `country_indeed`, `location_keywords` (with
  `strict_location: true` only listings naming one of them, the country, or
  remote are kept), optional `level_terms`, and `extra_*` lists that are added
  to the shared role/level/query/reject lists (Turkish titles for Istanbul).
  It also sets the CV/cover-letter `contact_overrides`, whether the
  right-to-work line is shown, the cover-letter tone, and `scoring_notes`
  passed to the AI (for example work authorisation facts). A config without
  `markets` searches the UK only.
- `filters.title_hard_reject`: phrases that immediately reject a title.
- `filters.title_domain_reject`: off-target fields (finance, developer...) rejected in a title unless it also matches `filters.title_domain_exceptions` (AI, automation, programme...).
- `filters.description_hard_reject`: phrases that immediately reject a
  description.
- `filters.description_hard_reject_regex`: advanced regular-expression hard
  rejects, including apprenticeships.
- `filters.soft_reject` and `soft_reject_regex`: risks that reduce the
  deterministic pre-score.
- `filters.skill_keywords`: skills that increase the pre-score.
- `filters.max_years_experience`: listings that ask for more years (English or
  Turkish wording) are rejected before any AI call.
- `filters.advanced`: default score weights and penalties. Most candidates do
  not need to change these.
- `selection`: AI score thresholds, candidate limit, and Top-N size, applied
  per market.
- `documents`: document generation and language (English for every market).
- `notifications`: email enablement and an optional recipient override.
- `schedule`: London timezone, active days, hours, and run interval (default
  every 3 hours: 09:00, 12:00, 15:00).

A market with a `queries` list searches exactly those queries. Otherwise, for
each target role, the search layer generates:

- every `level term + role` combination;
- the role without a level prefix;
- every entry in `extra_queries`.

Duplicate queries are removed case-insensitively.

## 2. Supabase

Each candidate should use their own Supabase project.

Run [supabase/schema.sql](supabase/schema.sql) once in the Supabase SQL Editor.
It creates:

- `profile_cache`
- `job_cache`
- `emailed_jobs`

The tables have Row Level Security enabled and are granted only to the
server-side `service_role`. Use a Supabase secret/service-role key in the
backend environment; never expose it in client-side code or commit it.

The AI cache key includes the job, candidate profile, market, target roles and
levels, model, and prompt version. Score thresholds are applied after the
cache, so changing them does not throw away cached assessments.

A job is identified by its title + company + market (see `filter/identity.py`);
the same id is used for dedup, the archive and `emailed_jobs`, so a listing that
reappears with a new URL, or on another site, is not emailed twice.

## 3. Local setup

Requirements:

- Python 3.12
- `pdflatex` for PDF output
- A configured OpenAI API key
- Gmail SMTP credentials
- Supabase URL and server-side secret/service-role key

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Create an ignored `.env` file:

```dotenv
OPENAI_API_KEY=
EMAIL_ADDRESS=
EMAIL_PASSWORD=
EMAIL_TO=
SUPABASE_URL=
SUPABASE_KEY=
```

The existing legacy variable name `OPEN_AI_SECRET_KEY` remains supported, but
new installations should use `OPENAI_API_KEY`.

Run immediately:

```bash
python main.py
```

Local execution does not enforce the schedule by default. Missing config, CV,
or required environment variables are reported before search or AI calls.

## 4. GitHub Actions

The workflow wakes every hour; scheduled runs then follow the timezone, active
days, start/end times, and interval in `profile/user_config.json`.

After changing `profile/user_config.json` (for example to add the Istanbul
market), update the `USER_CONFIG_JSON_B64` secret: CI only sees the secret.

The repository is public, so generated CVs are not uploaded as workflow
artifacts; they arrive by email.
`workflow_dispatch` always runs immediately.

Create these GitHub repository secrets:

| Secret | Purpose |
| --- | --- |
| `MASTER_CV_TEX_B64` | Base64-encoded `profile/master_cv.tex` |
| `USER_CONFIG_JSON_B64` | Base64-encoded `profile/user_config.json` |
| `OPENAI_API_KEY` | OpenAI API credential |
| `EMAIL_ADDRESS` | Gmail sender |
| `EMAIL_PASSWORD` | Gmail app password |
| `EMAIL_TO` | Optional report recipient |
| `SUPABASE_URL` | Candidate's Supabase project URL |
| `SUPABASE_KEY` | Server-side Supabase secret/service-role key |

For compatibility, the workflow also accepts the existing
`OPEN_AI_SECRET_KEY` GitHub secret when `OPENAI_API_KEY` has not yet been
created.

Generate the two file values without committing candidate data:

```bash
base64 < profile/master_cv.tex | tr -d '\n'
base64 < profile/user_config.json | tr -d '\n'
```

Paste each result into its corresponding GitHub secret.

## Outputs

```text
outputs/
├── Jobspy/
│   ├── UK_raw.json / UK_filtered.json / UK_rejected.json
│   └── TR_raw.json / TR_filtered.json / TR_rejected.json
├── UK/ and TR/
│   ├── candidates.json
│   └── scored.json
├── applications/
│   ├── UK/
│   └── TR/
├── history/            (incl. run_summary_<time>.json with counts per market)
├── top_jobs_current_run.json
├── top_jobs.json
└── generated_documents.json
```

The canonical selected-job shape is:

```json
{
  "UK": [],
  "TR": []
}
```

Each entry in `generated_documents.json` lists `removed_entries` (CV entries
dropped as irrelevant for that job) and `grounding_fixes` (reworded text that
was reverted because it named a number, tool or unmet skill that the master
CV does not contain).

No email or document-generation call is made when the current run has no new
suitable jobs. A failed SMTP send does not mark jobs as emailed.

## Tests

The tests mock JobSpy, OpenAI, Supabase, SMTP, and pipeline side effects:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

They cover configuration validation, query generation, job identity and dedup
(real Indeed/LinkedIn URL shapes), hard and soft filters, UK and Istanbul
location handling, years-of-experience extraction, the deterministic score,
CV template rendering, grounding checks, empty runs, SMTP failure, and London
scheduling.
