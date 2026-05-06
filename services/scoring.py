from openai import OpenAI
from dotenv import load_dotenv
import json
import os

load_dotenv()

API_KEY = os.environ.get("OPEN_AI_SECRET_KEY", None)
client = OpenAI(api_key=API_KEY)

VALID_DECISIONS = {"strong_apply", "apply", "maybe", "reject"}
VALID_CONFIDENCE = {"high", "medium", "low"}


def clean_json(content: str) -> str:
    if not content:
        raise ValueError("Empty response from model")

    content = content.strip()

    # Remove markdown JSON block if model returns ```json ... ```
    if content.startswith("```"):
        content = content.replace("```json", "").replace("```", "").strip()

    # Extra safety: keep only JSON object
    start = content.find("{")
    end = content.rfind("}")

    if start != -1 and end != -1:
        content = content[start:end + 1]

    return content

def normalise_decision_scores(result: dict) -> dict:
    decision = result.get("application_decision", {})

    ten_scale_fields = [
        "application_worthiness",
        "cv_tailoring_potential",
        "domain_gap_risk",
        "red_flag_severity",
        "competition_risk",
        "time_investment_priority"
    ]

    for field in ten_scale_fields:
        value = decision.get(field, 0)

        if isinstance(value, (int, float)) and value > 10:
            decision[field] = round(value / 10, 1)

        if isinstance(value, (int, float)):
            decision[field] = max(0, min(10, decision[field]))

    result["application_decision"] = decision
    return result


def normalize_score_result(score_result: dict) -> dict:
    score_result = score_result if isinstance(score_result, dict) else {}
    fit_analysis = score_result.get("fit_analysis", {})
    if not isinstance(fit_analysis, dict):
        fit_analysis = {}
    application_decision = score_result.get("application_decision", {})
    if not isinstance(application_decision, dict):
        application_decision = {}

    raw_score = score_result.get("score")
    if not isinstance(raw_score, (int, float)):
        raw_score = fit_analysis.get("final_score")
    if not isinstance(raw_score, (int, float)):
        raw_score = application_decision.get("applicable_rate")
    if not isinstance(raw_score, (int, float)):
        raw_score = 0

    score = max(0, min(100, int(round(raw_score))))

    decision_value = (
        score_result.get("decision")
        or application_decision.get("decision")
        or ""
    )
    decision_map = {
        "strong_apply": "strong_apply",
        "apply": "apply",
        "apply_after_cv_tailoring": "apply",
        "backup_option": "maybe",
        "maybe": "maybe",
        "skip": "reject",
        "reject": "reject",
    }
    decision = decision_map.get(str(decision_value).strip().lower())
    if decision not in VALID_DECISIONS:
        if score >= 80:
            decision = "strong_apply"
        elif score >= 65:
            decision = "apply"
        elif score >= 50:
            decision = "maybe"
        else:
            decision = "reject"

    confidence_value = str(score_result.get("confidence") or "").strip().lower()
    if confidence_value in VALID_CONFIDENCE:
        confidence = confidence_value
    else:
        confidence = "high" if score >= 80 else "medium" if score >= 60 else "low"

    strengths = score_result.get("strengths") or fit_analysis.get("strengths") or []
    weaknesses = score_result.get("weaknesses") or fit_analysis.get("weaknesses") or []
    risks = score_result.get("risks") or application_decision.get("risks") or []

    main_reason = (
        score_result.get("main_reason")
        or application_decision.get("reasoning")
        or application_decision.get("top_application_angle")
        or fit_analysis.get("summary")
        or (strengths[0] if isinstance(strengths, list) and strengths else "")
        or "Relevant role based on the available profile and job description."
    )
    main_reason = str(main_reason).strip() or "Relevant role based on the available profile and job description."

    main_risk = (
        score_result.get("main_risk")
        or application_decision.get("main_risk")
        or (risks[0] if isinstance(risks, list) and risks else "")
        or (weaknesses[0] if isinstance(weaknesses, list) and weaknesses else "")
        or "No major risk identified from the available information."
    )
    main_risk = str(main_risk).strip() or "No major risk identified from the available information."

    apply_strategy = (
        score_result.get("apply_strategy")
        or application_decision.get("apply_strategy")
        or application_decision.get("top_application_angle")
    )
    if not apply_strategy:
        if decision in {"strong_apply", "apply"}:
            apply_strategy = "Apply with a tailored CV focused on the strongest matching skills and responsibilities."
        elif decision == "maybe":
            apply_strategy = "Review the role carefully and apply only if the responsibilities match your goals."
        else:
            apply_strategy = "Do not prioritise this role unless there is a strong personal reason."
    apply_strategy = str(apply_strategy).strip() or "Do not prioritise this role unless there is a strong personal reason."

    return {
        "score": score,
        "decision": decision,
        "confidence": confidence,
        "main_reason": main_reason,
        "main_risk": main_risk,
        "apply_strategy": apply_strategy,
    }


