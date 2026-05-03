from __future__ import annotations

from typing import List, Optional, Tuple

from .config import FilterConfig
from .dedup import DuplicateDetector
from .location import LocationMatcher
from .matcher import Matchers
from .rejector import HardRejector
from .scorer import JobScorer
from .types import Job


class JobFilter:
    def __init__(self, config: Optional[FilterConfig] = None) -> None:
        self.config = config or FilterConfig()

        self.matchers = Matchers.from_config(self.config)
        self.location_matcher = LocationMatcher(self.config)

        self.rejector = HardRejector(
            config=self.config,
            matchers=self.matchers,
            location_matcher=self.location_matcher,
        )

        self.scorer = JobScorer(
            config=self.config,
            matchers=self.matchers,
            location_matcher=self.location_matcher,
        )

    def filter_jobs(self, jobs: List[Job]) -> Tuple[List[Job], List[Job]]:
        accepted: List[Job] = []
        rejected: List[Job] = []

        for raw_job in jobs:
            job = dict(raw_job)

            reject_result = self.rejector.check(job)

            if reject_result.rejected:
                job["reject_reason"] = reject_result.reason
                rejected.append(job)
                continue

            score_result = self.scorer.score(job)

            job["pre_score"] = score_result.score
            job["quality_flags"] = score_result.quality_flags
            job["risk_flags"] = score_result.risk_flags

            if score_result.score < self.config.min_score:
                job["reject_reason"] = "low_score"
                rejected.append(job)
                continue

            accepted.append(job)

        accepted = DuplicateDetector.remove_duplicates(accepted)

        accepted.sort(
            key=lambda item: item.get("pre_score", 0),
            reverse=True,
        )

        return accepted, rejected


def filter_jobs(
    jobs: List[Job],
    config: Optional[FilterConfig] = None,
) -> Tuple[List[Job], List[Job]]:
    job_filter = JobFilter(config=config)
    return job_filter.filter_jobs(jobs)


def split_top_jobs_by_location(
    jobs: List[Job],
    london_limit: int = 20,
    istanbul_limit: int = 20,
) -> Tuple[List[Job], List[Job]]:
    london: List[Job] = []
    istanbul: List[Job] = []

    for job in jobs:
        target_location = job.get("target_location")

        if target_location == "London" and len(london) < london_limit:
            london.append(job)

        elif target_location == "Istanbul" and len(istanbul) < istanbul_limit:
            istanbul.append(job)

        if len(london) >= london_limit and len(istanbul) >= istanbul_limit:
            break

    return london, istanbul