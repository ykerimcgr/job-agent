from __future__ import annotations

from datetime import datetime, time
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


CONFIG_PATH = Path("profile/user_config.json")
CV_PATH = Path("profile/master_cv.tex")
WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
UK_LOCATION_KEYWORDS = [
    "united kingdom", "uk", "gb", "great britain", "england", "scotland", "wales",
    "northern ireland", "london", "manchester", "birmingham", "bristol", "leeds",
    "liverpool", "glasgow", "edinburgh", "cardiff", "brighton", "hove",
]


class ConfigError(ValueError):
    """Raised when user_config.json is missing or invalid."""


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ContactOverrides(Strict):
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    address: str = ""
    right_to_work: str = ""


class CandidateConfig(Strict):
    contact_overrides: ContactOverrides = ContactOverrides()


class SearchConfig(Strict):
    target_roles: list[str] = Field(min_length=1)
    level_terms: list[str] = []
    extra_queries: list[str] = []
    sources: list[str] = Field(default=["indeed", "linkedin"], min_length=1)
    hours_old: int = Field(default=72, ge=1)
    results_per_query: int = Field(default=12, ge=1)


class ExtraSearch(Strict):
    """Another place to run a market's search, e.g. a nearby industrial zone or remote-only."""

    location: str
    remote: bool = False
    # None: run the market's own queries here.
    queries: list[str] | None = None


class MarketConfig(Strict):
    """One place to search. Lists named extra_* are added to the shared lists."""

    code: str = Field(pattern=r"^[A-Z]{2,3}$")
    search_location: str
    country_indeed: str
    location_keywords: list[str] = Field(min_length=1)
    # strict: keep only listings whose location names a keyword (or only the country / remote).
    strict_location: bool = False
    country_names: list[str] = []
    level_terms: list[str] | None = None
    # Per-market overrides of search.sources / search.results_per_query / search.hours_old.
    hours_old: int | None = Field(default=None, ge=1)
    # Per-market override of selection.ai_candidate_limit (how many filtered jobs the AI scores).
    ai_candidate_limit: int | None = Field(default=None, ge=1)
    extra_searches: list[ExtraSearch] = []
    sources: list[str] | None = Field(default=None, min_length=1)
    results_per_query: int | None = Field(default=None, ge=1)
    # When set, exactly these JobSpy queries are used (no role x level expansion).
    queries: list[str] | None = None
    extra_level_keywords: list[str] = []
    extra_queries: list[str] = []
    extra_role_keywords: list[str] = []
    extra_title_hard_reject: list[str] = []
    extra_description_hard_reject: list[str] = []
    contact_overrides: ContactOverrides = ContactOverrides()
    include_right_to_work: bool = True
    cover_letter_style: str = "UK business tone"
    # Length the tailored CV should aim for in this market (1 or 2 pages).
    cv_max_pages: int = Field(default=2, ge=1, le=2)
    scoring_notes: str = ""


DEFAULT_UK_MARKET = MarketConfig(
    code="UK",
    search_location="UK",
    country_indeed="UK",
    location_keywords=UK_LOCATION_KEYWORDS,
    country_names=["united kingdom", "uk", "gb", "great britain"],
)


class FilterAdvancedConfig(Strict):
    min_pre_score: int = 5
    max_score: int = 100
    reject_missing_description: bool = True
    level_bonus: int = 25
    missing_level_penalty: int = 10
    role_bonus: int = 25
    skill_bonus: int = 3
    soft_reject_penalty: int = 8


class FiltersConfig(Strict):
    title_hard_reject: list[str] = []
    # A title-reject word ("manager", "yönetici") is ignored when the title also has one of these
    # ("New Graduates: IT Manager", "Yönetici Yardımcısı"); the AI judges the real level.
    title_hard_reject_exceptions: list[str] = []
    # Off-target fields (finance, developer...). Skipped when the title also has an exception word (AI, programme...).
    title_domain_reject: list[str] = []
    title_domain_exceptions: list[str] = []
    description_hard_reject: list[str] = []
    description_hard_reject_regex: list[str] = []
    soft_reject: list[str] = []
    soft_reject_regex: list[str] = []
    skill_keywords: list[str] = []
    # Listings asking for more years than this are rejected before any AI call.
    max_years_experience: int = Field(default=3, ge=0)
    advanced: FilterAdvancedConfig = FilterAdvancedConfig()

    @field_validator("description_hard_reject_regex", "soft_reject_regex")
    @classmethod
    def _valid_regex(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"Invalid regex {pattern!r}") from exc
        return patterns


