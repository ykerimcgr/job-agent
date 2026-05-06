import json
from pathlib import Path
from datetime import datetime

from services.job_identity import generate_canonical_job_hash


EMAILED_JOBS_PATH = Path("cache/emailed_jobs.json")


def load_emailed_jobs() -> dict:
    if not EMAILED_JOBS_PATH.exists():
        return {}

    try:
        with open(EMAILED_JOBS_PATH, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def save_emailed_jobs(data: dict):
    EMAILED_JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(EMAILED_JOBS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def generate_job_identity_hash_from_job(job: dict) -> str:
    # Backward-compatible wrapper name; canonical hash is source-agnostic.
    return generate_canonical_job_hash(job)


def generate_job_identity_hash_from_item(job_item: dict) -> str:
    return generate_job_identity_hash_from_job(job_item.get("job", {}))


def filter_out_emailed_jobs(jobs: list[dict]) -> list[dict]:
    emailed_jobs = load_emailed_jobs()

    fresh_jobs = []

    for job in jobs:
        job_hash = generate_job_identity_hash_from_job(job)

        if job_hash in emailed_jobs:
            continue

        fresh_jobs.append(job)

    return fresh_jobs


def mark_job_items_as_emailed(top_jobs: dict):
    emailed_jobs = load_emailed_jobs()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for location in ["London", "Istanbul"]:
        for job_item in top_jobs.get(location, []):
            job = job_item.get("job", {})
            job_hash = generate_job_identity_hash_from_job(job)

            emailed_jobs[job_hash] = {
                "sent_at": now,
                "location": location,
                "company": job.get("company", ""),
                "title": job.get("title", ""),
                "url": job.get("url", ""),
                "score": (
                    job_item
                    .get("score_result", {})
                    .get("application_decision", {})
                    .get("applicable_rate", 0)
                )
            }

    save_emailed_jobs(emailed_jobs)
