import json
import re
import subprocess
import os, sys
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


API_KEY = os.environ.get("OPEN_AI_SECRET_KEY", None)

client = OpenAI(api_key=API_KEY)

APPLICATIONS_DIR = Path("outputs/applications")
APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# BASIC HELPERS
# =========================================================

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

    if (
        "istanbul" in location
        or "i̇stanbul" in location
        or "turkey" in location
        or "türkiye" in location
    ):
        return "Istanbul"

    return "London"


def escape_latex(text: str) -> str:
    if text is None:
        return ""

    text = str(text)

    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


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


# =========================================================
# COVER LETTER: STRUCTURED JSON FROM LLM
# =========================================================

def generate_cover_letter_content(
    job: dict,
    score_result: dict,
    profile: dict,
    master_cv_text: str,
    contact_context: dict,
    location_context: dict,
    application_location: str
) -> dict:
    title = job.get("title", "Unknown Role")
    company = job.get("company", "Unknown Company")
    description = job.get("description", "")

    prompt = f"""
You are a professional job application writing assistant.

Your task is to generate structured cover letter content only.

Application location:
{application_location}

Contact context:
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
- Do not invent experience, tools, employers, dates, achievements, certifications, education, or metrics.
- If evidence is not clearly supported by the master CV or candidate profile, do not use it.
- Do not mention UK Graduate Visa for Istanbul applications.
- Mention UK right to work only for London applications if available in contact_context.
- Write in English.
- Write naturally, like a real person.
- Avoid generic phrases such as "I am excited to apply" and "I am writing to express my interest".
- Do not use em dashes.
- Do not use this character: —
- Keep content concise and recruiter-readable.

COVER LETTER STRUCTURE:
Return structured content only.
Do not return LaTeX.
Do not return markdown.

Opening:
- 2 to 3 lines maximum.
- Mention the role and company naturally.
- Make it specific to the role.

Key Fit:
- 4 to 6 items maximum.
- Each item must match one job requirement to one concrete piece of evidence.
- Each evidence must come from the master CV/profile only.
- Keep each requirement and evidence short.
- Do not write paragraphs inside requirement or evidence.

Closing:
- 2 to 3 lines maximum.
- Professional, direct, and human.

Return ONLY valid JSON in this structure:

{{
  "opening": "",
  "key_fit": [
    {{
      "requirement": "",
      "evidence": ""
    }}
  ],
  "closing": ""
}}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    content = response.choices[0].message.content
    cleaned = clean_json(content)

    data = json.loads(cleaned)

    # Defensive cleanup
    data["opening"] = (data.get("opening") or "").replace("—", "-")
    data["closing"] = (data.get("closing") or "").replace("—", "-")

    cleaned_key_fit = []
    for item in data.get("key_fit", []):
        requirement = (item.get("requirement") or "").replace("—", "-")
        evidence = (item.get("evidence") or "").replace("—", "-")

        if requirement and evidence:
            cleaned_key_fit.append({
                "requirement": requirement,
                "evidence": evidence
            })

    data["key_fit"] = cleaned_key_fit[:6]

    return data


def render_cover_letter_tex(
    content: dict,
    job: dict,
    contact_context: dict,
    application_location: str
) -> str:
    company = escape_latex(job.get("company", ""))
    title = escape_latex(job.get("title", ""))

    address = escape_latex(contact_context.get("address", ""))
    phone = escape_latex(contact_context.get("phone", ""))
    email = escape_latex(contact_context.get("email", ""))
    linkedin = escape_latex(contact_context.get("linkedin", ""))

    opening = escape_latex(content.get("opening", ""))
    closing = escape_latex(content.get("closing", ""))

    key_fit_items = ""

    for item in content.get("key_fit", []):
        requirement = escape_latex(item.get("requirement", ""))
        evidence = escape_latex(item.get("evidence", ""))

        key_fit_items += f"""
    \\item \\textbf{{{requirement}:}} {evidence}
"""

    tex = f"""
\\documentclass[11pt,a4paper]{{article}}

\\usepackage[utf8]{{inputenc}}
\\usepackage[T1]{{fontenc}}
\\usepackage{{newtxtext}}
\\usepackage{{newtxmath}}
\\usepackage[margin=0.8in]{{geometry}}
\\usepackage{{enumitem}}
\\usepackage{{titlesec}}

\\setlength{{\\parindent}}{{0pt}}
\\setlength{{\\parskip}}{{6pt}}

\\begin{{document}}

\\begin{{center}}
    {{\\Large \\textbf{{Yusuf Ciger}}}} \\\\[0.15cm]
    {address} \\textbar\\ {phone} \\textbar\\ {email} \\textbar\\ {linkedin}
\\end{{center}}

\\vspace{{0.25cm}}

Dear Hiring Manager,

{opening}

\\vspace{{0.2cm}}

\\textbf{{Key Fit}}

\\begin{{itemize}}[leftmargin=1.5em, itemsep=4pt, topsep=2pt]
{key_fit_items}
\\end{{itemize}}

{closing}

\\vspace{{0.3cm}}

Kind regards, \\\\
Yusuf Ciger

