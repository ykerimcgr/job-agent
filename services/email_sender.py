from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage
import os
from pathlib import Path
import smtplib

from dotenv import load_dotenv

from app_config import AppConfig
from services.state_store import mark_job_items_as_emailed


load_dotenv()


def get_application_rate(job_item: dict) -> int:
    return (
        job_item.get("score_result", {})
        .get("application_decision", {})
        .get("applicable_rate", 0)
    )


def get_decision(job_item: dict) -> dict:
    return job_item.get("score_result", {}).get("application_decision", {})


def make_key(market: str, company: str, title: str) -> str:
    return f"{market}|{company.casefold().strip()}|{title.casefold().strip()}"


def build_document_lookup(generated_documents: list[dict]) -> dict:
    return {
        make_key(doc.get("market", ""), doc.get("company", ""), doc.get("title", "")): doc
        for doc in generated_documents
    }


def build_email_body(top_jobs: dict[str, list[dict]], candidate_name: str) -> str:
    now = datetime.now().strftime("%d/%m/%Y - %H:%M")
    lines = [
        f"Job Report for {candidate_name or 'Candidate'} - {now}",
        "",
        "The following roles were selected by the AI job agent.",
        "CV and cover letter files are attached where available.",
    ]

    for code, items in top_jobs.items():
        if not items:
            continue
        lines += ["", "=" * 40, f"{code} TOP JOBS ({len(items)})", "=" * 40, ""]
        for index, item in enumerate(items, start=1):
            job = item.get("job", {})
            decision = get_decision(item)
            lines += [
                f"{index}. {job.get('company', 'Unknown Company')} - {job.get('location', '')}",
                f"Role: {job.get('title', 'Unknown Role')}",
                f"Score: {get_application_rate(item)} ({decision.get('decision', '')})",
            ]
            if decision.get("reasoning"):
                lines.append(f"Why: {decision['reasoning']}")
            lines += [f"Apply: {job.get('url', 'No link')}", ""]
    return "\n".join(lines)


def collect_attachments(
    top_jobs: dict[str, list[dict]],
    generated_documents: list[dict],
) -> list[str]:
    lookup = build_document_lookup(generated_documents)
    attachments: list[str] = []
    seen: set[str] = set()

    for code, items in top_jobs.items():
        for item in items:
            job = item.get("job", {})
            docs = lookup.get(make_key(code, job.get("company", ""), job.get("title", "")))
            if not docs:
                continue
            for path_key in ["cv_pdf_path", "cover_letter_pdf_path"]:
                file_path = docs.get(path_key)
                if file_path and file_path not in seen and Path(file_path).exists():
                    seen.add(file_path)
                    attachments.append(file_path)
    return attachments


def attach_files(message: EmailMessage, attachments: list[str]) -> None:
    for file_path in attachments:
        path = Path(file_path)
        try:
            file_data = path.read_bytes()
        except OSError as exc:
            print(f"Attachment failed: {file_path} → {exc}")
            continue
        message.add_attachment(
            file_data,
            maintype="application",
            subtype="pdf",
            filename=path.name,
        )


def resolve_recipient(
    config: AppConfig,
    profile: dict,
    sender: str,
) -> str:
    return (
        config.notifications.recipient_override
        or (os.getenv("EMAIL_TO") or "").strip()
        or str(profile.get("email", "")).strip()
        or sender
    )


def send_job_email(
    top_jobs: dict,
    generated_documents: list[dict],
    profile: dict,
    config: AppConfig,
) -> bool:
    if not config.notifications.enabled:
        return False
    if not any(top_jobs.values()):
        print("No new suitable jobs; email skipped.")
        return False

    sender = (os.getenv("EMAIL_ADDRESS") or "").strip()
    password = (os.getenv("EMAIL_PASSWORD") or "").strip()
    if not sender or not password:
        raise ValueError("EMAIL_ADDRESS and EMAIL_PASSWORD are required")

    candidate_name = str(profile.get("name", "")).strip()
    recipient = resolve_recipient(config, profile, sender)
    now = datetime.now().strftime("%d/%m/%Y - %H:%M")

    message = EmailMessage()
    counts = ", ".join(f"{code} {len(items)}" for code, items in top_jobs.items() if items)
    message["Subject"] = f"Job Report ({counts}) - {now}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(build_email_body(top_jobs, candidate_name))

    attachments = collect_attachments(top_jobs, generated_documents)
    attach_files(message, attachments)
    print(f"Email attachments found: {len(attachments)}")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.send_message(message)
    except Exception as exc:
        print(f"Email sending failed: {exc}")
        return False

    mark_job_items_as_emailed(top_jobs)
    print("Email sent successfully ✔")
    return True
