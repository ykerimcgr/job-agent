import json
from pathlib import Path

from agents.job_parser import parse_job_description
from services.scoring import score_job
from services.cache import generate_legacy_job_hash, generate_text_hash
from services.job_identity import generate_source_job_hash
from services.state_store import get_cached_job, save_job_cache


def score_single_job(
    job: dict,
    profile: dict,
    contact_rules: dict,
    location_rules: dict
) -> dict:
    job_text = job.get("description", "")

    if not job_text:
        return {
            "job": job,
            "parsed_job": None,
            "score_result": {
                "status": "rejected",
                "reason": "missing_description"
            }
        }

    source_job_hash = generate_source_job_hash(job)
    legacy_text_hash = generate_text_hash(
        f"{job.get('title', '')}|{job.get('company', '')}|{job.get('location', '')}|{job_text}"
    )

    cached = get_cached_job(source_job_hash) or get_cached_job(legacy_text_hash)

    if cached and "parsed_job" in cached and "score_result" in cached:
        print(f"Loaded from cache ✔ {job.get('title')} | {job.get('company')}")
        return {
            "job": job,
            "parsed_job": cached["parsed_job"],
            "score_result": cached["score_result"]
        }

    print(f"Scoring with OpenAI → {job.get('title')} | {job.get('company')}")

    parsed_job = parse_job_description(job_text)

    score_result = score_job(
        job_text=job_text,
        parsed_job=parsed_job,
        profile=profile,
        contact_rules=contact_rules,
        location_rules=location_rules
    )

    save_job_cache(source_job_hash, {
        "parsed_job": parsed_job,
        "score_result": score_result
    })

    return {
        "job": job,
        "parsed_job": parsed_job,
        "score_result": score_result
    }


def score_jobs_batch(
    jobs: list[dict],
    profile: dict,
    contact_rules: dict,
    location_rules: dict
) -> list[dict]:
    scored_jobs = []

    for job in jobs:
        title = job.get("title", "Unknown title")
        company = job.get("company", "Unknown company")

        # Stable job hash
        if isinstance(job, dict):
            source_job_hash = generate_source_job_hash(job)
            legacy_job_hash = generate_legacy_job_hash(job)
        else:
            source_job_hash = generate_text_hash(str(job))
            legacy_job_hash = source_job_hash

        cached_job = get_cached_job(source_job_hash)
        if not cached_job and legacy_job_hash != source_job_hash:
            cached_job = get_cached_job(legacy_job_hash)

        if cached_job and cached_job.get("parsed_job") and cached_job.get("score_result"):
            print(f"Loaded from Supabase cache ✔ {title} | {company}")

            scored_jobs.append({
                "job": job,
                "parsed_job": cached_job["parsed_job"],
                "score_result": cached_job["score_result"]
            })

            continue

        print(f"Scoring with OpenAI → {title} | {company}")

        job_text = job.get("description", "")

        parsed_job = parse_job_description(job_text)

        score_result = score_job(
            job_text=job_text,
            parsed_job=parsed_job,
            profile=profile,
            contact_rules=contact_rules,
            location_rules=location_rules
        )

        result_item = {
            "job": job,
            "parsed_job": parsed_job,
            "score_result": score_result
        }

        save_job_cache(
            source_job_hash,
            {
                "parsed_job": parsed_job,
                "score_result": score_result
            }
        )

        scored_jobs.append(result_item)

    return scored_jobs


def get_applicable_rate(scored_job: dict) -> float:
    return (
        scored_job
        .get("score_result", {})
        .get("application_decision", {})
        .get("applicable_rate", 0)
    )


def select_top_jobs(scored_jobs: list[dict], min_jobs: int = 5, max_jobs: int = 10) -> list[dict]:
    valid_jobs = [
        job for job in scored_jobs
        if job.get("score_result", {}).get("status") == "scored"
        and job.get("score_result", {}).get("application_decision", {}).get("decision") != "skip"
        and get_applicable_rate(job) >= 60
    ]


    sorted_jobs = sorted(
        valid_jobs,
        key=get_applicable_rate,
        reverse=True
    )

    strong_jobs = [
        job for job in sorted_jobs
        if get_applicable_rate(job) >= 70
    ]

    if len(strong_jobs) >= min_jobs:
        return strong_jobs[:max_jobs]

    return sorted_jobs[:min(max_jobs, len(sorted_jobs))]
