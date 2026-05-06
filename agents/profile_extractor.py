from openai import OpenAI
from dotenv import load_dotenv
import os
from services.llm_json import parse_llm_json

load_dotenv()

key = os.environ.get("OPEN_AI_SECRET_KEY", None)

client = OpenAI(api_key= key )


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

    response = client.chat.completions.create(
        model="gpt-5.4-nano",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    content = response.choices[0].message.content

    return parse_llm_json(content)
