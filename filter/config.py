from __future__ import annotations

from dataclasses import dataclass

from app_config import AppConfig


@dataclass(frozen=True)
class FilterConfig:
    market: str
    hard_reject_title_keywords: list[str]
    hard_reject_description_keywords: list[str]
    hard_reject_description_regex: list[str]
    target_role_keywords: list[str]
    level_keywords: list[str]
    skill_keywords: list[str]
    soft_risk_keywords: list[str]
    soft_risk_regex: list[str]
    source_bonus: dict[str, int]
    min_score: int
    max_score: int
    reject_if_missing_description: bool
    location_score: int
    level_bonus: int
    missing_level_penalty: int
    role_bonus: int
    skill_bonus: int
    description_bonus: int
    missing_description_penalty: int
    url_bonus: int
    soft_risk_penalty: int

    @classmethod
    def from_app_config(cls, config: AppConfig) -> "FilterConfig":
        advanced = config.filters.advanced
        return cls(
            market=config.market,
            hard_reject_title_keywords=config.filters.title_hard_reject,
            hard_reject_description_keywords=config.filters.description_hard_reject,
            hard_reject_description_regex=config.filters.description_hard_reject_regex,
            target_role_keywords=config.search.target_roles,
            level_keywords=config.search.level_terms,
            skill_keywords=config.filters.skill_keywords,
            soft_risk_keywords=config.filters.soft_reject,
            soft_risk_regex=config.filters.soft_reject_regex,
            source_bonus=advanced.source_bonus,
            min_score=advanced.min_pre_score,
            max_score=advanced.max_score,
            reject_if_missing_description=advanced.reject_missing_description,
            location_score=advanced.location_score,
            level_bonus=advanced.level_bonus,
            missing_level_penalty=advanced.missing_level_penalty,
            role_bonus=advanced.role_bonus,
            skill_bonus=advanced.skill_bonus,
            description_bonus=advanced.description_bonus,
            missing_description_penalty=advanced.missing_description_penalty,
            url_bonus=advanced.url_bonus,
            soft_risk_penalty=advanced.soft_reject_penalty,
        )
