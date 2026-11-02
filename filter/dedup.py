from __future__ import annotations

from typing import List, Tuple

from .identity import content_key, source_job_id
from .types import Job


def remove_duplicates(jobs: List[Job]) -> Tuple[List[Job], List[Job]]:
    """Keep the first copy of each job; a job is a duplicate if its site id OR its title+company matches."""
    seen: set[str] = set()
    unique: List[Job] = []
    duplicates: List[Job] = []

    for job in jobs:
        keys = {key for key in (source_job_id(job.get("url")), content_key(job)) if key}
        if keys & seen:
            duplicates.append({**job, "reject_reason": "duplicate"})
            continue
        seen |= keys
        unique.append(job)

    return unique, duplicates
