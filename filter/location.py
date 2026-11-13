from __future__ import annotations

import re

from .config import FilterConfig
from .normalizer import TextNormalizer
from .types import NormalizedJob


FOREIGN_COUNTRIES = (
    "united states", "usa", "us", "canada", "australia", "turkey", "turkiye",
    "germany", "france", "india", "singapore", "netherlands", "spain", "italy",
    "ireland", "poland", "united arab emirates", "uae",
)
REMOTE_WORDS = ("remote", "hybrid", "uzaktan", "hibrit")
SEPARATORS = re.compile(r"[,/()\-|]+")


def _contains(location: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", location) is not None


class LocationMatcher:
    def __init__(self, config: FilterConfig) -> None:
        market = config.market
        self.code = market.code
        self.strict = market.strict_location
        self.keywords = [TextNormalizer.normalize(k) for k in market.location_keywords]
        self.country_names = [TextNormalizer.normalize(c) for c in market.country_names]
        own = set(self.keywords) | set(self.country_names)
        self.foreign = [country for country in FOREIGN_COUNTRIES if country not in own]

    def is_target_location(self, normalized_job: NormalizedJob) -> bool:
        if normalized_job.target_market != self.code:
            return False

        location = normalized_job.location
        if not location or any(_contains(location, word) for word in self.keywords):
            # Empty location: trust the location-scoped search.
            return True

        if self.strict and normalized_job.is_remote:
            # A remote listing anywhere in the market's country.
            return any(_contains(location, country) for country in self.country_names)
        if self.strict:
            # Only "Türkiye", "Remote, Turkey" etc.: country-wide or remote listings.
            leftover = location
            for word in self.country_names + list(REMOTE_WORDS):
                leftover = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", " ", leftover)
            return not SEPARATORS.sub(" ", leftover).strip()

        return not any(_contains(location, country) for country in self.foreign)
