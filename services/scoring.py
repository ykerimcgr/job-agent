from __future__ import annotations

import json

from app_config import AppConfig
from services.openai_client import get_openai_client


SCORING_MODEL = "gpt-4.1-mini"
SCORING_PROMPT_VERSION = "uk-fit-v1"


def clean_json(content: str) -> str:
    if not content:
        raise ValueError("Empty response from model")
    content = content.strip()
    if content.startswith("```"):
        content = content.replace("```json", "").replace("```", "").strip()
    start = content.find("{")
    end = content.rfind("}")
    return content[start : end + 1] if start != -1 and end != -1 else content


def normalise_decision_scores(result: dict) -> dict:
    decision = result.get("application_decision", {})
    for field in [
        "application_worthiness",
        "cv_tailoring_potential",
        "domain_gap_risk",
        "red_flag_severity",
        "competition_risk",
        "time_investment_priority",
    ]:
        value = decision.get(field, 0)
        if isinstance(value, (int, float)) and value > 10:
            value = round(value / 10, 1)
        if isinstance(value, (int, float)):
            decision[field] = max(0, min(10, value))
    result["application_decision"] = decision
    return result


def score_job(
    job_text: str,
    parsed_job: dict,
    profile: dict,
    config: AppConfig,
) -> dict:
    preferences = {
        "market": config.market,
        "target_roles": config.search.target_roles,
        "target_levels": config.search.level_terms,
        "skills_of_interest": config.filters.skill_keywords,
        "minimum_application_rate": config.selection.min_applicable_rate,
        "strong_application_rate": config.selection.strong_applicable_rate,
    }
    prompt = f"""
You are an international recruiter, ATS analyst, and career strategist.

Evaluate the candidate for a United Kingdom job. UK right-to-work information
is relevant when it exists. Never invent eligibility or candidate evidence.

Your task has two parts:
1. Evaluate how well the candidate fits the job.
2. Decide whether applying is worth the candidate's time.

Important distinction:
- final_score measures candidate-to-job fit.
- applicable_rate measures whether the job is worth applying to after fit,
  risks, realistic CV tailoring potential, and time investment.

Candidate search preferences:
{json.dumps(preferences, indent=2)}

Calibration:
- final_score and applicable_rate use 0-100.
- All component scores use 0-10.
- 90-100 exceptional; 80-89 strong; 70-79 good; 60-69 partial;
  50-59 weak/strategic; below 50 skip.
- Be strict. Do not reward a degree or general analytical ability as though it
  were direct domain experience.
- If direct core-domain experience is absent, final_score should usually not
  exceed 75.
- If multiple core requirements are absent, final_score should usually not
  exceed 65.
- Tailoring potential helps only when gaps are realistically fixable without
  inventing facts.

Candidate profile:
{json.dumps(profile, indent=2)}

Parsed job:
{json.dumps(parsed_job, indent=2)}

Original job text:
{job_text}

Return ONLY valid JSON with this exact structure:
{{
  "status": "scored",
  "fit_analysis": {{
    "final_score": 0,
    "role_fit": 0,
    "skill_fit": 0,
    "experience_fit": 0,
    "location_fit": 0,
    "keyword_fit": 0,
    "strengths": [],
    "weaknesses": [],
    "recommended_cv_changes": []
  }},
  "application_decision": {{
    "applicable_rate": 0,
    "decision": "strong_apply / apply_after_cv_tailoring / backup_option / skip",
    "priority": "high / medium_high / medium / low",
    "application_worthiness": 0,
    "cv_tailoring_potential": 0,
    "domain_gap_risk": 0,
    "red_flag_severity": 0,
    "competition_risk": 0,
    "time_investment_priority": 0,
    "reasoning": "",
    "top_application_angle": "",
    "what_to_fix_before_applying": []
  }}
}}
"""
    response = get_openai_client().chat.completions.create(
        model=SCORING_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    result = json.loads(clean_json(response.choices[0].message.content))
    return normalise_decision_scores(result)
