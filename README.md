# Reusable UK AI Job Agent

This project searches UK job listings, applies deterministic filters, scores
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
JobSpy UK search
          ↓
Config-driven hard filters and pre-score
          ↓
Candidate-specific OpenAI fit score
          ↓
Top UK jobs
          ↓
Tailored CV and cover letter
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
- `search.extra_queries`: full additional JobSpy queries.
- `search.sources`, `hours_old`, and `results_per_query`: search behaviour.
- `filters.title_hard_reject`: phrases that immediately reject a title.
- `filters.description_hard_reject`: phrases that immediately reject a
  description.
- `filters.description_hard_reject_regex`: advanced regular-expression hard
  rejects, including apprenticeships.
- `filters.soft_reject` and `soft_reject_regex`: risks that reduce the
  deterministic pre-score.
- `filters.skill_keywords`: skills that increase the pre-score.
- `filters.advanced`: default score weights and penalties. Most candidates do
  not need to change these.
- `selection`: AI score thresholds, candidate limit, and daily Top-N size.
- `documents`: document generation, language, UK tone, and right-to-work use.
- `notifications`: email enablement and an optional recipient override.
- `schedule`: London timezone, active days, hours, and hourly interval.

For each target role, the search layer generates:

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

The AI cache key includes the job, candidate profile, scoring configuration,
model, and prompt version. Changing the CV or a scoring-relevant config value
therefore cannot reuse a stale score from another candidate context.

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

The workflow runs every hour. Scheduled runs read the actual timezone, active
days, start/end times, and interval from `profile/user_config.json`.
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
│   ├── jobspy_raw.json
│   ├── jobspy_filtered.json
│   └── jobspy_rejected.json
├── UK/
│   ├── uk_candidates.json
│   └── uk_scored.json
├── applications/
│   └── UK/
├── history/
├── top_jobs_current_run.json
├── top_jobs.json
└── generated_documents.json
```

The canonical selected-job shape is:

```json
{
  "UK": []
}
```

No email or document-generation call is made when the current run has no new
suitable jobs. A failed SMTP send does not mark jobs as emailed.

## Tests

The tests mock JobSpy, OpenAI, Supabase, SMTP, and pipeline side effects:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

They cover configuration validation, query generation, hard and soft filters,
UK location handling, candidate-specific cache keys, selection thresholds,
candidate document identity, empty runs, SMTP failure, and London scheduling.
