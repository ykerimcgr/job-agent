from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel

from app_config import AppConfig, MarketConfig
from services.openai_client import structured_completion


SCORING_MODEL = "gpt-4.1-mini"
SCORING_PROMPT_VERSION = "fit-v5"
STATUS_POINTS = {"met": 1.0, "partial": 0.5, "missing": 0.0}
LEVEL_PENALTY = {"mid": 15, "senior": 35}
ADJACENT_ROLE_PENALTY = 15
UNRELATED_ROLE_CAP = 45  # below min_applicable_rate, so off-target roles never get picked


class Requirement(BaseModel):
    requirement: str
    importance: Literal["must", "nice"]
    status: Literal["met", "partial", "missing"]
    evidence: str


class JobAssessment(BaseModel):
    role_match: Literal["direct", "adjacent", "unrelated"]
    role_level: Literal["entry", "junior", "mid", "senior", "unclear"]
    years_required: int | None
    work_model: Literal["onsite", "hybrid", "remote", "unclear"]
    blockers: list[str]
    requirements: list[Requirement]
    strengths: list[str]
    gaps: list[str]
    application_angle: str
    reasoning: str


def effective_level_terms(config: AppConfig, market: MarketConfig) -> list[str]:
    return config.search.level_terms if market.level_terms is None else market.level_terms


def scoring_fingerprint(config: AppConfig, market: MarketConfig) -> str:
    """Everything that changes the prompt or model; thresholds are applied after the cache."""
    payload = {
        "market": [market.code, market.search_location, market.scoring_notes],
        "target_roles": config.search.target_roles,
        "level_terms": effective_level_terms(config, market),
        "prompt_version": SCORING_PROMPT_VERSION,
        "model": SCORING_MODEL,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _coverage(requirements: list[Requirement]) -> float:
    if not requirements:
        return 1.0
    return sum(STATUS_POINTS[r.status] for r in requirements) / len(requirements)


def applicable_rate(assessment: JobAssessment, max_years_experience: int) -> int:
    """0-100. Deterministic, so the spread comes from evidence, not from the model's taste in numbers."""
    must = [r for r in assessment.requirements if r.importance == "must"]
    nice = [r for r in assessment.requirements if r.importance == "nice"]
    rate = 70 * _coverage(must) + 30 * _coverage(nice)
    rate -= LEVEL_PENALTY.get(assessment.role_level, 0)
    if assessment.years_required and assessment.years_required > max_years_experience:
        rate -= 10 * (assessment.years_required - max_years_experience)
    if assessment.role_match == "adjacent":
        rate -= ADJACENT_ROLE_PENALTY
    elif assessment.role_match == "unrelated":
        rate = min(rate, UNRELATED_ROLE_CAP)
    if assessment.blockers:
        rate = min(rate, 40)
    return int(round(max(0, min(100, rate))))


def build_score_result(assessment: JobAssessment, config: AppConfig) -> dict:
    rate = applicable_rate(assessment, config.filters.max_years_experience)
    selection = config.selection
    if rate >= selection.strong_applicable_rate:
        decision = "strong_apply"
    elif rate >= selection.min_applicable_rate:
        decision = "apply"
    else:
        decision = "skip"
    return {
        "status": "scored",
        "application_decision": {
            "applicable_rate": rate,
            "decision": decision,
            "reasoning": assessment.reasoning,
            "top_application_angle": assessment.application_angle,
            "what_to_fix_before_applying": assessment.gaps,
        },
        "assessment": assessment.model_dump(),
    }


def assess_job(job: dict, profile: dict, config: AppConfig, market: MarketConfig) -> JobAssessment:
    preferences = {
        "target_roles": config.search.target_roles,
        "target_levels": effective_level_terms(config, market),
        "max_years_experience": config.filters.max_years_experience,
    }
    prompt = f"""
You are a strict recruiter screening one job for one candidate.
Judge only from the evidence given. Never invent candidate experience.

Market: {market.code}, searching around {market.search_location}.
{market.scoring_notes}

Candidate search preferences:
{json.dumps(preferences, indent=2)}

Candidate profile:
{json.dumps(profile, indent=2, ensure_ascii=False)}

Job:
- Title: {job.get("title", "")}
- Company: {job.get("company", "")}
- Location: {job.get("location", "")}
- Description:
{job.get("description", "")}

Instructions:
- role_match: compare the job's core day-to-day duties (not the title alone) with target_roles.
  "direct" = the duties are those of one of the target_roles or a close variant.
  "adjacent" = a general graduate, rotational or trainee scheme, or a role in another field where
  target-role work is a large part of the job.
  "unrelated" = the core work is a discipline that none of the target_roles covers (for example
  engineering, actuarial, HR, sales), even if the title says Graduate, Analyst or Specialist.
- requirements: the job's 4-10 most important requirements.
  importance = "must" for anything stated as required/essential/must, "nice" for preferred/desirable.
  status = "met" only with direct evidence in the profile (put that evidence in `evidence`);
  "partial" for related or transferable evidence; "missing" otherwise.
  A degree or general analytical ability alone is "partial", never "met", for a domain-specific requirement.
- role_level: the seniority the job actually hires for, judged from duties and requirements, not the title alone.
- years_required: the minimum years of experience the job states, or null. Also null when
  the job accepts an academic or project background instead of that experience.
- blockers: only hard stops that the job EXPLICITLY states and the candidate clearly cannot meet
  (a language the candidate does not speak, nationality or security clearance, a professional
  licence, work authorisation the candidate lacks, a driving licence or car). Missing skills or
  experience are never blockers; they belong in requirements. If you are unsure, or the job does
  not state it, leave it out. Never list something and then say it is not a blocker. Empty if none.
- strengths / gaps: short phrases.
- application_angle: the strongest honest pitch for this candidate.
- reasoning: one or two sentences on fit.
"""
    return structured_completion(prompt, JobAssessment, model=SCORING_MODEL)
