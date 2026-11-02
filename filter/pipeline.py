from __future__ import annotations

from typing import List, Tuple

from app_config import AppConfig
from .config import FilterConfig
from .dedup import DuplicateDetector
from .location import LocationMatcher
from .matcher import Matchers
from .rejector import HardRejector
from .scorer import JobScorer
from .types import Job


class JobFilter:
    def __init__(self, config: FilterConfig) -> None:
        self.config = config

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
    config: AppConfig | FilterConfig,
) -> Tuple[List[Job], List[Job]]:
    filter_config = (
        FilterConfig.from_app_config(config)
        if isinstance(config, AppConfig)
        else config
    )
    job_filter = JobFilter(config=filter_config)
    return job_filter.filter_jobs(jobs)


def select_top_candidates(
    jobs: List[Job],
    limit: int,
) -> List[Job]:
    return jobs[:limit]
