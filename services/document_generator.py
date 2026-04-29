import json
import re
import subprocess
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.environ.get("OPEN_AI_SECRET_KEY", None)

client = OpenAI(api_key=API_KEY)

APPLICATIONS_DIR = Path("outputs/applications")
APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)


def safe_name(value: str) -> str:
    value = value or "Unknown"
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    return value.strip("_")


def clean_json(content: str) -> str:
    if not content:
        raise ValueError("Empty response from model")

    content = content.strip()

    if content.startswith("```"):
        content = content.replace("```json", "").replace("```", "").strip()

    start = content.find("{")
    end = content.rfind("}")

    if start != -1 and end != -1:
        content = content[start:end + 1]

    return content


def get_application_location(job: dict) -> str:
    target_location = job.get("target_location", "")

    if target_location in ["London", "Istanbul"]:
        return target_location

    location = (job.get("location") or "").lower()

    if "london" in location:
        return "London"

    if "istanbul" in location or "i̇stanbul" in location or "turkey" in location or "türkiye" in location:
        return "Istanbul"

    return "London"


def compile_latex(tex_path: Path):
    try:
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_path.name],
            cwd=tex_path.parent,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )

        # cleanup auxiliary files
        for ext in [".aux", ".log", ".out"]:
            aux_file = tex_path.with_suffix(ext)
            if aux_file.exists():
                aux_file.unlink()

    except Exception as e:
        print(f"PDF compile failed for {tex_path}: {e}")


def generate_documents_for_job(
    job_item: dict,
    profile: dict,
    master_cv_text: str,
    contact_rules: dict,
    location_rules: dict
) -> dict:
    job = job_item.get("job", {})
    score_result = job_item.get("score_result", {})

    company = job.get("company", "Unknown Company")
    title = job.get("title", "Unknown Role")
    description = job.get("description", "")

    application_location = get_application_location(job)

    contact_context = contact_rules.get(application_location, {})
    location_context = location_rules.get(application_location, {})

    company_safe = safe_name(company)

    company_dir = APPLICATIONS_DIR / company_safe
    company_dir.mkdir(parents=True, exist_ok=True)

    cv_filename = f"Yusuf_Ciger_CV_{company_safe}.tex"
    cover_filename = f"Yusuf_Ciger_Cover_Letter_{company_safe}.tex"

    cv_path = company_dir / cv_filename
    cover_path = company_dir / cover_filename

    prompt = f"""
You are a professional CV and cover letter tailoring assistant for international job applications.

You must generate:
1. A tailored LaTeX CV
2. A tailored LaTeX Cover Letter

Application location:
{application_location}

Contact context to use:
{json.dumps(contact_context, indent=2)}

Location rules:
{json.dumps(location_context, indent=2)}

Candidate profile:
{json.dumps(profile, indent=2)}

Master CV LaTeX, SOURCE OF TRUTH:
{master_cv_text}

Job title:
{title}

Company:
{company}

Job description:
{description}

AI scoring insights:
{json.dumps(score_result, indent=2)}

STRICT RULES:
- Use the master CV as the only source of truth.
- Do not invent experience, tools, companies, achievements, education, certifications, dates, or metrics.
- You may reorder and rephrase content, but you must not create new facts.
- The CV must be ATS-friendly and ideally one page.
- Use the correct phone number, email, LinkedIn, and address from contact_context.
- If application_location is London, include right-to-work information if available in contact_context.
- If application_location is Istanbul, do not mention UK Graduate Visa or UK right-to-work.
- Both documents must be in English.
- Do not use em dashes. Do not use this character: —
- Use commas, periods, or parentheses instead of em dashes.

WRITING STYLE RULES:
- Write like a real human, not like AI.
- Be concise, specific, and natural.
- Avoid generic phrases such as "I am excited to apply" or "I am writing to express my interest" unless absolutely necessary.
- Avoid exaggerated language.
- Avoid long paragraphs.
- Prioritise relevance to the job description.

COVER LETTER FORMAT:
- Use bullet-style T-format, not a table.
- Do not use tabular, longtable, or table environments for the cover letter.
- Structure the cover letter as:
  1. Short opening paragraph, maximum 2 to 3 lines.
  2. A section titled "Key Fit".
  3. Bullet points where each bullet follows this format:
     Requirement: short requirement from the job
     Evidence: specific evidence from the candidate's CV
  4. Short closing paragraph, maximum 2 to 3 lines.
- Each Key Fit bullet must be short and scannable.
- Each bullet must match one job requirement with one piece of evidence.
- Do not write long explanations inside bullets.
- Use 4 to 6 Key Fit bullets maximum.

LATEX RULES:
- Return complete compilable LaTeX documents for both files.
- Use simple ATS-friendly LaTeX.
- Avoid complex tables.
- Avoid icons unless they already exist in the master CV.
- Escape LaTeX special characters where needed.
- Keep layout clean and readable.

Return ONLY valid JSON.
Do not use markdown.
Do not add explanation outside JSON.

JSON structure:
{{
  "tailored_cv_tex": "",
  "cover_letter_tex": ""
}}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    content = response.choices[0].message.content
    cleaned = clean_json(content)
    docs = json.loads(cleaned)

    cv_tex = docs.get("tailored_cv_tex", "")
    cover_tex = docs.get("cover_letter_tex", "")

    cv_tex = cv_tex.replace("—", "-")
    cover_tex = cover_tex.replace("—", "-")

    with open(cv_path, "w") as f:
        f.write(cv_tex)

    with open(cover_path, "w") as f:
        f.write(cover_tex)

    compile_latex(cv_path)
    compile_latex(cover_path)

    return {
        "company": company,
        "title": title,
        "application_location": application_location,
        "cv_tex_path": str(cv_path),
        "cover_letter_tex_path": str(cover_path),
        "cv_pdf_path": str(cv_path.with_suffix(".pdf")),
        "cover_letter_pdf_path": str(cover_path.with_suffix(".pdf"))
    }


def generate_documents_for_top_jobs(
    top_jobs: dict,
    profile: dict,
    master_cv_text: str,
    contact_rules: dict,
    location_rules: dict
) -> list[dict]:
    generated = []

    all_jobs = top_jobs.get("London", []) + top_jobs.get("Istanbul", [])

    for job_item in all_jobs:
        decision = (
            job_item
            .get("score_result", {})
            .get("application_decision", {})
            .get("decision", "")
        )

        if decision == "skip":
            continue

        result = generate_documents_for_job(
            job_item=job_item,
            profile=profile,
            master_cv_text=master_cv_text,
            contact_rules=contact_rules,
            location_rules=location_rules
        )

        generated.append(result)
        print(f"Generated documents ✔ {result['company']}")

    return generated