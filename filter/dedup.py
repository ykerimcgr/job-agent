from __future__ import annotations

from typing import List
from urllib.parse import urlparse, urlunparse

from .normalizer import TextNormalizer
from .types import Job
from services.job_identity import generate_canonical_job_hash


class DuplicateDetector:
    @classmethod
    def canonical_url(cls, url: str) -> str:
        if not url:
            return ""

        parsed = urlparse(url)

        if not parsed.netloc:
            return ""

        cleaned = parsed._replace(query="", fragment="")
        canonical = urlunparse(cleaned).rstrip("/")

        return TextNormalizer.normalize(canonical)

    @classmethod
    def generate_key(cls, job: Job) -> str:
        return generate_canonical_job_hash(job)

    @classmethod
    def remove_duplicates(cls, jobs: List[Job]) -> List[Job]:
        seen: set[str] = set()
        unique: List[Job] = []

        for job in jobs:
            key = cls.generate_key(job)

            if key in seen:
                job["duplicate_removed"] = True
                continue

            seen.add(key)
            job["duplicate_key"] = key
            unique.append(job)

        return unique