def score_job(
    job_text: str,
    parsed_job: dict,
    profile: dict,
    contact_rules: dict,
    location_rules: dict
) -> dict:
    prompt = f"""
You are an international recruiter, ATS analyst, and career strategist.

Evaluate the candidate according to the job's actual location and market context.

Important location rules:
- If the job is in London or the UK, UK right-to-work information is relevant.
- If the job is in Istanbul or Turkey, UK Graduate Visa information is irrelevant.
- For Istanbul/Turkey jobs, do NOT reward or penalise the candidate because of UK Graduate Visa.
- Location fit must be based on the correct contact/location profile for the job market.
- Use contact_rules and location_rules when judging location fit.

Your task has two parts:

PART 1 — FIT ANALYSIS:
Evaluate how well the candidate fits this job.

PART 2 — APPLICATION DECISION:
Decide whether this job is worth applying to and whether it should appear in the candidate's daily Top 10 job list.

Important distinction:
- final_score = how well the candidate fits the job
- applicable_rate = whether the job is worth applying to after considering fit, risks, CV tailoring potential, and time investment

Scoring calibration rules:

Be strict. Do not inflate scores.

final_score:
90-100 = exceptional match, almost all core requirements met
80-89 = strong match, minor gaps only
70-79 = good match, some fixable gaps
60-69 = partial match, several important gaps
50-59 = weak match, apply only if strategic
below 50 = skip

applicable_rate:
90-100 = must apply today
80-89 = strong apply after tailoring
70-79 = apply if enough time
60-69 = backup only
below 60 = skip

Important:
- If the candidate lacks direct experience in the role's core domain, final_score should usually not exceed 75.
- If the candidate lacks multiple core requirements, final_score should usually not exceed 65.
- If the role requires production ML/cloud/commercial systems and the candidate lacks them, cap final_score at 70.
- Do not give high scores just because the candidate is analytical or has a good degree.
- Do not give high applicable_rate if the job requires several core skills the candidate does not have.
- CV tailoring potential should increase applicable_rate only if the gaps are realistically fixable.

Scale rules:
- final_score and applicable_rate must be 0 to 100.
- role_fit, skill_fit, experience_fit, location_fit, keyword_fit must be 0 to 10.
- application_worthiness, cv_tailoring_potential, domain_gap_risk, red_flag_severity, competition_risk, time_investment_priority must be 0 to 10.

Even if the decision is "skip", still provide:
- top_application_angle (if candidate insists on applying)
- what_to_fix_before_applying (at least 2 items)

Candidate profile:
{json.dumps(profile, indent=2)}

Contact rules:
{json.dumps(contact_rules, indent=2)}

Location rules:
{json.dumps(location_rules, indent=2)}

Parsed job:
{json.dumps(parsed_job, indent=2)}

Original job text:
{job_text}

Return ONLY valid JSON.
No markdown.
No explanation outside JSON.

JSON structure:
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

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    content = response.choices[0].message.content

    cleaned = clean_json(content)
    result = json.loads(cleaned)

    result = normalise_decision_scores(result)

    return result
