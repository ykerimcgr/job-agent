# AI-Powered Job Application Automation System

An end-to-end AI system that finds relevant jobs in the UK and Istanbul, decides
which ones are worth applying to, and prepares an ATS-friendly CV and cover
letter for each, delivered by email.

## Contact

For any inquiries or collaboration opportunities:

- :briefcase: [LinkedIn](https://www.linkedin.com/in/yusuf-kerim-ciger/)
- :mailbox_with_mail: [Email](mailto:ykerimciger@gmail.com)

## Overview

This project is not just a job scraper. It automates a real job-search
workflow, from discovery to a ready-to-send application:

- Finds job listings in several markets (UK, Istanbul, Kocaeli and remote
  Turkey by default)
- Filters out senior, off-target, temporary and duplicate roles before any AI
  call
- Uses an LLM to check each remaining job against the candidate's real
  experience and turns that into a deterministic 0-100 "applicable rate"
- Tailors the candidate's own LaTeX CV and writes a cover letter for each
  selected job, without inventing skills or results
- Emails the best new opportunities with the documents attached, and never
  emails the same job twice

The agent prepares application material but never submits an application.

## Features

- **Multi-market search** with [JobSpy](https://github.com/speedyapply/JobSpy)
  (LinkedIn and Indeed), with per-market queries, sources, search window and
  extra search locations (for example an industrial zone or remote-only)
- **Turkish and English rules**: Turkish titles, seniority words and
  "N yıl deneyim" requirements are understood alongside English ones
- **Deterministic pre-filter**: senior-title, off-field, years-of-experience,
  location and apprenticeship rejects, with exceptions for graduate and
  assistant titles ("New Graduates 2027: IT Manager", "Yönetici Yardımcısı")
- **Evidence-based AI scoring**: the model lists the job's requirements and
  marks each as met, partial or missing from the candidate's profile; the
  score is computed from that evidence, not from the model's opinion of a number
- **Grounded CV tailoring**: entries and bullets can be dropped, reordered,
  merged and reworded, but a skill, tool or number only appears if the master
  CV already shows it; anything else is reverted automatically
- **ATS-friendly output**: clean PDF text (no icon glyphs or split keywords),
  a job-specific summary and job-first skill ordering
- **Caching** of profiles and AI assessments in Supabase to cut API cost
- **Scheduled runs** with GitHub Actions on a London working-hours schedule

## Architecture

```text
LaTeX CV + user_config.json
          ↓
JobSpy search per market and search location (UK, Istanbul, Kocaeli, remote TR)
          ↓
Dedup → hard filters (title, field, years, location) → keyword pre-score
          ↓
One structured OpenAI assessment per job → deterministic 0-100 rate
          ↓
Top jobs per market (already-emailed jobs removed)
          ↓
Tailored CV (master CV as template) + cover letter, unsupported claims reverted
          ↓
Gmail report + Supabase history
```

## Tech Stack

- Python 3.12, pydantic
- OpenAI API (Structured Outputs): `gpt-6-luna` for scoring and CV parsing,
  `gpt-6.1-terra` for CV and cover-letter writing
- JobSpy for job scraping
- LaTeX (`moderncv` or a plain `article` CV) for documents
- Supabase for caching and emailed-job history
- GitHub Actions for scheduling

## Example workflow

1. The agent searches each market with its own queries and window (Istanbul
   looks back 14 days, because graduate programmes stay open for weeks).
2. Duplicates, senior, off-field, temporary and too-experienced roles are
   removed; the rest are ranked by a keyword pre-score.
3. Up to the market's AI limit (40 for the UK, 140 for Turkey), each job is
   assessed and given an applicable rate.
4. Jobs scoring 60 or more are selected, best first, up to 10 per market.
5. A tailored CV and cover letter are generated for each and emailed.

## Output

For each selected job the system generates:

- Tailored CV (`.tex` and `.pdf`)
- Tailored cover letter (`.tex` and `.pdf`)

```text
outputs/applications/
└── TR/
    └── UPS_Industrial_Engineering_Specialist/
        ├── Yusuf_Ciger_CV_UPS_Industrial_Engineering_Specialist.pdf
        └── Yusuf_Ciger_Cover_Letter_UPS_Industrial_Engineering_Specialist.pdf
```

## Why this project?

Job searching is repetitive, time-consuming and inefficient. This project shows
how AI can be used to:

- Automate decision-making with evidence instead of guesses
- Improve application quality while staying truthful
- Reduce manual effort
- Build reliable pipelines instead of simple scripts

---

# Setup guide

Each repository copy represents one candidate. A new candidate changes only:

1. `profile/master_cv.tex`
2. `profile/user_config.json`
3. The private service credentials used locally or in GitHub Actions

Candidate details, target roles, reject rules, score thresholds, document
preferences and scheduling are not hardcoded in Python.

## 1. Candidate files

Copy the example configuration:

```bash
cp profile/user_config.example.json profile/user_config.json
```

Replace `profile/master_cv.tex` with the candidate's real LaTeX CV, then edit
`profile/user_config.json`. Both real candidate files are ignored by Git; only
`profile/user_config.example.json` is committed.

### The master CV

The CV is used as a template: the AI never writes LaTeX, it only says which
entries and bullets to keep, in what order, and how to reword them. Two layouts
are understood:

- `moderncv`: each job or project is an `\item{\cventry{dates}{title}{organisation}{place}{}{...}}`,
  the profile statement is the `\small{...}` paragraph after `\makecvtitle`, and
  `\name`, `\address`, `\phone` and `\email` are replaced per market.
- plain `article`: entries use a custom `\entry{...}` command and the summary
  is the text under a "Summary" section.

Experience and project entries can be dropped for a job; education cannot.
Sections named Languages, References or Additional Information are never
edited. Skill lists (for example Core Competencies) may only name skills that
an experience, project or education entry plainly shows. Contact icons are
switched off in generated CVs so they do not leak stray characters into the
PDF text an ATS reads.

### Configuration sections

- `candidate.contact_overrides`: optional corrections for values extracted
  from the CV. Empty strings keep the extracted value.
- `search.target_roles`: roles the candidate wants.
- `search.level_terms`: terms such as `Graduate`, `Junior` or `Entry-Level`.
- `search.extra_queries`: full additional JobSpy queries for every market.
- `search.sources`, `hours_old` and `results_per_query`: default search
  behaviour.
- `markets`: one entry per place to search. Each has its JobSpy
  `search_location` and `country_indeed`, and `location_keywords` (with
  `strict_location: true`, only listings naming one of them, the country, or
  remote are kept). Optional per-market settings:
  - `queries`: exactly these JobSpy queries, instead of role x level expansion.
  - `sources`, `results_per_query`, `hours_old`: override the search defaults
    (for example a 14-day window for Istanbul).
  - `extra_searches`: further places to run the search, each with a
    `location`, an optional `remote: true`, and optional `queries` of its own.
    Remote listings anywhere in the market's country are accepted.
  - `ai_candidate_limit`: how many filtered jobs the AI scores in this market.
  - `level_terms` and `extra_*` lists, added to the shared role, level, query
    and reject lists (Turkish titles for Istanbul).
  - `contact_overrides`, `include_right_to_work`, `cover_letter_style`,
    `cv_max_pages` (1 or 2) and `scoring_notes` (passed to the AI, for example
    work authorisation facts and which roles count as on-target).

  A config without `markets` searches the UK only.
- `filters.title_hard_reject`: phrases that immediately reject a title.
- `filters.title_hard_reject_exceptions`: words that cancel a title reject
  (for example `graduate`, `yardımcısı`), so the AI judges the real level.
- `filters.title_domain_reject`: off-target fields (finance, developer...)
  rejected in a title unless it also matches `filters.title_domain_exceptions`
  (AI, automation, programme...).
- `filters.description_hard_reject` and `description_hard_reject_regex`:
  phrases and regular expressions that immediately reject a description,
  including apprenticeships.
- `filters.soft_reject` and `soft_reject_regex`: risks that reduce the
  keyword pre-score.
- `filters.skill_keywords`: skills (English or Turkish) that increase the
  pre-score.
- `filters.max_years_experience`: listings that ask for more years (English or
  Turkish wording) are rejected before any AI call.
- `filters.advanced`: default score weights and penalties. Most candidates do
  not need to change these.
- `selection`: AI score thresholds, default candidate limit, and Top-N size,
  applied per market.
- `documents`: document generation and language (English for every market).
- `notifications`: email enablement and an optional recipient override.
- `schedule`: London timezone, active days, hours and run interval (default
  every 3 hours: 09:00, 12:00, 15:00).

For a market without `queries`, the search layer generates, for each target
role: every `level term + role` combination, the role without a level prefix,
and every entry in `extra_queries`. Duplicate queries are removed
case-insensitively.

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
levels, model and prompt version. Score thresholds are applied after the
cache, so changing them does not throw away cached assessments. Changing a
model re-scores every job once.

A job is identified by its title + company + market (see `filter/identity.py`);
the same id is used for dedup, the archive and `emailed_jobs`, so a listing that
reappears with a new URL, or on another site, is not emailed twice.

## 3. Local setup

Requirements:

- Python 3.12
- `pdflatex` (TeX Live, with `moderncv` if the CV uses it) for PDF output
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

The legacy variable name `OPEN_AI_SECRET_KEY` remains supported, but new
installations should use `OPENAI_API_KEY`.

Run immediately:

```bash
python main.py
```

Local execution does not enforce the schedule by default. Missing config, CV,
or required environment variables are reported before search or AI calls.

## 4. GitHub Actions

The workflow wakes every hour; scheduled runs then follow the timezone, active
days, start/end times and interval in `profile/user_config.json`. A full run of
both markets with the default Istanbul settings takes about 40 minutes, inside
the workflow's 60-minute limit.

After changing `profile/user_config.json` or `profile/master_cv.tex`, update the
matching secret: CI only sees the secrets.

The repository is public, so generated CVs are not uploaded as workflow
artifacts; they arrive by email. `workflow_dispatch` always runs immediately.

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
was reverted because it named a number, tool or skill that the master CV does
not contain).

No email or document-generation call is made when the current run has no new
suitable jobs. A failed SMTP send does not mark jobs as emailed.

## Tests

The tests mock JobSpy, OpenAI, Supabase, SMTP and pipeline side effects:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

They cover configuration validation, query generation and per-market search
plans, job identity and dedup (real Indeed/LinkedIn URL shapes), hard and soft
filters including Turkish title rules, UK and Istanbul location handling
(remote listings included), years-of-experience extraction, the deterministic
score, CV template parsing and rendering for both layouts, grounding checks for
bullets and skill lists, empty runs, SMTP failure and London scheduling.

## Future improvements

- Employer career pages (Koç and Sabancı group companies, industrial
  multinationals) as an extra job source
- A Turkish master CV for Turkish-language ads
- A dashboard for tracking applications and outcomes
- Telegram notifications for high-score jobs

## Disclaimer

This project is intended for educational and automation purposes. Always
review generated CVs and cover letters before submitting applications.

## Author

Yusuf Ciger
