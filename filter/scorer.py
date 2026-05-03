from __future__ import annotations

from typing import List

from .config import FilterConfig
from .location import LocationMatcher
from .matcher import Matchers
from .normalizer import normalize_job
from .types import Job, NormalizedJob, ScoreResult


class JobScorer:
    def __init__(
        self,
        config: FilterConfig,
        matchers: Matchers,
        location_matcher: LocationMatcher,
    ) -> None:
        self.config = config
        self.matchers = matchers
        self.location_matcher = location_matcher

    def score(self, job: Job) -> ScoreResult:
        normalized = normalize_job(job)

        score = 0
        quality_flags: List[str] = []
        risk_flags: List[str] = []

        if self.location_matcher.is_target_location(normalized):
            score += self.config.location_score
            quality_flags.append("location_match")
        else:
            risk_flags.append("location_mismatch")

        if normalized.description:
            score += self.config.description_bonus
            quality_flags.append("has_description")
        else:
            score -= self.config.missing_description_penalty
            risk_flags.append("missing_description")

        if normalized.target_location == "London":
            score += self._score_london(
                normalized=normalized,
                quality_flags=quality_flags,
                risk_flags=risk_flags,
            )

        elif normalized.target_location == "Istanbul":
            score += self._score_istanbul(
                normalized=normalized,
                quality_flags=quality_flags,
                risk_flags=risk_flags,
            )

        else:
            risk_flags.append("unknown_target_location")

        skill_matches = self.matchers.skills.find_matches(normalized.full_text)

        if skill_matches:
            score += len(skill_matches) * self.config.skill_bonus
            quality_flags.extend(
                [f"skill:{skill}" for skill in skill_matches]
            )

        for source_name, bonus in self.config.source_bonus.items():
            if source_name in normalized.source:
                score += bonus
                quality_flags.append(f"source:{source_name}")
                break

        if normalized.url:
            score += self.config.url_bonus
            quality_flags.append("has_url")

        soft_risks = self.matchers.soft_risks.find_matches(normalized.full_text)

        if soft_risks:
            score -= len(soft_risks) * self.config.soft_risk_penalty
            risk_flags.extend(
                [f"soft_risk:{risk}" for risk in soft_risks]
            )

        score = max(0, min(self.config.max_score, score))

        return ScoreResult(
            score=score,
            quality_flags=quality_flags,
            risk_flags=risk_flags,
        )

    def _score_london(
        self,
        normalized: NormalizedJob,
        quality_flags: List[str],
        risk_flags: List[str],
    ) -> int:
        score = 0

        level_matches = self.matchers.levels.find_matches(normalized.title)

        if not level_matches and normalized.description:
            level_matches = self.matchers.levels.find_matches(
                normalized.description
            )

        if level_matches:
            score += self.config.london_level_bonus
            quality_flags.extend(
                [f"level:{level}" for level in level_matches]
            )
        else:
            score -= self.config.london_missing_level_penalty
            risk_flags.append("not_explicitly_junior")

        role_matches = self.matchers.target_roles.find_matches(
            normalized.title
        )

        if role_matches:
            score += self.config.london_role_bonus
            quality_flags.append(f"role:{role_matches[0]}")
        else:
            weak_role_matches = self.matchers.target_roles.find_matches(
                normalized.full_text
            )

            if weak_role_matches:
                score += int(self.config.london_role_bonus * 0.5)
                quality_flags.append(f"role_weak:{weak_role_matches[0]}")
            else:
                risk_flags.append("no_target_role_match")

        return score

    def _score_istanbul(
        self,
        normalized: NormalizedJob,
        quality_flags: List[str],
        risk_flags: List[str],
    ) -> int:
        score = 0

        tr_role_matches = self.matchers.istanbul_roles.find_matches(
            normalized.title
        )

        if tr_role_matches:
            score += self.config.istanbul_role_bonus
            quality_flags.append(f"istanbul_role:{tr_role_matches[0]}")

        en_role_matches = self.matchers.target_roles.find_matches(
            normalized.title
        )

        if en_role_matches:
            score += self.config.istanbul_english_role_bonus
            quality_flags.append(f"english_role:{en_role_matches[0]}")

        if not tr_role_matches and not en_role_matches:
            risk_flags.append("no_istanbul_role_match")

        return score