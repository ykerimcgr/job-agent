from __future__ import annotations

from .config import FilterConfig
from .types import NormalizedJob


class LocationMatcher:
    UK_INDICATORS = (
        "united kingdom",
        " uk ",
        ", uk",
        ", gb",
        "great britain",
        "england",
        "scotland",
        "wales",
        "northern ireland",
        "london",
        "manchester",
        "birmingham",
        "bristol",
        "leeds",
        "liverpool",
        "glasgow",
        "edinburgh",
        "cardiff",
        "brighton",
        "hove",
    )
    EXPLICIT_NON_UK_INDICATORS = (
        "united states",
        " usa ",
        ", us",
        "canada",
        "australia",
        "turkey",
        "turkiye",
        "türkiye",
        "germany",
        "france",
        "india",
        "singapore",
        "netherlands",
        "spain",
        "italy",
    )

    def __init__(self, config: FilterConfig) -> None:
        self.config = config

    def is_target_location(self, normalized_job: NormalizedJob) -> bool:
        if normalized_job.target_market != self.config.market:
            return False

        if self.config.market != "UK":
            return False

        location = f" {normalized_job.location} "
        if any(indicator in location for indicator in self.UK_INDICATORS):
            return True

        if "remote" in location:
            return not any(
                indicator in location
                for indicator in self.EXPLICIT_NON_UK_INDICATORS
            )

        if any(
            indicator in location for indicator in self.EXPLICIT_NON_UK_INDICATORS
        ):
            return False

        # JobSpy is called with location=UK and country_indeed=UK. Some sources
        # return only a city or omit the country, so trust the scoped search
        # unless the listing explicitly identifies a conflicting country.
        return True
