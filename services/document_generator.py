from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from app_config import AppConfig
from services.openai_client import get_openai_client


DOCUMENT_MODEL = "gpt-4.1-mini"
APPLICATIONS_DIR = Path("outputs/applications")


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value or "Unknown")
    return cleaned.strip("_") or "Unknown"


def clean_json(content: str) -> str:
    if not content:
        raise ValueError("Empty response from model")
    content = content.strip()
    if content.startswith("```"):
        content = content.replace("```json", "").replace("```", "").strip()
    start = content.find("{")
    end = content.rfind("}")
    return content[start : end + 1] if start != -1 and end != -1 else content


def escape_latex(text: str) -> str:
    if text is None:
        return ""
    escaped = str(text)
    for old, new in {
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
    }.items():
        escaped = escaped.replace(old, new)
    return escaped


def compile_latex(tex_path: Path) -> bool:
    try:
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_path.name],
            cwd=tex_path.parent,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError as exc:
        print(f"PDF compile failed for {tex_path}: {exc}")
        return False
    finally:
        for extension in [".aux", ".log", ".out"]:
            auxiliary = tex_path.with_suffix(extension)
            if auxiliary.exists():
                auxiliary.unlink()

    pdf_exists = tex_path.with_suffix(".pdf").exists()
    if result.returncode != 0 or not pdf_exists:
        print(f"PDF compile failed for {tex_path}")
        return False
    return True


