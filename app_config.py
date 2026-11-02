from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, time
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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


class ConfigError(ValueError):
    """Raised when user_config.json is missing or invalid."""


def _string_list(value: Any, field_name: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{field_name} must be a JSON array of strings")

    cleaned = [item.strip() for item in value if item.strip()]
    if not allow_empty and not cleaned:
        raise ConfigError(f"{field_name} must contain at least one value")
    return cleaned


def _object(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{field_name} must be a JSON object")
    return value


def _reject_unknown(
    value: dict[str, Any],
    allowed: set[str],
    field_name: str,
) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ConfigError(
            f"Unknown {field_name} fields: " + ", ".join(sorted(unknown))
        )


def _string(
    value: Any,
    field_name: str,
    *,
    allow_empty: bool = True,
) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{field_name} must be a string")
    cleaned = value.strip()
    if not allow_empty and not cleaned:
        raise ConfigError(f"{field_name} cannot be empty")
    return cleaned


def _positive_int(value: Any, field_name: str, *, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ConfigError(f"{field_name} must be an integer greater than or equal to {minimum}")
    return value


def _number(value: Any, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"{field_name} must be a number")
    return float(value)


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{field_name} must be true or false")
    return value


def _parse_time(value: Any, field_name: str) -> time:
    if not isinstance(value, str):
        raise ConfigError(f"{field_name} must use HH:MM format")
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(f"{field_name} must use HH:MM format") from exc


@dataclass(frozen=True)
class ContactOverrides:
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    address: str = ""
    right_to_work: str = ""


@dataclass(frozen=True)
class CandidateConfig:
    contact_overrides: ContactOverrides = field(default_factory=ContactOverrides)


@dataclass(frozen=True)
class SearchConfig:
    target_roles: list[str]
    level_terms: list[str]
    extra_queries: list[str]
    sources: list[str]
    hours_old: int = 168
    results_per_query: int = 12


@dataclass(frozen=True)
class FilterAdvancedConfig:
    min_pre_score: int = 40
    max_score: int = 100
    reject_missing_description: bool = True
    location_score: int = 15
    level_bonus: int = 25
    missing_level_penalty: int = 10
    role_bonus: int = 25
    skill_bonus: int = 3
    description_bonus: int = 8
    missing_description_penalty: int = 10
    url_bonus: int = 5
    soft_reject_penalty: int = 8
    source_bonus: dict[str, int] = field(
        default_factory=lambda: {"linkedin": 3, "indeed": 3}
    )


@dataclass(frozen=True)
class FiltersConfig:
    title_hard_reject: list[str]
    description_hard_reject: list[str]
    description_hard_reject_regex: list[str]
    soft_reject: list[str]
    soft_reject_regex: list[str]
    skill_keywords: list[str]
    advanced: FilterAdvancedConfig = field(default_factory=FilterAdvancedConfig)


@dataclass(frozen=True)
class SelectionConfig:
    min_applicable_rate: int = 60
    strong_applicable_rate: int = 70
    min_jobs: int = 5
    max_jobs: int = 10
    ai_candidate_limit: int = 40


@dataclass(frozen=True)
class DocumentsConfig:
    enabled: bool = True
    cv_language: str = "English"
    cover_letter_style: str = "UK business tone"
    include_right_to_work: bool = True


@dataclass(frozen=True)
class NotificationsConfig:
    enabled: bool = True
    recipient_override: str = ""


@dataclass(frozen=True)
class ScheduleConfig:
    timezone: str = "Europe/London"
    active_days: list[str] = field(
        default_factory=lambda: ["monday", "tuesday", "wednesday", "thursday", "friday"]
    )
    start_time: str = "09:00"
    end_time: str = "17:00"
    every_hours: int = 1

    def should_run(self, now: datetime | None = None, *, force: bool = False) -> bool:
        if force:
            return True

        timezone = ZoneInfo(self.timezone)
        local_now = now.astimezone(timezone) if now else datetime.now(timezone)
        allowed_weekdays = {WEEKDAYS[day] for day in self.active_days}

        if local_now.weekday() not in allowed_weekdays:
            return False

        start = _parse_time(self.start_time, "schedule.start_time")
        end = _parse_time(self.end_time, "schedule.end_time")
        if not start <= local_now.time().replace(tzinfo=None) < end:
            return False

        elapsed_hours = local_now.hour - start.hour
        return elapsed_hours >= 0 and elapsed_hours % self.every_hours == 0


@dataclass(frozen=True)
class AppConfig:
    candidate: CandidateConfig
    search: SearchConfig
    filters: FiltersConfig
    selection: SelectionConfig
    documents: DocumentsConfig
    notifications: NotificationsConfig
    schedule: ScheduleConfig
    market: str = "UK"

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

        root = _object(raw, "configuration")
        _reject_unknown(
            root,
            {
                "market",
                "candidate",
                "search",
                "filters",
                "selection",
                "documents",
                "notifications",
                "schedule",
            },
            "top-level",
        )
        candidate_raw = _object(root.get("candidate", {}), "candidate")
        _reject_unknown(candidate_raw, {"contact_overrides"}, "candidate")
        overrides_raw = _object(
            candidate_raw.get("contact_overrides", {}), "candidate.contact_overrides"
        )
        allowed_contacts = set(ContactOverrides.__dataclass_fields__)
        unknown_contacts = set(overrides_raw) - allowed_contacts
        if unknown_contacts:
            raise ConfigError(
                "Unknown candidate.contact_overrides fields: "
                + ", ".join(sorted(unknown_contacts))
            )
        for key, value in overrides_raw.items():
            if not isinstance(value, str):
                raise ConfigError(f"candidate.contact_overrides.{key} must be a string")
        candidate = CandidateConfig(contact_overrides=ContactOverrides(**overrides_raw))

        search_raw = _object(root.get("search"), "search")
        _reject_unknown(
            search_raw,
            set(SearchConfig.__dataclass_fields__),
            "search",
        )
        search = SearchConfig(
            target_roles=_string_list(
                search_raw.get("target_roles"), "search.target_roles", allow_empty=False
            ),
            level_terms=_string_list(
                search_raw.get("level_terms", []), "search.level_terms"
            ),
            extra_queries=_string_list(
                search_raw.get("extra_queries", []), "search.extra_queries"
            ),
            sources=_string_list(
                search_raw.get("sources", ["indeed", "linkedin"]),
                "search.sources",
                allow_empty=False,
            ),
            hours_old=_positive_int(
                search_raw.get("hours_old", 168), "search.hours_old"
            ),
            results_per_query=_positive_int(
                search_raw.get("results_per_query", 12),
                "search.results_per_query",
            ),
        )

        filters_raw = _object(root.get("filters"), "filters")
        _reject_unknown(
            filters_raw,
            {
                "title_hard_reject",
                "description_hard_reject",
                "description_hard_reject_regex",
                "soft_reject",
                "soft_reject_regex",
                "skill_keywords",
                "advanced",
            },
            "filters",
        )
        advanced_raw = _object(filters_raw.get("advanced", {}), "filters.advanced")
        _reject_unknown(
            advanced_raw,
            set(FilterAdvancedConfig.__dataclass_fields__),
            "filters.advanced",
        )
        source_bonus_raw = _object(
            advanced_raw.get("source_bonus", {"linkedin": 3, "indeed": 3}),
            "filters.advanced.source_bonus",
        )
        source_bonus: dict[str, int] = {}
        for source, bonus in source_bonus_raw.items():
            if not isinstance(source, str) or not isinstance(bonus, int):
                raise ConfigError(
                    "filters.advanced.source_bonus must map source names to integers"
                )
            source_bonus[source.casefold()] = bonus

        advanced = FilterAdvancedConfig(
            min_pre_score=int(
                _number(
                    advanced_raw.get("min_pre_score", 40),
                    "filters.advanced.min_pre_score",
                )
            ),
            max_score=int(
                _number(
                    advanced_raw.get("max_score", 100), "filters.advanced.max_score"
                )
            ),
            reject_missing_description=_boolean(
                advanced_raw.get("reject_missing_description", True),
                "filters.advanced.reject_missing_description",
            ),
            location_score=int(
                _number(
                    advanced_raw.get("location_score", 15),
                    "filters.advanced.location_score",
                )
            ),
            level_bonus=int(
                _number(
                    advanced_raw.get("level_bonus", 25),
                    "filters.advanced.level_bonus",
                )
            ),
            missing_level_penalty=int(
                _number(
                    advanced_raw.get("missing_level_penalty", 10),
                    "filters.advanced.missing_level_penalty",
                )
            ),
            role_bonus=int(
                _number(
                    advanced_raw.get("role_bonus", 25),
                    "filters.advanced.role_bonus",
                )
            ),
            skill_bonus=int(
                _number(
                    advanced_raw.get("skill_bonus", 3),
                    "filters.advanced.skill_bonus",
                )
            ),
            description_bonus=int(
                _number(
                    advanced_raw.get("description_bonus", 8),
                    "filters.advanced.description_bonus",
                )
            ),
            missing_description_penalty=int(
                _number(
                    advanced_raw.get("missing_description_penalty", 10),
                    "filters.advanced.missing_description_penalty",
                )
            ),
            url_bonus=int(
                _number(
                    advanced_raw.get("url_bonus", 5),
                    "filters.advanced.url_bonus",
                )
            ),
            soft_reject_penalty=int(
                _number(
                    advanced_raw.get("soft_reject_penalty", 8),
                    "filters.advanced.soft_reject_penalty",
                )
            ),
            source_bonus=source_bonus,
        )

        filters = FiltersConfig(
            title_hard_reject=_string_list(
                filters_raw.get("title_hard_reject", []),
                "filters.title_hard_reject",
            ),
            description_hard_reject=_string_list(
                filters_raw.get("description_hard_reject", []),
                "filters.description_hard_reject",
            ),
            description_hard_reject_regex=_string_list(
                filters_raw.get("description_hard_reject_regex", []),
                "filters.description_hard_reject_regex",
            ),
            soft_reject=_string_list(
                filters_raw.get("soft_reject", []), "filters.soft_reject"
            ),
            soft_reject_regex=_string_list(
                filters_raw.get("soft_reject_regex", []),
                "filters.soft_reject_regex",
            ),
            skill_keywords=_string_list(
                filters_raw.get("skill_keywords", []), "filters.skill_keywords"
            ),
            advanced=advanced,
        )
        for field_name, patterns in (
            ("filters.description_hard_reject_regex", filters.description_hard_reject_regex),
            ("filters.soft_reject_regex", filters.soft_reject_regex),
        ):
            for pattern in patterns:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    raise ConfigError(f"Invalid regex in {field_name}: {pattern!r}") from exc

        selection_raw = _object(root.get("selection", {}), "selection")
        _reject_unknown(
            selection_raw,
            set(SelectionConfig.__dataclass_fields__),
            "selection",
        )
        selection = SelectionConfig(
            min_applicable_rate=_positive_int(
                selection_raw.get("min_applicable_rate", 60),
                "selection.min_applicable_rate",
                minimum=0,
            ),
            strong_applicable_rate=_positive_int(
                selection_raw.get("strong_applicable_rate", 70),
                "selection.strong_applicable_rate",
                minimum=0,
            ),
            min_jobs=_positive_int(
                selection_raw.get("min_jobs", 5), "selection.min_jobs", minimum=0
            ),
            max_jobs=_positive_int(
                selection_raw.get("max_jobs", 10), "selection.max_jobs"
            ),
            ai_candidate_limit=_positive_int(
                selection_raw.get("ai_candidate_limit", 40),
                "selection.ai_candidate_limit",
            ),
        )
        if selection.min_applicable_rate > 100 or selection.strong_applicable_rate > 100:
            raise ConfigError("selection score thresholds must be between 0 and 100")
        if selection.strong_applicable_rate < selection.min_applicable_rate:
            raise ConfigError(
                "selection.strong_applicable_rate must be greater than or equal to "
                "selection.min_applicable_rate"
            )
        if selection.min_jobs > selection.max_jobs:
            raise ConfigError("selection.min_jobs cannot exceed selection.max_jobs")

        documents_raw = _object(root.get("documents", {}), "documents")
        _reject_unknown(
            documents_raw,
            set(DocumentsConfig.__dataclass_fields__),
            "documents",
        )
        documents = DocumentsConfig(
            enabled=_boolean(documents_raw.get("enabled", True), "documents.enabled"),
            cv_language=_string(
                documents_raw.get("cv_language", "English"),
                "documents.cv_language",
                allow_empty=False,
            ),
            cover_letter_style=_string(
                documents_raw.get("cover_letter_style", "UK business tone"),
                "documents.cover_letter_style",
                allow_empty=False,
            ),
            include_right_to_work=_boolean(
                documents_raw.get("include_right_to_work", True),
                "documents.include_right_to_work",
            ),
        )

        notifications_raw = _object(root.get("notifications", {}), "notifications")
        _reject_unknown(
            notifications_raw,
            set(NotificationsConfig.__dataclass_fields__),
            "notifications",
        )
        notifications = NotificationsConfig(
            enabled=_boolean(
                notifications_raw.get("enabled", True), "notifications.enabled"
            ),
            recipient_override=_string(
                notifications_raw.get("recipient_override", ""),
                "notifications.recipient_override",
            ),
        )

        schedule_raw = _object(root.get("schedule", {}), "schedule")
        _reject_unknown(
            schedule_raw,
            set(ScheduleConfig.__dataclass_fields__),
            "schedule",
        )
        active_days = [
            day.casefold()
            for day in _string_list(
                schedule_raw.get(
                    "active_days",
                    ["monday", "tuesday", "wednesday", "thursday", "friday"],
                ),
                "schedule.active_days",
                allow_empty=False,
            )
        ]
        unknown_days = set(active_days) - set(WEEKDAYS)
        if unknown_days:
            raise ConfigError(
                "Unknown schedule.active_days values: " + ", ".join(sorted(unknown_days))
            )

        timezone_name = _string(
            schedule_raw.get("timezone", "Europe/London"),
            "schedule.timezone",
            allow_empty=False,
        )
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"Unknown schedule.timezone: {timezone_name}") from exc

        start_time = str(schedule_raw.get("start_time", "09:00"))
        end_time = str(schedule_raw.get("end_time", "17:00"))
        start = _parse_time(start_time, "schedule.start_time")
        end = _parse_time(end_time, "schedule.end_time")
        if start >= end:
            raise ConfigError("schedule.start_time must be earlier than schedule.end_time")

        schedule = ScheduleConfig(
            timezone=timezone_name,
            active_days=active_days,
            start_time=start_time,
            end_time=end_time,
            every_hours=_positive_int(
                schedule_raw.get("every_hours", 1), "schedule.every_hours"
            ),
        )

        market = _string(
            root.get("market", "UK"),
            "market",
            allow_empty=False,
        ).upper()
        if market != "UK":
            raise ConfigError("This version supports only market='UK'")

        return cls(
            candidate=candidate,
            search=search,
            filters=filters,
            selection=selection,
            documents=documents,
            notifications=notifications,
            schedule=schedule,
            market=market,
        )

    def scoring_fingerprint(self) -> str:
        payload = {
            "market": self.market,
            "target_roles": self.search.target_roles,
            "level_terms": self.search.level_terms,
            "filters": asdict(self.filters),
            "selection": asdict(self.selection),
            "scoring_prompt_version": "uk-fit-v1",
            "scoring_model": "gpt-4.1-mini",
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def merge_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        merged = dict(profile)
        overrides = asdict(self.candidate.contact_overrides)
        field_map = {"address": "current_location"}
        for key, value in overrides.items():
            if value:
                merged[field_map.get(key, key)] = value
        return merged

    def contact_context(self, profile: dict[str, Any]) -> dict[str, str]:
        merged = self.merge_profile(profile)
        return {
            "name": str(merged.get("name", "")),
            "email": str(merged.get("email", "")),
            "phone": str(merged.get("phone", "")),
            "linkedin": str(merged.get("linkedin", "")),
            "address": str(merged.get("current_location", "")),
            "right_to_work": str(merged.get("right_to_work", "")),
        }
