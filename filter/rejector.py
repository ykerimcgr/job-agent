from __future__ import annotations

from .config import FilterConfig
from .location import LocationMatcher
from .matcher import Matchers
from .normalizer import normalize_job
from .types import Job, RejectResult


class HardRejector:
    def __init__(
        self,
        config: FilterConfig,
        matchers: Matchers,
        location_matcher: LocationMatcher,
    ) -> None:
        self.config = config
        self.matchers = matchers
        self.location_matcher = location_matcher

    def check(self, job: Job) -> RejectResult:
        normalized = normalize_job(job)

        if self.config.reject_if_missing_description and not normalized.description:
            return RejectResult(
                rejected=True,
                reason="missing_description",
            )

        title_rejects = self.matchers.title_hard_reject.find_matches(
            normalized.title
        )

        if title_rejects:
            return RejectResult(
                rejected=True,
                reason=f"title_reject:{title_rejects[0]}",
            )

        description_rejects = self.matchers.description_hard_reject.find_matches(
            normalized.description
        )

        if description_rejects:
            return RejectResult(
                rejected=True,
                reason=f"description_reject:{description_rejects[0]}",
            )

        if not self.location_matcher.is_target_location(normalized):
            return RejectResult(
                rejected=True,
                reason="location_mismatch",
            )

        return RejectResult(rejected=False)