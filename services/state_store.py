import os, time
import hashlib
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client, Client
from services.job_identity import generate_canonical_job_hash


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


# =========================================================
# SUPABASE CLIENT
# =========================================================

def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing from environment variables")

    return create_client(SUPABASE_URL, SUPABASE_KEY)


supabase = get_supabase_client()


# =========================================================
# COMMON HELPERS
# =========================================================

def now_iso() -> str:
    return datetime.now().isoformat()


def generate_job_identity_hash_from_job(job: dict) -> str:
    """
    Stable identity hash for identifying a job across runs.
    Used for emailed_jobs and duplicate detection.
    """
    # Backward-compatible wrapper name; canonical hash is source-agnostic.
    return generate_canonical_job_hash(job)


def generate_job_identity_hash_from_item(job_item: dict) -> str:
    return generate_job_identity_hash_from_job(job_item.get("job", {}))


def generate_legacy_job_identity_hash_from_job(job: dict) -> str:
    """
    Previous emailed-job hash strategy retained for compatibility reads.
    """
    raw = "|".join([
        (job.get("title") or "").lower().strip(),
        (job.get("company") or "").lower().strip(),
        (job.get("location") or "").lower().strip(),
        (job.get("url") or "").lower().strip(),
    ])

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def execute_with_retry(query_builder, retries: int = 3, delay: float = 2.0):
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            return query_builder.execute()
        except Exception as e:
            last_error = e
            print(f"Supabase request failed attempt {attempt}/{retries}: {e}")

            if attempt < retries:
                time.sleep(delay * attempt)

    raise last_error

# =========================================================
# PROFILE CACHE
# =========================================================

def load_cached_profile(cv_hash: str) -> Optional[dict]:
    """
    Load parsed profile from Supabase by CV hash.
    """
    query = (
        supabase
        .table("profile_cache")
        .select("profile_json")
        .eq("cv_hash", cv_hash)
        .limit(1)
    )

    response = execute_with_retry( query )


    if not response.data:
        return None

    return response.data[0].get("profile_json")


def save_profile_cache(cv_hash: str, profile: dict) -> None:
    """
    Upsert parsed profile into Supabase.
    """
    payload = {
        "cv_hash": cv_hash,
        "profile_json": profile,
        "updated_at": now_iso()
    }

    try:
        query = (
            supabase
            .table("profile_cache")
            .upsert(payload)
        )

        execute_with_retry(query)

    except Exception as e:
        print(f"Supabase job cache save failed, continuing pipeline: {e}")


# =========================================================
# JOB CACHE
# =========================================================

def get_cached_job(job_hash: str) -> Optional[dict]:
    """
    Load parsed job + score result from Supabase by job hash.
    Return structure matches old local cache style:
    {
        "parsed_job": {...},
        "score_result": {...}
    }
    """
    query = (
        supabase
        .table("job_cache")
        .select("parsed_job_json, score_result_json")
        .eq("job_hash", job_hash)
        .limit(1)
    )

    response = execute_with_retry( query )

    if not response.data:
        return None

    row = response.data[0]

    parsed_job = row.get("parsed_job_json")
    score_result = row.get("score_result_json")

    if parsed_job is None and score_result is None:
        return None

    return {
        "parsed_job": parsed_job,
        "score_result": score_result
    }


def save_job_cache(job_hash: str, data: dict) -> None:
    """
    Save parsed job and score result into Supabase.

    Expected data:
    {
        "parsed_job": {...},
        "score_result": {...}
    }
    """
    payload = {
        "job_hash": job_hash,
        "parsed_job_json": data.get("parsed_job"),
        "score_result_json": data.get("score_result"),
        "updated_at": now_iso()
    }

    try:
        query = (
            supabase
            .table("job_cache")
            .upsert(payload)
        )

        execute_with_retry( query )

    except Exception as e:
        print(f"Supabase job cache save failed, continuing pipeline: {e}")


# =========================================================
# EMAILED JOBS
# =========================================================

def load_emailed_job_hashes() -> set[str]:
    """
    Load all previously emailed job hashes.
    """
    query = (
        supabase
        .table("emailed_jobs")
        .select("job_hash")
    )

    response = execute_with_retry(query)

    hashes = set()

    for row in response.data or []:
        job_hash = row.get("job_hash")
        if job_hash:
            hashes.add(job_hash)

    return hashes


def is_job_emailed(job: dict) -> bool:
    """
    Check if a raw job has already been emailed.
    """
    job_hash = generate_job_identity_hash_from_job(job)
    legacy_hash = generate_legacy_job_identity_hash_from_job(job)
    emailed_hashes = load_emailed_job_hashes()

    return job_hash in emailed_hashes or legacy_hash in emailed_hashes


def filter_out_emailed_jobs(jobs: list[dict]) -> list[dict]:
    """
    Remove jobs that were already emailed before AI scoring.

    This is important because we do not want already-sent jobs
    to compete again in the top jobs list.
    """
    emailed_hashes = load_emailed_job_hashes()

    fresh_jobs = []

    for job in jobs:
        job_hash = generate_job_identity_hash_from_job(job)
        legacy_hash = generate_legacy_job_identity_hash_from_job(job)

        if job_hash in emailed_hashes or legacy_hash in emailed_hashes:
            continue

        fresh_jobs.append(job)

    return fresh_jobs


def mark_job_items_as_emailed(top_jobs: dict) -> None:
    """
    Mark emailed top jobs in Supabase after email is successfully sent.
    """
    rows_to_upsert = []
    sent_at = now_iso()

    for location in ["London", "Istanbul"]:
        for job_item in top_jobs.get(location, []):
            job = job_item.get("job", {})
            job_hash = generate_job_identity_hash_from_job(job)

            score = (
                job_item
                .get("score_result", {})
                .get("application_decision", {})
                .get("applicable_rate", 0)
            )

            rows_to_upsert.append({
                "job_hash": job_hash,
                "sent_at": sent_at,
                "location": location,
                "company": job.get("company", ""),
                "title": job.get("title", ""),
                "url": job.get("url", ""),
                "score": score
            })

    if not rows_to_upsert:
        return

    query = (
        supabase
        .table("emailed_jobs")
        .upsert(rows_to_upsert)
    )

    execute_with_retry( query )
