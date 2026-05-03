from __future__ import annotations

import hashlib
from typing import List
from urllib.parse import urlparse, urlunparse

from .normalizer import TextNormalizer, normalize_job
from .types import Job


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
        normalized = normalize_job(job)

        canonical_url = cls.canonical_url(normalized.url)

        if canonical_url:
            raw = f"url|{canonical_url}"
        else:
            raw = "|".join([
                normalized.title,
                normalized.company,
                normalized.target_location,
            ])

        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

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