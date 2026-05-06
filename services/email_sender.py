import smtplib
import os
from pathlib import Path
from email.message import EmailMessage
from dotenv import load_dotenv
from datetime import datetime

from .state_store import mark_job_items_as_emailed

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO") or EMAIL_ADDRESS


def get_application_rate(job_item: dict) -> int:
    return (
        job_item
        .get("score_result", {})
        .get("application_decision", {})
        .get("applicable_rate", 0)
    )


def get_decision(job_item: dict) -> str:
    return (
        job_item
        .get("score_result", {})
        .get("application_decision", {})
        .get("decision", "")
    )


def build_document_lookup(generated_documents: list[dict]) -> dict:
    lookup = {}

    for doc in generated_documents:
        company = doc.get("company", "")
        title = doc.get("title", "")

        key = make_key(company, title)

        lookup[key] = {
            "cv_pdf_path": doc.get("cv_pdf_path"),
            "cover_letter_pdf_path": doc.get("cover_letter_pdf_path")
        }

    return lookup


def make_key(company: str, title: str) -> str:
    return f"{company.lower().strip()}|{title.lower().strip()}"


def build_email_body(top_jobs: dict) -> str:
    now = datetime.now().strftime("%d/%m/%Y - %H:%M")

    lines = []
    lines.append(f"Daily Job Report - {now}")
    lines.append("")
    lines.append("The following roles were selected by the AI job agent.")
    lines.append("CV and cover letter files are attached where available.")
    lines.append("")

    for location in ["London", "Istanbul"]:
        jobs = top_jobs.get(location, [])

        lines.append("=" * 40)
        lines.append(f"{location.upper()} TOP JOBS")
        lines.append("=" * 40)
        lines.append("")

        if not jobs:
            lines.append("No suitable jobs found.")
            lines.append("")
            continue

        for index, item in enumerate(jobs, start=1):
            job = item.get("job", {})

            company = job.get("company", "Unknown Company")
            title = job.get("title", "Unknown Role")
            link = job.get("url", "No link")

            rate = get_application_rate(item)
            decision = get_decision(item)

            lines.append(f"{index}. {company}")
            lines.append(f"Role: {title}")
            lines.append(f"Score: {rate}")
            lines.append(f"Decision: {decision}")
            lines.append(f"Apply: {link}")
            lines.append("")

    return "\n".join(lines)


def collect_attachments(top_jobs: dict, generated_documents: list[dict]) -> list[str]:
    document_lookup = build_document_lookup(generated_documents)

    attachments = []

    all_jobs = top_jobs.get("London", []) + top_jobs.get("Istanbul", [])

    for item in all_jobs:
        job = item.get("job", {})

        company = job.get("company", "")
        title = job.get("title", "")

        key = make_key(company, title)
        docs = document_lookup.get(key)

        if not docs:
            continue

        for path_key in ["cv_pdf_path", "cover_letter_pdf_path"]:
            file_path = docs.get(path_key)

            if file_path and Path(file_path).exists():
                attachments.append(file_path)

    # duplicate attachmentları kaldır
    unique = []
    seen = set()

    for path in attachments:
        if path in seen:
            continue

        seen.add(path)
        unique.append(path)

    return unique


def attach_files(msg: EmailMessage, attachments: list[str]):
    for file_path in attachments:
        try:
            path = Path(file_path)

            with open(path, "rb") as f:
                file_data = f.read()

            msg.add_attachment(
                file_data,
                maintype="application",
                subtype="pdf",
                filename=path.name
            )

        except Exception as e:
            print(f"Attachment failed: {file_path} → {e}")


def send_job_email(top_jobs: dict, generated_documents: list[dict], dry_run: bool = False):
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        raise ValueError("EMAIL_ADDRESS or EMAIL_PASSWORD is missing from .env")

    now = datetime.now().strftime("%d/%m/%Y - %H:%M")

    msg = EmailMessage()
    msg["Subject"] = f"Daily Job Report - {now}"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_TO

    body = build_email_body(top_jobs)
    msg.set_content(body)

    attachments = collect_attachments(
        top_jobs=top_jobs,
        generated_documents=generated_documents
    )

    attach_files(msg, attachments)

    print(f"Email attachments found: {len(attachments)}")

    if dry_run:
        total_jobs = len(top_jobs.get("London", [])) + len(top_jobs.get("Istanbul", []))
        print("DRY RUN: email send skipped")
        print(f"DRY RUN summary: subject={msg['Subject']}")
        print(f"DRY RUN summary: jobs={total_jobs}")
        print(f"DRY RUN summary: attachments={len(attachments)}")
        print(f"DRY RUN summary: recipient={EMAIL_TO}")
        return

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)

        mark_job_items_as_emailed(top_jobs)

        print("Email sent successfully ✔")

    except Exception as e:
        print("Email sending failed:", e)
