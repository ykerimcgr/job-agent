from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Pattern, Tuple

from .config import FilterConfig
from .normalizer import TextNormalizer


class KeywordMatcher:
    def __init__(self, keywords: Iterable[str]) -> None:
        self.patterns: List[Tuple[str, Pattern[str]]] = [
            (keyword, self._compile_keyword(keyword))
            for keyword in keywords
            if keyword and keyword.strip()
        ]

    @staticmethod
    def _compile_keyword(keyword: str) -> Pattern[str]:
        normalized = TextNormalizer.normalize(keyword)

        escaped = re.escape(normalized)
        escaped = escaped.replace(r"\ ", r"\s+")

        pattern = rf"(?<!\w){escaped}(?!\w)"
        return re.compile(pattern, flags=re.IGNORECASE)

    def find_matches(self, text: str) -> List[str]:
        if not text:
            return []

        return [
            keyword
            for keyword, pattern in self.patterns
            if pattern.search(text)
        ]

    def has_match(self, text: str) -> bool:
        return bool(self.find_matches(text))


@dataclass
class Matchers:
    title_hard_reject: KeywordMatcher
    description_hard_reject: KeywordMatcher
    target_roles: KeywordMatcher
    istanbul_roles: KeywordMatcher
    levels: KeywordMatcher
    skills: KeywordMatcher
    soft_risks: KeywordMatcher

    @classmethod
    def from_config(cls, config: FilterConfig) -> "Matchers":
        return cls(
            title_hard_reject=KeywordMatcher(config.hard_reject_title_keywords),
            description_hard_reject=KeywordMatcher(config.hard_reject_description_keywords),
            target_roles=KeywordMatcher(config.target_role_keywords),
            istanbul_roles=KeywordMatcher(config.istanbul_role_keywords),
            levels=KeywordMatcher(config.level_keywords),
            skills=KeywordMatcher(config.skill_keywords),
            soft_risks=KeywordMatcher(config.soft_risk_keywords),
        )