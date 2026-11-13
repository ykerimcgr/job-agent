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


DOCUMENT_MODEL = "gpt-6.1-terra"
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
                "type": "skill list" if block.heading == block.section else "entry",
                "can_remove": block.droppable,
                "bullets": [{"id": b.id, "text": b.text} for b in block.bullets],
            }
            for block in template.blocks
            if block.editable
        ],
    }
    assessment = score_result.get("assessment", {})
    length_rule = (
        "the CV must fit ONE page: keep about three experience entries, at most three bullets "
        "each, and a project only if it is clearly relevant."
        if market.cv_max_pages == 1
        else "up to two pages is fine, but nothing stays just to fill space."
    )
    prompt = f"""
You tailor a candidate's existing CV and write a short cover letter for one job.
The CV is first read by an applicant tracking system (ATS) that matches the job's keywords,
then by a recruiter who gives it a few seconds. Make the strongest HONEST case for this job.

Hard rule: every statement must be supported by the CV below. You select, reorder, combine,
expand and reword the candidate's own facts. You never add a fact, skill, tool, number,
employer, date, responsibility or result that the CV does not state.

Job: {job.get("title", "")} at {job.get("company", "")} ({job.get("location", "")})
Job description:
{job.get("description", "")}

Screening result (requirement status for this candidate):
{json.dumps(assessment.get("requirements", []), indent=2, ensure_ascii=False)}

Candidate CV, as ids and plain text:
{json.dumps(cv, indent=2, ensure_ascii=False)}

Step 1 - read the job. Note its 8-12 most important keywords: tasks, tools, methods, domain
terms. For each, decide whether the CV plainly shows it. Only those the CV shows may be used.

Step 2 - choose what stays (blocks: return exactly one entry for EVERY block id above).
- keep=false removes an entry; only allowed when can_remove is true.
- A focused CV beats a complete one. Rank the experience entries by how much they prove for
  THIS job, keep the strongest and remove the rest. Technical and analytical experience
  outranks unrelated work for a technical or operations job.
- Remove an entry whose work is unrelated to this job (for example a short sales role for an
  engineering or analyst job) unless the job explicitly asks for what it shows. Being the
  most recent entry is not a reason to keep it. Never keep a weaker entry while removing a
  stronger one. Keep at least two experience entries.
- Length: {length_rule}
- Projects: keep a project when it shows skills this job asks for; otherwise remove it.
- bullets: the block's bullet ids, most relevant to this job first, each with its final text.
  Leave out bullets that do nothing for this job.

Step 3 - rewrite the kept bullets of each entry.
- Lead with what this job asks for: the task, the tool, the scale, the result.
- Where the CV states the same thing as a job keyword, use the job's wording, but only with
  words the CV itself uses somewhere. Do not import a term the CV never uses.
- You may expand a bullet, or merge two, using facts stated elsewhere in the SAME entry (the
  tool from one bullet, the result from another). Never move a fact between entries.
- Numbers stay exactly as written. No purpose, benefit or impact phrase ("to improve X",
  "enhancing Y") unless the entry states it.
- Keep a bullet unchanged when it is already a strong match.

Step 4 - skill lists (blocks whose type is "skill list").
- A skill, tool or method may be named only when an experience, project or education part of
  this CV plainly shows it. If in doubt, leave it out. Never add a skill because the job asks.
- Put the lines and terms this job asks for first; drop lines that do not matter here.
- Keep each line's leading label and its short-phrase style. No proficiency words
  ("proficient", "experienced", "skilled").

Step 5 - summary: 2-3 sentences, built only from CV facts, written for this job. Open with
who the candidate is (degree and background), work the target role from the job title in
naturally, then give the two or three facts that matter most for it. Do not write "applying
for" or "candidate for". Never reuse the CV's summary unchanged.

Never claim a requirement whose status is "missing".

Cover letter ({config.documents.cv_language}, {market.cover_letter_style}):
- The greeting ("Dear Hiring Manager,") and sign-off are added separately; do not write them.
- cover_opening: 2-3 lines naming the role and employer and the single strongest reason the
  candidate fits, taken from the CV.
- Write every part in {config.documents.cv_language}, including requirements: when the job ad
  is in another language, translate the requirement instead of quoting it.
  The job title and employer name are the exception: write them exactly as the ad does.
- cover_key_fit: 3-5 pairs. requirement = a requirement from the job, in the job's words;
  evidence = one concrete fact restated from the CV (what was done, with what, and the
  result). Skip requirements the CV cannot evidence.
- cover_closing: 2-3 lines; say what the candidate wants to contribute, using CV facts only.
- No em dashes. Do not mention right to work or visas. No generic praise of the company.
"""
    return structured_completion(prompt, ApplicationDraft, model=DOCUMENT_MODEL, reasoning_effort="medium")


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

    def check(
        text: str,
        source: str,
        label: str,
        extra_known: set[str] = frozenset(),
        base: set[str] | None = None,
        allowed: set[str] = frozenset(),
        strict: bool = False,
    ) -> bool:
        words = (known if base is None else base) | extra_known
        problems = unsupported_terms(text, source=source, known=words, risky=risky - allowed, strict=strict)
        if problems:
            fixes.append(f"{label}: {', '.join(sorted(set(problems)))}")
        return not problems

    # The summary and cover may name the role and employer ("Graduate Machine Learning Engineer, 2027").
    title, company = job.get("title", "the role"), job.get("company", "your company")
    role_words = vocabulary(f"{title} {company}")
    about_job = f"{template.plain_text} {title} {company}"

    summary = draft.summary.replace("—", "-").strip()
    if not summary or not check(summary, about_job, "summary", role_words, allowed=role_words):
        summary = None

    blocks = {block.id: block for block in template.blocks if block.editable}
    plans: dict[str, tuple[bool, list[tuple[str, str]]]] = {}
    for plan in draft.blocks:
        block = blocks.get(plan.id)
        if block is None:
            continue
        own = {bullet.id: bullet for bullet in block.bullets}
        # A bullet may reuse any fact from its own entry, never from another entry.
        block_text = " ".join([block.heading, *(bullet.text for bullet in block.bullets)])
        # A skill list (no employer or dates of its own) summarises the whole CV, so it may name
        # anything the CV states, and nothing else: every word must already be a CV word.
        is_skill_list = block.heading == block.section
        chosen: list[tuple[str, str]] = []
        for choice in plan.bullets:
            original = own.pop(choice.id, None)
            if original is None:
                continue
            text = choice.text.replace("—", "-").strip() or original.text
            if text == original.text:
                supported = True
            elif is_skill_list:
                supported = check(text, template.plain_text, choice.id, strict=True)
            else:
                supported = check(text, block_text, choice.id, base=vocabulary(block_text))
            if not supported:
                text = original.text
            chosen.append((choice.id, text))
        plans[block.id] = (plan.keep or not block.droppable, chosen)

    # Never remove all experience: keep its entries then. Other sections (Projects) may go entirely.
    for section in {b.section for b in blocks.values() if b.droppable and "experience" in b.section.casefold()}:
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
    opening = draft.cover_opening.replace("—", "-").strip()
    if not opening or not check(opening, about_job, "cover opening", names, allowed=role_words):
        opening = f"I am writing to apply for the {title} position at {company}."
    closing = draft.cover_closing.replace("—", "-").strip()
    if not closing or not check(closing, about_job, "cover closing", names, allowed=role_words):
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
