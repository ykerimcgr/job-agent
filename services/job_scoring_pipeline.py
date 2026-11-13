from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app_config import AppConfig, MarketConfig
from services.cache import generate_scoring_cache_key
from services.scoring import (
    SCORING_MODEL,
    SCORING_PROMPT_VERSION,
    JobAssessment,
    assess_job,
    build_score_result,
    scoring_fingerprint,
)
from services.state_store import get_cached_job, save_job_cache


MAX_PARALLEL_CALLS = 5


def score_jobs_batch(
    jobs: list[dict],
    profile: dict,
    profile_hash: str,
    config: AppConfig,
    market: MarketConfig,
) -> list[dict]:
    fingerprint = scoring_fingerprint(config, market)
    assessments: dict[int, JobAssessment | Exception] = {}
    cache_keys: dict[int, str] = {}
    to_score: list[int] = []

    for index, job in enumerate(jobs):
        cache_keys[index] = generate_scoring_cache_key(
            job,
            profile_hash,
            fingerprint,
            prompt_version=SCORING_PROMPT_VERSION,
            model=SCORING_MODEL,
        )
        cached = get_cached_job(cache_keys[index])
        try:
            assessments[index] = JobAssessment.model_validate(cached["score_result"])
            print(f"Loaded from cache ✔ {job.get('title')} | {job.get('company')}")
        except (TypeError, KeyError, ValueError):
            to_score.append(index)

    def run(index: int) -> JobAssessment | Exception:
        job = jobs[index]
        print(f"Scoring with OpenAI → {job.get('title')} | {job.get('company')}")
        try:
            return assess_job(job, profile, config, market)
        except Exception as exc:  # one bad job must not stop the batch
            print(f"AI scoring failed for {job.get('title')} | {job.get('company')}: {exc}")
            return exc

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CALLS) as pool:
        for index, result in zip(to_score, pool.map(run, to_score)):
            assessments[index] = result
            if isinstance(result, JobAssessment):
                save_job_cache(
                    cache_keys[index],
                    {"parsed_job": None, "score_result": result.model_dump()},
                )

    scored_jobs: list[dict] = []
    for index, job in enumerate(jobs):
        result = assessments[index]
        if isinstance(result, Exception):
            score_result = {"status": "error", "reason": str(result)}
        else:
            score_result = build_score_result(result, config)
        scored_jobs.append({"job": job, "score_result": score_result})
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
