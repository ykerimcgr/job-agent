from __future__ import annotations

from dataclasses import dataclass

from app_config import AppConfig, MarketConfig


@dataclass(frozen=True)
class FilterConfig:
    """Shared filter settings merged with one market's additions."""

    market: MarketConfig
    hard_reject_title_keywords: list[str]
    hard_reject_description_keywords: list[str]
    hard_reject_description_regex: list[str]
    target_role_keywords: list[str]
    level_keywords: list[str]
    skill_keywords: list[str]
    soft_risk_keywords: list[str]
    soft_risk_regex: list[str]
    max_years_experience: int
    min_score: int
    max_score: int
    reject_if_missing_description: bool
    level_bonus: int
    missing_level_penalty: int
    role_bonus: int
    skill_bonus: int
    soft_risk_penalty: int

    @classmethod
    def for_market(cls, config: AppConfig, market: MarketConfig) -> "FilterConfig":
        filters = config.filters
        advanced = filters.advanced
        level_terms = config.search.level_terms if market.level_terms is None else market.level_terms
        return cls(
            market=market,
            hard_reject_title_keywords=filters.title_hard_reject + market.extra_title_hard_reject,
            hard_reject_description_keywords=(
                filters.description_hard_reject + market.extra_description_hard_reject
            ),
            hard_reject_description_regex=filters.description_hard_reject_regex,
            target_role_keywords=config.search.target_roles + market.extra_role_keywords,
            level_keywords=level_terms + market.extra_level_keywords,
            skill_keywords=filters.skill_keywords,
            soft_risk_keywords=filters.soft_reject,
            soft_risk_regex=filters.soft_reject_regex,
            max_years_experience=filters.max_years_experience,
            min_score=advanced.min_pre_score,
            max_score=advanced.max_score,
            reject_if_missing_description=advanced.reject_missing_description,
            level_bonus=advanced.level_bonus,
            missing_level_penalty=advanced.missing_level_penalty,
            role_bonus=advanced.role_bonus,
            skill_bonus=advanced.skill_bonus,
            soft_risk_penalty=advanced.soft_reject_penalty,
        )
