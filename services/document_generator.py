from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import re
import subprocess
from pathlib import Path

from pydantic import BaseModel

from app_config import AppConfig, MarketConfig
from services.cv_template import CvTemplate, parse_cv, render_cv
from services.grounding import risky_vocabulary, unsupported_terms, vocabulary
from services.openai_client import structured_completion


DOCUMENT_MODEL = "gpt-4.1-mini"
APPLICATIONS_DIR = Path("outputs/applications")
MAX_PARALLEL_CALLS = 4


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value or "Unknown")
    return cleaned.strip("_") or "Unknown"


LATEX_SPECIALS = {
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
LATEX_SPECIALS_PATTERN = re.compile("|".join(map(re.escape, LATEX_SPECIALS)))


def escape_latex(text: str) -> str:
    # Single pass, so the braces added for a backslash are never escaped again.
    if text is None:
        return ""
    return LATEX_SPECIALS_PATTERN.sub(lambda m: LATEX_SPECIALS[m.group()], str(text))


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


class BulletChoice(BaseModel):
    id: str
    text: str


class BlockPlan(BaseModel):
    id: str
    keep: bool
    bullets: list[BulletChoice]


class KeyFit(BaseModel):
    requirement: str
    evidence: str


class ApplicationDraft(BaseModel):
    summary: str
    blocks: list[BlockPlan]
    cover_opening: str
    cover_key_fit: list[KeyFit]
    cover_closing: str


def draft_application(
    job: dict,
    score_result: dict,
    template: CvTemplate,
    config: AppConfig,
    market: MarketConfig,
) -> ApplicationDraft:
    cv = {
        "summary": template.summary,
        "blocks": [
            {
                "id": block.id,
                "section": block.section,
                "heading": block.heading,
                "can_remove": block.droppable,
                "bullets": [{"id": b.id, "text": b.text} for b in block.bullets],
            }
            for block in template.blocks
            if block.editable
        ],
    }
    assessment = score_result.get("assessment", {})
    prompt = f"""
You tailor a candidate's existing CV and write a short cover letter for one job.
Everything you write must be supported by the CV below. You are choosing and
rewording, never adding.

Job: {job.get("title", "")} at {job.get("company", "")} ({job.get("location", "")})
Job description:
{job.get("description", "")}

Screening result (requirement status for this candidate):
{json.dumps(assessment.get("requirements", []), indent=2, ensure_ascii=False)}

Candidate CV, as ids and plain text:
{json.dumps(cv, indent=2, ensure_ascii=False)}

CV rules:
- blocks: one entry per block id you change. keep=false removes an entry; only allowed
  when can_remove is true. Remove entries that would not help for this job (unrelated
  roles, weak or off-topic experience); keep entries that show transferable skills.
- bullets: the block's bullet ids in the order you want them, each with its final text.
  Leave out bullets that do not help. Use the original text unchanged when it already fits.
- Rewording may only reorder emphasis or use clearer wording. Keep every fact, number,
  tool, employer and date exactly as the source bullet says. Never add a skill, tool,
  number, responsibility or result that is not in that same bullet.
- Never claim a requirement whose status is "missing".
- summary: 2-3 sentences built only from facts in the CV, angled to this job.

Cover letter rules ({config.documents.cv_language}, {market.cover_letter_style}):
- cover_opening and cover_closing: 2-3 lines each.
- cover_key_fit: 3-5 pairs. requirement = a requirement from the job; evidence = a fact
  restated from the CV. Skip requirements the CV cannot evidence.
- No em dashes. Do not mention right to work or visas.
"""
    return structured_completion(prompt, ApplicationDraft, model=DOCUMENT_MODEL, temperature=0.2)


def ground_draft(
    draft: ApplicationDraft,
    template: CvTemplate,
    job: dict,
    score_result: dict,
) -> tuple[dict, list[str]]:
    """Keep only rewrites the master CV supports; anything else falls back to the original text."""
    known = vocabulary(template.plain_text)
    unmet = [
        r.get("requirement", "")
        for r in score_result.get("assessment", {}).get("requirements", [])
        if r.get("status") != "met"
    ]
    risky = risky_vocabulary(unmet, known)
    fixes: list[str] = []

    def check(text: str, source: str, label: str, extra_known: set[str] = frozenset()) -> bool:
        problems = unsupported_terms(text, source=source, known=known | extra_known, risky=risky)
        if problems:
            fixes.append(f"{label}: {', '.join(sorted(set(problems)))}")
        return not problems

    summary = draft.summary.replace("—", "-").strip()
    if not summary or not check(summary, template.plain_text, "summary"):
        summary = None

    blocks = {block.id: block for block in template.blocks if block.editable}
    plans: dict[str, tuple[bool, list[tuple[str, str]]]] = {}
    for plan in draft.blocks:
        block = blocks.get(plan.id)
        if block is None:
            continue
        own = {bullet.id: bullet for bullet in block.bullets}
        chosen: list[tuple[str, str]] = []
        for choice in plan.bullets:
            original = own.pop(choice.id, None)
            if original is None:
                continue
            text = choice.text.replace("—", "-").strip() or original.text
            if text != original.text and not check(text, original.text, choice.id):
                text = original.text
            chosen.append((choice.id, text))
        plans[block.id] = (plan.keep or not block.droppable, chosen)

    # Never empty a whole section (e.g. all experience removed): keep its entries then.
    for section in {block.section for block in blocks.values() if block.droppable}:
        members = [b.id for b in blocks.values() if b.section == section and b.droppable]
        if all(not plans.get(block_id, (True, []))[0] for block_id in members):
            for block_id in members:
                plans[block_id] = (True, plans[block_id][1])
            fixes.append(f"kept all of {section}")

    # Openings may name the real employer behind a job board (e.g. "InPost" on targetjobs),
    # so any word from the job ad is allowed there; unmet-requirement words are still blocked.
    names = vocabulary(
        " ".join(str(job.get(key, "")) for key in ("title", "company", "location", "description"))
    )
    title, company = job.get("title", "the role"), job.get("company", "your company")
    opening = draft.cover_opening.replace("—", "-").strip()
    if not opening or not check(opening, template.plain_text, "cover opening", names):
        opening = f"I am writing to apply for the {title} position at {company}."
    closing = draft.cover_closing.replace("—", "-").strip()
    if not closing or not check(closing, template.plain_text, "cover closing", names):
        closing = (
            "Thank you for considering my application. I would welcome the "
            f"opportunity to discuss how I could contribute to {company}."
        )
    key_fit = [
        {"requirement": item.requirement.replace("—", "-"), "evidence": item.evidence.replace("—", "-")}
        for item in draft.cover_key_fit
        if item.requirement and item.evidence
        and check(item.evidence, template.plain_text, f"cover evidence '{item.requirement}'")
    ][:5]

    removed = [blocks[b].heading for b, (keep, _) in plans.items() if not keep]
    return {
        "summary": summary,
        "block_plans": plans,
        "cover": {"opening": opening, "key_fit": key_fit, "closing": closing},
        "removed_entries": removed,
    }, fixes


def render_cover_letter_tex(content: dict, contact_context: dict) -> str:
    candidate_name = escape_latex(contact_context.get("name", "Candidate"))
    details = r" \textbar\ ".join(
        escape_latex(contact_context[key])
        for key in ("address", "phone", "email", "linkedin")
        if contact_context.get(key)
    )
    opening = escape_latex(content.get("opening", ""))
    closing = escape_latex(content.get("closing", ""))
    items = "".join(
        f"\n\\item \\textbf{{{escape_latex(item['requirement'])}:}} "
        f"{escape_latex(item['evidence'])}\n"
        for item in content.get("key_fit", [])
    )
    key_fit = (
        f"\\textbf{{Key Fit}}\n\\begin{{itemize}}[leftmargin=1.5em, itemsep=4pt, topsep=2pt]\n{items}\\end{{itemize}}\n"
        if items
        else ""
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
\\normalsize {details}
\\end{{center}}
\\vspace{{0.25cm}}
Dear Hiring Manager,

{opening}

{key_fit}
{closing}

\\vspace{{0.3cm}}
Kind regards, \\\\
{candidate_name}
\\end{{document}}
"""


def write_documents(
    job_item: dict,
    grounded: dict,
    fixes: list[str],
    template: CvTemplate,
    contact_context: dict,
    market: MarketConfig,
) -> dict:
    job = job_item.get("job", {})
    candidate_safe = safe_name(contact_context.get("name", "Candidate"))
    folder_safe = f"{safe_name(job.get('company', 'Unknown Company'))}_{safe_name(job.get('title', 'Unknown Role'))}"
    company_dir = APPLICATIONS_DIR / market.code / folder_safe
    company_dir.mkdir(parents=True, exist_ok=True)

    cv_path = company_dir / f"{candidate_safe}_CV_{folder_safe}.tex"
    cover_path = company_dir / f"{candidate_safe}_Cover_Letter_{folder_safe}.tex"
    cv_path.write_text(
        render_cv(
            template,
            summary=grounded["summary"],
            block_plans=grounded["block_plans"],
            contact=contact_context,
            escape=escape_latex,
        ),
        encoding="utf-8",
    )
    cover_path.write_text(render_cover_letter_tex(grounded["cover"], contact_context), encoding="utf-8")
    cv_compiled = compile_latex(cv_path)
    cover_compiled = compile_latex(cover_path)

    return {
        "company": job.get("company", "Unknown Company"),
        "title": job.get("title", "Unknown Role"),
        "market": market.code,
        "cv_tex_path": str(cv_path),
        "cover_letter_tex_path": str(cover_path),
        "cv_pdf_path": str(cv_path.with_suffix(".pdf")) if cv_compiled else "",
        "cover_letter_pdf_path": str(cover_path.with_suffix(".pdf")) if cover_compiled else "",
        "removed_entries": grounded["removed_entries"],
        "grounding_fixes": fixes,
    }


def generate_documents_for_top_jobs(
    top_jobs: dict[str, list[dict]],
    profile: dict,
    master_cv_text: str,
    config: AppConfig,
) -> list[dict]:
    if not config.documents.enabled:
        return []

    template = parse_cv(master_cv_text)
    markets = {market.code: market for market in config.markets}
    work = [(markets[code], item) for code, items in top_jobs.items() for item in items]

    def draft(pair: tuple[MarketConfig, dict]) -> ApplicationDraft | Exception:
        market, item = pair
        try:
            return draft_application(item.get("job", {}), item.get("score_result", {}), template, config, market)
        except Exception as exc:  # one failed draft must not stop the others
            return exc

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CALLS) as pool:
        drafts = list(pool.map(draft, work))

    generated: list[dict] = []
    for (market, item), result in zip(work, drafts):
        job = item.get("job", {})
        try:
            if isinstance(result, Exception):
                raise result
            grounded, fixes = ground_draft(result, template, job, item.get("score_result", {}))
            document = write_documents(
                item, grounded, fixes, template, config.contact_context(profile, market), market
            )
        except Exception as exc:
            print(f"Document generation failed for {job.get('title')} | {job.get('company')}: {exc}")
            continue
        generated.append(document)
        note = f" ({len(fixes)} unsupported rewrites reverted)" if fixes else ""
        print(f"Generated documents ✔ {market.code} | {document['company']}{note}")
    return generated