\\end{{document}}
"""

    return tex


# =========================================================
# CV: STRICT MASTER-CV-BASED LATEX GENERATION
# =========================================================

def generate_tailored_cv_tex(
    job: dict,
    score_result: dict,
    profile: dict,
    master_cv_text: str,
    contact_context: dict,
    location_context: dict,
    application_location: str
) -> str:
    title = job.get("title", "Unknown Role")
    company = job.get("company", "Unknown Company")
    description = job.get("description", "")

    prompt = f"""
You are a professional CV tailoring assistant.

Your task is to generate a tailored LaTeX CV.

Application location:
{application_location}

Contact context:
{json.dumps(contact_context, indent=2)}

Location rules:
{json.dumps(location_context, indent=2)}

Candidate profile:
{json.dumps(profile, indent=2)}

MASTER CV LATEX, SOURCE OF TRUTH:
{master_cv_text}

Job title:
{title}

Company:
{company}

Job description:
{description}

AI scoring insights:
{json.dumps(score_result, indent=2)}

CRITICAL SOURCE OF TRUTH RULES:
- The master CV LaTeX is the only source of truth.
- Do not invent experience, tools, employers, dates, achievements, education, certifications, languages, projects, or metrics.
- Do not add any skill that is not present in the master CV or candidate profile.
- Do not add Power BI, Tableau, AWS, Azure, Salesforce, Jira, Confluence, Zapier, Power Automate, or any other tool unless it is already present in the master CV/profile.
- You may reorder, rephrase, and prioritise existing content only.
- You may tailor the Professional Summary using only existing facts.
- You may reorder Key Skills using only existing skills.
- You may rephrase bullet points using only existing facts.
- Do not change company names, dates, universities, degrees, or job titles.
- Do not exaggerate experience level.
- If the job asks for a skill the candidate does not have, do not pretend they have it.
- You may remove, shorten, or deprioritise content that is weakly related to the target role.
- You should emphasise the strongest evidence for this job, especially relevant experience, skills, projects, and measurable impact.
- Do not keep every bullet from the master CV if it weakens relevance.
- Keep the CV focused on the target role.
- Preserve core work history, education, and contact details, but you may reduce irrelevant bullets.
- If a role is only weakly related, keep 1 to 2 concise bullets maximum.
- Do not add new facts to create relevance. Relevance must come from existing evidence only.

LOCATION RULES:
- Use the correct phone number, email, LinkedIn, and address from contact_context.
- If application_location is London, include right-to-work information only if provided in contact_context or location_rules.
- If application_location is Istanbul, do not mention UK Graduate Visa or UK right-to-work.

STYLE RULES:
- ATS-friendly.
- One page if possible.
- Clean LaTeX.
- Keep the same overall style as the master CV.
- Do not use em dashes.
- Do not use this character: —
- Avoid icons.
- Avoid complex tables.
- Use concise bullet points.
- Return complete compilable LaTeX only.
- Prioritise relevance over completeness.
- The final CV should feel intentionally tailored, not like a copied master CV.

OUTPUT RULES:
Return ONLY valid JSON.
Do not use markdown.
Do not add explanation.

JSON structure:
{{
  "tailored_cv_tex": ""
}}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.15
    )

    content = response.choices[0].message.content
    cleaned = clean_json(content)

    data = json.loads(cleaned)
    cv_tex = data.get("tailored_cv_tex", "")

    cv_tex = cv_tex.replace("—", "-")

    return cv_tex


# =========================================================
# MAIN DOCUMENT GENERATION
# =========================================================

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

    application_location = get_application_location(job)

    contact_context = contact_rules.get(application_location, {})
    location_context = location_rules.get(application_location, {})

    company_safe = safe_name(company)

    company_dir = APPLICATIONS_DIR / application_location / company_safe
    company_dir.mkdir(parents=True, exist_ok=True)

    cv_filename = f"Yusuf_Ciger_CV_{company_safe}.tex"
    cover_filename = f"Yusuf_Ciger_Cover_Letter_{company_safe}.tex"

    cv_path = company_dir / cv_filename
    cover_path = company_dir / cover_filename

    # 1) Generate CV LaTeX
    cv_tex = generate_tailored_cv_tex(
        job=job,
        score_result=score_result,
        profile=profile,
        master_cv_text=master_cv_text,
        contact_context=contact_context,
        location_context=location_context,
        application_location=application_location
    )

    # 2) Generate structured cover letter content
    cover_content = generate_cover_letter_content(
        job=job,
        score_result=score_result,
        profile=profile,
        master_cv_text=master_cv_text,
        contact_context=contact_context,
        location_context=location_context,
        application_location=application_location
    )

    # 3) Render cover letter with fixed LaTeX template
    cover_tex = render_cover_letter_tex(
        content=cover_content,
        job=job,
        contact_context=contact_context,
        application_location=application_location
    )

    # 4) Save tex files
    with open(cv_path, "w", encoding="utf-8") as f:
        f.write(cv_tex)

    with open(cover_path, "w", encoding="utf-8") as f:
        f.write(cover_tex)

    # 5) Compile PDFs
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

        applicable_rate = (
            job_item
            .get("score_result", {})
            .get("application_decision", {})
            .get("applicable_rate", 0)
        )

        if decision == "skip":
            continue

        if applicable_rate < 60:
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