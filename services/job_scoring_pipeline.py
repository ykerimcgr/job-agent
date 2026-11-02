from __future__ import annotations

from agents.job_parser import parse_job_description
from app_config import AppConfig
from services.cache import generate_scoring_cache_key
from services.scoring import SCORING_MODEL, SCORING_PROMPT_VERSION, score_job
from services.state_store import get_cached_job, save_job_cache


def score_jobs_batch(
    jobs: list[dict],
    profile: dict,
    profile_hash: str,
    config: AppConfig,
) -> list[dict]:
    scored_jobs: list[dict] = []
    config_fingerprint = config.scoring_fingerprint()

    for job in jobs:
        title = job.get("title", "Unknown title")
        company = job.get("company", "Unknown company")
        description = job.get("description", "")

        if not description:
            scored_jobs.append(
                {
                    "job": job,
                    "parsed_job": None,
                    "score_result": {
                        "status": "rejected",
                        "reason": "missing_description",
                    },
                }
            )
            continue

        cache_key = generate_scoring_cache_key(
            job,
            profile_hash,
            config_fingerprint,
            prompt_version=SCORING_PROMPT_VERSION,
            model=SCORING_MODEL,
        )
        cached_job = get_cached_job(cache_key)

        if cached_job and cached_job.get("parsed_job") and cached_job.get("score_result"):
            print(f"Loaded from Supabase cache ✔ {title} | {company}")
            scored_jobs.append(
                {
                    "job": job,
                    "parsed_job": cached_job["parsed_job"],
                    "score_result": cached_job["score_result"],
                }
            )
            continue

        print(f"Scoring with OpenAI → {title} | {company}")
        try:
            parsed_job = parse_job_description(description)
            score_result = score_job(
                job_text=description,
                parsed_job=parsed_job,
                profile=profile,
                config=config,
            )
        except Exception as exc:
            print(f"AI scoring failed for {title} | {company}: {exc}")
            scored_jobs.append(
                {
                    "job": job,
                    "parsed_job": None,
                    "score_result": {
                        "status": "error",
                        "reason": str(exc),
                    },
                }
            )
            continue

        save_job_cache(
            cache_key,
            {
                "parsed_job": parsed_job,
                "score_result": score_result,
            },
        )
        scored_jobs.append(
            {
                "job": job,
                "parsed_job": parsed_job,
                "score_result": score_result,
            }
        )

    return scored_jobs


def get_applicable_rate(scored_job: dict) -> float:
    return (
        scored_job.get("score_result", {})
        .get("application_decision", {})
        .get("applicable_rate", 0)
    )


def select_top_jobs(scored_jobs: list[dict], config: AppConfig) -> list[dict]:
    selection = config.selection
    valid_jobs = [
        item
        for item in scored_jobs
        if item.get("score_result", {}).get("status") == "scored"
        and item.get("score_result", {})
        .get("application_decision", {})
        .get("decision")
        != "skip"
        and get_applicable_rate(item) >= selection.min_applicable_rate
    ]
    sorted_jobs = sorted(valid_jobs, key=get_applicable_rate, reverse=True)
    strong_jobs = [
        item
        for item in sorted_jobs
        if get_applicable_rate(item) >= selection.strong_applicable_rate
    ]

    if len(strong_jobs) >= selection.min_jobs:
        return strong_jobs[: selection.max_jobs]
    return sorted_jobs[: selection.max_jobs]
