import json
from services.openai_client import get_openai_client


def parse_job_description(job_text: str) -> dict:
    prompt = f"""
You are a professional job description parser.

Your task is to extract structured job information from the provided job description.

Rules:
- Do NOT invent information.
- If a field is not available, use an empty string or empty list.
- Return ONLY valid JSON.
- No markdown.
- No explanation.

Return this JSON structure:

{{
  "title": "",
  "company": "",
  "location": "",
  "work_model": "",
  "employment_type": "",
  "salary_range": "",
  "required_skills": [],
  "nice_to_have_skills": [],
  "responsibilities": [],
  "requirements": [],
  "years_of_experience": "",
  "role_level": "",
  "keywords": [],
  "red_flags": []
}}

Job description:
{job_text}
"""

    response = get_openai_client().chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    content = response.choices[0].message.content

    return json.loads(content)
