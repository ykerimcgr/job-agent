from __future__ import annotations

from typing import List

from .config import FilterConfig
from .matcher import Matchers
from .normalizer import normalize_job
from .types import Job, NormalizedJob, ScoreResult


class JobScorer:
    def __init__(
        self,
        config: FilterConfig,
        matchers: Matchers,
    ) -> None:
        self.config = config
        self.matchers = matchers

    def score(self, job: Job) -> ScoreResult:
        normalized = normalize_job(job)
        score = 0
        quality_flags: List[str] = []
        risk_flags: List[str] = []

        score += self._score_role_and_level(normalized, quality_flags, risk_flags)

        skill_matches = self.matchers.skills.find_matches(normalized.full_text)
        if skill_matches:
            score += len(skill_matches) * self.config.skill_bonus
            quality_flags.extend(f"skill:{skill}" for skill in skill_matches)

        soft_risks = self.matchers.soft_risks.find_matches(normalized.full_text)
        regex_risks = [
            pattern.pattern
            for pattern in self.matchers.soft_risk_regex
            if pattern.search(normalized.full_text)
        ]
        all_soft_risks = soft_risks + regex_risks
        if all_soft_risks:
            score -= len(all_soft_risks) * self.config.soft_risk_penalty
            risk_flags.extend(f"soft_risk:{risk}" for risk in all_soft_risks)

        score = max(0, min(self.config.max_score, score))
        return ScoreResult(
            score=score,
            quality_flags=quality_flags,
            risk_flags=risk_flags,
        )

    def _score_role_and_level(
        self,
        normalized: NormalizedJob,
        quality_flags: List[str],
        risk_flags: List[str],
    ) -> int:
        score = 0
        # Title only: "graduate degree required" in a senior description is not a level signal.
        level_matches = self.matchers.levels.find_matches(normalized.title)

        if level_matches:
            score += self.config.level_bonus
            quality_flags.extend(f"level:{level}" for level in level_matches)
        else:
            score -= self.config.missing_level_penalty
            risk_flags.append("not_explicitly_target_level")

        role_matches = self.matchers.target_roles.find_matches(normalized.title)
        if role_matches:
            score += self.config.role_bonus
            quality_flags.append(f"role:{role_matches[0]}")
        elif family := self.matchers.role_families.find_matches(normalized.title):
            score += int(self.config.role_bonus * 0.5)
            quality_flags.append(f"role_family:{family[0]}")
        elif weak := self.matchers.target_roles.find_matches(normalized.description):
            score += int(self.config.role_bonus * 0.25)
            quality_flags.append(f"role_weak:{weak[0]}")
        else:
            risk_flags.append("no_target_role_match")

        return score
