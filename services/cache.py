from __future__ import annotations

import hashlib
import json


def generate_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate_scoring_cache_key(
    job: dict,
    profile_hash: str,
    config_fingerprint: str,
    *,
    prompt_version: str,
    model: str,
) -> str:
    payload = {
        "job": {
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "url": job.get("url", ""),
            "description": job.get("description", ""),
        },
        "profile_hash": profile_hash,
        "config_fingerprint": config_fingerprint,
        "prompt_version": prompt_version,
        "model": model,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return generate_text_hash(encoded)
