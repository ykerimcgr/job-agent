from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import os
import time
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client


load_dotenv()


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_KEY") or "").strip()
    if not url or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY are required environment variables"
        )
    return create_client(url, key)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_job_identity_hash_from_job(job: dict) -> str:
    raw = "|".join(
        [
            (job.get("title") or "").casefold().strip(),
            (job.get("company") or "").casefold().strip(),
            (job.get("location") or "").casefold().strip(),
            (job.get("url") or "").casefold().strip(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def execute_with_retry(query_builder, retries: int = 3, delay: float = 2.0):
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return query_builder.execute()
        except Exception as exc:
            last_error = exc
            print(f"Supabase request failed attempt {attempt}/{retries}: {exc}")
            if attempt < retries:
                time.sleep(delay * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Supabase request failed without an exception")


def check_supabase_connection() -> None:
    query = get_supabase_client().table("profile_cache").select("cv_hash").limit(1)
    execute_with_retry(query, retries=1)


def load_cached_profile(cv_hash: str) -> Optional[dict]:
    query = (
        get_supabase_client()
        .table("profile_cache")
        .select("profile_json")
        .eq("cv_hash", cv_hash)
        .limit(1)
    )
    response = execute_with_retry(query)
    if not response.data:
        return None
    return response.data[0].get("profile_json")


def save_profile_cache(cv_hash: str, profile: dict) -> None:
    payload = {
        "cv_hash": cv_hash,
        "profile_json": profile,
        "updated_at": now_iso(),
    }
    query = get_supabase_client().table("profile_cache").upsert(payload)
    execute_with_retry(query)


def get_cached_job(cache_key: str) -> Optional[dict]:
    query = (
        get_supabase_client()
        .table("job_cache")
        .select("parsed_job_json, score_result_json")
        .eq("job_hash", cache_key)
        .limit(1)
    )
    response = execute_with_retry(query)
    if not response.data:
        return None
    row = response.data[0]
    if row.get("parsed_job_json") is None and row.get("score_result_json") is None:
        return None
    return {
        "parsed_job": row.get("parsed_job_json"),
        "score_result": row.get("score_result_json"),
    }


def save_job_cache(cache_key: str, data: dict) -> None:
    payload = {
        "job_hash": cache_key,
        "parsed_job_json": data.get("parsed_job"),
        "score_result_json": data.get("score_result"),
        "updated_at": now_iso(),
    }
    query = get_supabase_client().table("job_cache").upsert(payload)
    execute_with_retry(query)


def load_emailed_job_hashes() -> set[str]:
    query = get_supabase_client().table("emailed_jobs").select("job_hash")
    response = execute_with_retry(query)
    return {
        row["job_hash"]
        for row in (response.data or [])
        if row.get("job_hash")
    }


def filter_out_emailed_jobs(jobs: list[dict]) -> list[dict]:
    emailed_hashes = load_emailed_job_hashes()
    return [
        job
        for job in jobs
        if generate_job_identity_hash_from_job(job) not in emailed_hashes
    ]


def mark_job_items_as_emailed(top_jobs: dict) -> None:
    rows: list[dict] = []
    sent_at = now_iso()

    for item in top_jobs.get("UK", []):
        job = item.get("job", {})
        rows.append(
            {
                "job_hash": generate_job_identity_hash_from_job(job),
                "sent_at": sent_at,
                "location": "UK",
                "company": job.get("company", ""),
                "title": job.get("title", ""),
                "url": job.get("url", ""),
                "score": (
                    item.get("score_result", {})
                    .get("application_decision", {})
                    .get("applicable_rate", 0)
                ),
            }
        )

    if rows:
        query = get_supabase_client().table("emailed_jobs").upsert(rows)
        execute_with_retry(query)
