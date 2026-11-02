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
    description_hard_reject_regex: List[Pattern[str]]
    target_roles: KeywordMatcher
    role_families: KeywordMatcher
    levels: KeywordMatcher
    skills: KeywordMatcher
    soft_risks: KeywordMatcher
    soft_risk_regex: List[Pattern[str]]

    @classmethod
    def from_config(cls, config: FilterConfig) -> "Matchers":
        return cls(
            title_hard_reject=KeywordMatcher(config.hard_reject_title_keywords),
            description_hard_reject=KeywordMatcher(config.hard_reject_description_keywords),
            description_hard_reject_regex=[
                re.compile(pattern, flags=re.IGNORECASE)
                for pattern in config.hard_reject_description_regex
            ],
            target_roles=KeywordMatcher(config.target_role_keywords),
            # Last word of each role ("Analyst", "Analisti"): a title in the same family.
            role_families=KeywordMatcher(
                {role.split()[-1] for role in config.target_role_keywords if role.split()}
            ),
            levels=KeywordMatcher(config.level_keywords),
            skills=KeywordMatcher(config.skill_keywords),
            soft_risks=KeywordMatcher(config.soft_risk_keywords),
            soft_risk_regex=[
                re.compile(pattern, flags=re.IGNORECASE)
                for pattern in config.soft_risk_regex
            ],
        )