class SelectionConfig(Strict):
    min_applicable_rate: int = Field(default=60, ge=0, le=100)
    strong_applicable_rate: int = Field(default=70, ge=0, le=100)
    min_jobs: int = Field(default=5, ge=0)
    max_jobs: int = Field(default=10, ge=1)
    ai_candidate_limit: int = Field(default=40, ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> "SelectionConfig":
        if self.strong_applicable_rate < self.min_applicable_rate:
            raise ValueError("strong_applicable_rate must be >= min_applicable_rate")
        if self.min_jobs > self.max_jobs:
            raise ValueError("min_jobs cannot exceed max_jobs")
        return self


class DocumentsConfig(Strict):
    enabled: bool = True
    cv_language: str = "English"


class NotificationsConfig(Strict):
    enabled: bool = True
    recipient_override: str = ""


class ScheduleConfig(Strict):
    timezone: str = "Europe/London"
    active_days: list[str] = Field(
        default=["monday", "tuesday", "wednesday", "thursday", "friday"], min_length=1
    )
    start_time: time = time(9, 0)
    end_time: time = time(17, 0)
    every_hours: int = Field(default=3, ge=1)

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone {value}") from exc
        return value

    @field_validator("active_days")
    @classmethod
    def _valid_days(cls, days: list[str]) -> list[str]:
        days = [day.casefold() for day in days]
        unknown = set(days) - set(WEEKDAYS)
        if unknown:
            raise ValueError("Unknown days: " + ", ".join(sorted(unknown)))
        return days

    @model_validator(mode="after")
    def _ordered(self) -> "ScheduleConfig":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be earlier than end_time")
        return self

    def should_run(self, now: datetime | None = None, *, force: bool = False) -> bool:
        if force:
            return True
        zone = ZoneInfo(self.timezone)
        local_now = now.astimezone(zone) if now else datetime.now(zone)
        if local_now.weekday() not in {WEEKDAYS[day] for day in self.active_days}:
            return False
        if not self.start_time <= local_now.time().replace(tzinfo=None) < self.end_time:
            return False
        return (local_now.hour - self.start_time.hour) % self.every_hours == 0


class AppConfig(Strict):
    candidate: CandidateConfig = CandidateConfig()
    search: SearchConfig
    filters: FiltersConfig = FiltersConfig()
    markets: list[MarketConfig] = Field(default=[DEFAULT_UK_MARKET], min_length=1)
    selection: SelectionConfig = SelectionConfig()
    documents: DocumentsConfig = DocumentsConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    schedule: ScheduleConfig = ScheduleConfig()
    market: str | None = None  # legacy single-market key, ignored

    @field_validator("markets")
    @classmethod
    def _unique_codes(cls, markets: list[MarketConfig]) -> list[MarketConfig]:
        codes = [market.code for market in markets]
        if len(codes) != len(set(codes)):
            raise ValueError("market codes must be unique")
        return markets

    @classmethod
    def load(cls, path: str | Path = CONFIG_PATH) -> "AppConfig":
        config_path = Path(path)
        if not config_path.exists():
            raise ConfigError(
                f"Missing {config_path}. Copy profile/user_config.example.json "
                "to profile/user_config.json and customise it."
            )
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"Invalid JSON in {config_path}: line {exc.lineno}, column {exc.colno}"
            ) from exc
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            problems = [
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            ]
            raise ConfigError(f"Invalid {config_path}:\n- " + "\n- ".join(problems)) from exc

    def merge_profile(self, profile: dict[str, Any], market: MarketConfig | None = None) -> dict[str, Any]:
        merged = dict(profile)
        field_map = {"address": "current_location"}
        layers = [self.candidate.contact_overrides] + ([market.contact_overrides] if market else [])
        for overrides in layers:
            for key, value in overrides.model_dump().items():
                if value:
                    merged[field_map.get(key, key)] = value
        return merged

    def contact_context(self, profile: dict[str, Any], market: MarketConfig) -> dict[str, str]:
        merged = self.merge_profile(profile, market)
        return {
            "name": str(merged.get("name", "")),
            "email": str(merged.get("email", "")),
            "phone": str(merged.get("phone", "")),
            "linkedin": str(merged.get("linkedin", "")),
            "address": str(merged.get("current_location", "")),
            "right_to_work": (
                str(merged.get("right_to_work", "")) if market.include_right_to_work else ""
            ),
        }
