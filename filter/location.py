from __future__ import annotations

from typing import Dict

from .config import FilterConfig
from .matcher import KeywordMatcher
from .types import NormalizedJob


class LocationMatcher:
    def __init__(self, config: FilterConfig) -> None:
        self.config = config
        self.location_matchers: Dict[str, KeywordMatcher] = {
            location_name: KeywordMatcher(keywords)
            for location_name, keywords in config.location_keywords.items()
        }

    def is_target_location(self, normalized_job: NormalizedJob) -> bool:
        if not normalized_job.target_location:
            return False

        matcher = self.location_matchers.get(normalized_job.target_location)

        if matcher is None:
            return False

        return matcher.has_match(normalized_job.location)