import json
from services.openai_client import get_openai_client


PROFILE_MODEL = "gpt-6-luna"
PROFILE_PROMPT_VERSION = "candidate-profile-v1"


def extract_profile_from_cv(cv_text: str) -> dict:
    prompt = f"""
You are a professional CV parser and career analyst.

Your task is to extract structured candidate information from the provided LaTeX CV.

Rules:
- Do NOT invent information.
- Do NOT include LaTeX commands.
- Keep facts accurate.
- Return ONLY valid JSON.
- No markdown.
- No explanation.

Return this JSON structure:

{{
  "name": "",
  "current_location": "",
  "email": "",
  "phone": "",
  "linkedin": "",
  "professional_summary": "",
  "education": [
    {{
      "degree": "",
      "institution": "",
      "location": "",
      "years": "",
      "details": []
    }}
  ],
  "experience": [
    {{
      "role": "",
      "company": "",
      "location": "",
      "duration": "",
      "responsibilities": [],
      "achievements": []
    }}
  ],
  "skills": [],
  "tools": [],
  "languages": [],
  "right_to_work": "",
  "strengths": [],
  "target_roles": [],
  "seniority_level": ""
}}

CV:
{cv_text}
"""

    response = get_openai_client().chat.completions.create(
        model=PROFILE_MODEL,
        messages=[
            {"role": "user", "content": prompt}
        ],
        reasoning_effort="low",
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content

    return json.loads(content)