def generate_cover_letter_content(
    job: dict,
    score_result: dict,
    profile: dict,
    master_cv_text: str,
    contact_context: dict,
    config: AppConfig,
) -> dict:
    prompt = f"""
You are a professional UK job application writing assistant.

Generate structured cover letter content for:
- Role: {job.get("title", "Unknown Role")}
- Company: {job.get("company", "Unknown Company")}
- Market: UK
- Language: {config.documents.cv_language}
- Style: {config.documents.cover_letter_style}

Contact context:
{json.dumps(contact_context, indent=2)}

Candidate profile:
{json.dumps(profile, indent=2)}

Master CV LaTeX, the source of truth:
{master_cv_text}

Job description:
{job.get("description", "")}

Scoring insights:
{json.dumps(score_result, indent=2)}

Rules:
- Never invent experience, tools, employers, dates, achievements,
  certifications, education, or metrics.
- Use only evidence supported by the master CV or candidate profile.
- Mention UK right to work only when supplied in contact context and enabled.
- Write naturally and concisely. Do not use em dashes.
- Opening and closing must each be at most 2-3 lines.
- Include 4-6 short requirement/evidence pairs.

Return ONLY valid JSON:
{{
  "opening": "",
  "key_fit": [{{"requirement": "", "evidence": ""}}],
  "closing": ""
}}
"""
    response = get_openai_client().chat.completions.create(
        model=DOCUMENT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    data = json.loads(clean_json(response.choices[0].message.content))
    data["opening"] = (data.get("opening") or "").replace("—", "-")
    data["closing"] = (data.get("closing") or "").replace("—", "-")
    data["key_fit"] = [
        {
            "requirement": (item.get("requirement") or "").replace("—", "-"),
            "evidence": (item.get("evidence") or "").replace("—", "-"),
        }
        for item in data.get("key_fit", [])
        if item.get("requirement") and item.get("evidence")
    ][:6]
    return data


def render_cover_letter_tex(
    content: dict,
    contact_context: dict,
) -> str:
    candidate_name = escape_latex(contact_context.get("name", "Candidate"))
    address = escape_latex(contact_context.get("address", ""))
    phone = escape_latex(contact_context.get("phone", ""))
    email = escape_latex(contact_context.get("email", ""))
    linkedin = escape_latex(contact_context.get("linkedin", ""))
    opening = escape_latex(content.get("opening", ""))
    closing = escape_latex(content.get("closing", ""))
    items = "".join(
        f"\n\\item \\textbf{{{escape_latex(item['requirement'])}:}} "
        f"{escape_latex(item['evidence'])}\n"
        for item in content.get("key_fit", [])
    )

    return f"""
\\documentclass[11pt,a4paper]{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage[T1]{{fontenc}}
\\usepackage{{newtxtext}}
\\usepackage{{newtxmath}}
\\usepackage[margin=0.8in]{{geometry}}
\\usepackage{{enumitem}}
\\setlength{{\\parindent}}{{0pt}}
\\setlength{{\\parskip}}{{6pt}}
\\begin{{document}}
\\begin{{center}}
\\Large \\textbf{{{candidate_name}}} \\\\[0.15cm]
{address} \\textbar\\ {phone} \\textbar\\ {email} \\textbar\\ {linkedin}
\\end{{center}}
\\vspace{{0.25cm}}
Dear Hiring Manager,

{opening}

\\textbf{{Key Fit}}
\\begin{{itemize}}[leftmargin=1.5em, itemsep=4pt, topsep=2pt]
{items}
\\end{{itemize}}

{closing}

\\vspace{{0.3cm}}
Kind regards, \\\\
{candidate_name}
\\end{{document}}
"""


def generate_tailored_cv_tex(
    job: dict,
    score_result: dict,
    profile: dict,
    master_cv_text: str,
    contact_context: dict,
    config: AppConfig,
) -> str:
    prompt = f"""
You are a professional UK CV tailoring assistant.

Generate a complete, compilable LaTeX CV for:
- Role: {job.get("title", "Unknown Role")}
- Company: {job.get("company", "Unknown Company")}
- Language: {config.documents.cv_language}

Contact context:
{json.dumps(contact_context, indent=2)}

Candidate profile:
{json.dumps(profile, indent=2)}

Master CV LaTeX, the only source of truth:
{master_cv_text}

Job description:
{job.get("description", "")}

Scoring insights:
{json.dumps(score_result, indent=2)}

Rules:
- Never invent skills, experience, tools, employers, dates, achievements,
  education, certifications, languages, projects, or metrics.
- You may reorder, shorten, rephrase, and prioritise existing facts only.
- Preserve company names, dates, universities, degrees, and job titles.
- Use contact_context for the candidate header.
- Include right-to-work information only when it is present in contact_context.
- Keep it ATS-friendly, concise, and one page when practical.
- Preserve the master CV's overall style and return complete LaTeX.
- Do not use em dashes.

Return ONLY valid JSON:
{{"tailored_cv_tex": ""}}
"""
    response = get_openai_client().chat.completions.create(
        model=DOCUMENT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.15,
    )
    data = json.loads(clean_json(response.choices[0].message.content))
    return (data.get("tailored_cv_tex") or "").replace("—", "-")


def generate_documents_for_job(
    job_item: dict,
    profile: dict,
    master_cv_text: str,
    config: AppConfig,
) -> dict:
    job = job_item.get("job", {})
    score_result = job_item.get("score_result", {})
    contact_context = config.contact_context(profile)
    if not config.documents.include_right_to_work:
        contact_context["right_to_work"] = ""

    candidate_safe = safe_name(contact_context.get("name", "Candidate"))
    company_safe = safe_name(job.get("company", "Unknown Company"))
    title_safe = safe_name(job.get("title", "Unknown Role"))
    folder_safe = f"{company_safe}_{title_safe}"
    company_dir = APPLICATIONS_DIR / "UK" / folder_safe
    company_dir.mkdir(parents=True, exist_ok=True)

    cv_path = company_dir / f"{candidate_safe}_CV_{folder_safe}.tex"
    cover_path = company_dir / f"{candidate_safe}_Cover_Letter_{folder_safe}.tex"
    cv_tex = generate_tailored_cv_tex(
        job, score_result, profile, master_cv_text, contact_context, config
    )
    cover_content = generate_cover_letter_content(
        job, score_result, profile, master_cv_text, contact_context, config
    )
    cover_tex = render_cover_letter_tex(cover_content, contact_context)

    cv_path.write_text(cv_tex, encoding="utf-8")
    cover_path.write_text(cover_tex, encoding="utf-8")
    cv_compiled = compile_latex(cv_path)
    cover_compiled = compile_latex(cover_path)

    return {
        "company": job.get("company", "Unknown Company"),
        "title": job.get("title", "Unknown Role"),
        "market": "UK",
        "cv_tex_path": str(cv_path),
        "cover_letter_tex_path": str(cover_path),
        "cv_pdf_path": str(cv_path.with_suffix(".pdf")) if cv_compiled else "",
        "cover_letter_pdf_path": (
            str(cover_path.with_suffix(".pdf")) if cover_compiled else ""
        ),
    }


def generate_documents_for_top_jobs(
    top_jobs: dict,
    profile: dict,
    master_cv_text: str,
    config: AppConfig,
) -> list[dict]:
    if not config.documents.enabled:
        return []

    generated: list[dict] = []
    for job_item in top_jobs.get("UK", []):
        try:
            result = generate_documents_for_job(
                job_item=job_item,
                profile=profile,
                master_cv_text=master_cv_text,
                config=config,
            )
        except Exception as exc:
            job = job_item.get("job", {})
            print(
                "Document generation failed for "
                f"{job.get('title')} | {job.get('company')}: {exc}"
            )
            continue
        generated.append(result)
        print(f"Generated documents ✔ {result['company']}")
    return generated
