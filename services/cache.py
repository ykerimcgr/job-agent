import json
import hashlib
from pathlib import Path
from json import JSONDecodeError

from services.job_identity import (
    generate_source_job_hash,
    normalize_identity_text,
    canonicalize_job_url,
)


PROFILE_CACHE_PATH = Path("cache/profile_cache.json")
JOB_CACHE_PATH = Path("cache/job_cache.json")

def generate_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_cached_profile(cv_hash: str):
    if not PROFILE_CACHE_PATH.exists():
        return None

    if PROFILE_CACHE_PATH.stat().st_size == 0:
        return None

    try:
        with open(PROFILE_CACHE_PATH, "r") as f:
            cache = json.load(f)
    except JSONDecodeError:
        return None

    if cache.get("cv_hash") == cv_hash:
        return cache.get("profile")

    return None


def save_profile_cache(cv_hash: str, profile: dict):
    PROFILE_CACHE_PATH.parent.mkdir(exist_ok=True)

    cache_data = {
        "cv_hash": cv_hash,
        "profile": profile
    }

    with open(PROFILE_CACHE_PATH, "w") as f:
        json.dump(cache_data, f, indent=2)

def generate_job_hash(job: dict) -> str:
    # Backward-compatible wrapper name; maps to source_job_hash.
    return generate_source_job_hash(job)


def generate_legacy_job_hash(job: dict) -> str:
    """
    Previous job-cache hash strategy retained for compatibility reads.
    """
    canonical_url = canonicalize_job_url(job.get("url"))

    if canonical_url:
        raw = "|".join([
            normalize_identity_text(job.get("title")),
            normalize_identity_text(job.get("company")),
            canonical_url,
        ])
    else:
        raw = "|".join([
            normalize_identity_text(job.get("title")),
            normalize_identity_text(job.get("company")),
            normalize_identity_text(job.get("location")),
        ])

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_job_cache() -> dict:
    if not JOB_CACHE_PATH.exists() or JOB_CACHE_PATH.stat().st_size == 0:
        return {}

    try:
        with open(JOB_CACHE_PATH, "r") as f:
            return json.load(f)
    except JSONDecodeError:
        return {}


def get_cached_job(job_hash: str):
    cache = load_job_cache()
    return cache.get(job_hash)


def save_job_cache(job_hash: str, data: dict):
    JOB_CACHE_PATH.parent.mkdir(exist_ok=True)

    cache = load_job_cache()
    cache[job_hash] = data

    with open(JOB_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)
