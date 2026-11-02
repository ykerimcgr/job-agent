from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import shutil

from agents.profile_extractor import (
    PROFILE_MODEL,
    PROFILE_PROMPT_VERSION,
    extract_profile_from_cv,
)
from app_config import AppConfig, CONFIG_PATH, CV_PATH
from filter import filter_jobs, select_top_candidates
from services.cache import generate_text_hash
from services.document_generator import generate_documents_for_top_jobs
from services.email_sender import send_job_email
from services.job_manager import load_existing_top_jobs, update_top_jobs
from services.job_scoring_pipeline import score_jobs_batch, select_top_jobs
from services.jobspy_search import fetch_all_jobs_with_jobspy
from services.openai_client import get_openai_api_key
from services.state_store import (
    check_supabase_connection,
    filter_out_emailed_jobs,
    load_cached_profile,
    save_profile_cache,
)


OUTPUT_DIR = Path("outputs")
JOBSPY_DIR = OUTPUT_DIR / "Jobspy"
UK_DIR = OUTPUT_DIR / "UK"
HISTORY_DIR = OUTPUT_DIR / "history"


def ensure_output_directories() -> None:
    for folder in [OUTPUT_DIR, JOBSPY_DIR, UK_DIR, HISTORY_DIR]:
        folder.mkdir(parents=True, exist_ok=True)


def save_json(path: str | Path, data) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def validate_runtime(config: AppConfig) -> None:
    errors: list[str] = []

    if not CV_PATH.exists() or not CV_PATH.read_text(encoding="utf-8").strip():
        errors.append(f"{CV_PATH} is missing or empty")
    if not get_openai_api_key():
        errors.append(
            "OPENAI_API_KEY is missing "
            "(legacy OPEN_AI_SECRET_KEY is also supported)"
        )
    if not (os.getenv("SUPABASE_URL") or "").strip():
        errors.append("SUPABASE_URL is missing")
    if not (os.getenv("SUPABASE_KEY") or "").strip():
        errors.append("SUPABASE_KEY is missing")
    if config.notifications.enabled:
        if not (os.getenv("EMAIL_ADDRESS") or "").strip():
            errors.append("EMAIL_ADDRESS is missing")
        if not (os.getenv("EMAIL_PASSWORD") or "").strip():
            errors.append("EMAIL_PASSWORD is missing")

    if errors:
        raise ValueError("Runtime configuration errors:\n- " + "\n- ".join(errors))

    if config.documents.enabled and shutil.which("pdflatex") is None:
        print("Warning: pdflatex not found; .tex files will be generated without PDFs.")


def load_or_extract_profile(config: AppConfig) -> tuple[dict, str, str]:
    print("\n=== STEP 1: CV → PROFILE ===")
    cv_text = CV_PATH.read_text(encoding="utf-8")
    cv_hash = generate_text_hash(
        f"{PROFILE_PROMPT_VERSION}|{PROFILE_MODEL}|{cv_text}"
    )
    profile = load_cached_profile(cv_hash)

    if profile:
        print("Profile loaded from Supabase cache ✔")
    else:
        print("No profile cache found → extracting with OpenAI")
        profile = extract_profile_from_cv(cv_text)
        save_profile_cache(cv_hash, profile)
        print("Profile extracted and saved to Supabase cache ✔")

    merged_profile = config.merge_profile(profile)
    profile_hash = generate_text_hash(
        json.dumps(merged_profile, sort_keys=True, ensure_ascii=False)
    )
    save_json("profile/profile_extracted.json", merged_profile)
    return merged_profile, profile_hash, cv_text


def print_top_jobs(title: str, jobs: list[dict]) -> None:
    print(f"\n=== {title} ===")
    if not jobs:
        print("No suitable jobs found.")
        return
    for item in jobs:
        job = item.get("job", {})
        decision = item.get("score_result", {}).get("application_decision", {})
        print(
            f"- {decision.get('applicable_rate', 0)} | "
            f"{decision.get('decision', '')} | "
            f"{job.get('title')} | {job.get('company')}"
        )


def run_pipeline_once(
    *,
    config: AppConfig | None = None,
    perform_preflight: bool = True,
) -> dict:
    app_config = config or AppConfig.load(CONFIG_PATH)
    if perform_preflight:
        validate_runtime(app_config)
        check_supabase_connection()

    ensure_output_directories()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("\n==============================")
    print("UK AI JOB AGENT PIPELINE STARTED")
    print("==============================")

    profile, profile_hash, master_cv_text = load_or_extract_profile(app_config)

    print("\n=== STEP 2: FETCH UK JOBS WITH JOBSPY ===")
    raw_jobs = fetch_all_jobs_with_jobspy(app_config)
    save_json(JOBSPY_DIR / "jobspy_raw.json", raw_jobs)
    save_json(JOBSPY_DIR / f"jobspy_raw_{timestamp}.json", raw_jobs)

    print("\n=== STEP 3: FILTER JOBS ===")
    filtered_jobs, rejected_jobs = filter_jobs(raw_jobs, app_config)
    print(f"Filtered jobs: {len(filtered_jobs)}")
    print(f"Rejected jobs: {len(rejected_jobs)}")
    save_json(JOBSPY_DIR / "jobspy_filtered.json", filtered_jobs)
    save_json(JOBSPY_DIR / "jobspy_rejected.json", rejected_jobs)

    print("\n=== STEP 4: REMOVE ALREADY EMAILED JOBS ===")
    fresh_jobs = filter_out_emailed_jobs(filtered_jobs)
    print(f"Fresh filtered jobs: {len(fresh_jobs)}")
    print(f"Already emailed jobs removed: {len(filtered_jobs) - len(fresh_jobs)}")
    save_json(JOBSPY_DIR / "fresh_filtered_jobs.json", fresh_jobs)

    print("\n=== STEP 5: SELECT AI CANDIDATES ===")
    candidates = select_top_candidates(
        fresh_jobs,
        app_config.selection.ai_candidate_limit,
    )
    print(f"UK candidates for AI: {len(candidates)}")
    save_json(UK_DIR / "uk_candidates.json", candidates)

    print("\n=== STEP 6: AI SCORE CANDIDATES ===")
    scored_jobs = score_jobs_batch(
        jobs=candidates,
        profile=profile,
        profile_hash=profile_hash,
        config=app_config,
    )
    save_json(UK_DIR / "uk_scored.json", scored_jobs)

    print("\n=== STEP 7: SELECT TOP JOBS ===")
    top_uk = select_top_jobs(scored_jobs, app_config)
    current_run = {"UK": top_uk}
    archive = update_top_jobs(
        existing=load_existing_top_jobs(),
        new_jobs=top_uk,
        max_jobs=app_config.selection.max_jobs,
    )
    save_json(OUTPUT_DIR / "top_jobs_current_run.json", current_run)
    save_json(OUTPUT_DIR / "top_jobs.json", archive)
    save_json(HISTORY_DIR / f"top_jobs_{timestamp}.json", archive)
    print_top_jobs("CURRENT RUN TOP UK JOBS", current_run["UK"])
    print_top_jobs("ARCHIVED TOP UK JOBS", archive["UK"])

    generated_documents: list[dict] = []
    if current_run["UK"] and app_config.documents.enabled:
        print("\n=== STEP 8: GENERATE CV + COVER LETTER ===")
        generated_documents = generate_documents_for_top_jobs(
            top_jobs=current_run,
            profile=profile,
            master_cv_text=master_cv_text,
            config=app_config,
        )
    else:
        print("\n=== STEP 8: DOCUMENT GENERATION SKIPPED ===")

    save_json(OUTPUT_DIR / "generated_documents.json", generated_documents)
    save_json(
        HISTORY_DIR / f"generated_documents_{timestamp}.json",
        generated_documents,
    )

    email_sent = False
    if current_run["UK"] and app_config.notifications.enabled:
        print("\n=== STEP 9: SEND EMAIL ===")
        email_sent = send_job_email(
            top_jobs=current_run,
            generated_documents=generated_documents,
            profile=profile,
            config=app_config,
        )
    else:
        print("\n=== STEP 9: EMAIL SKIPPED ===")

    print("\n==============================")
    print("UK AI JOB AGENT PIPELINE COMPLETED ✔")
    print("==============================")
    return {
        "top_jobs": current_run,
        "generated_documents": generated_documents,
        "email_sent": email_sent,
    }


def _truthy_environment(name: str) -> bool:
    return (os.getenv(name) or "").strip().casefold() in {"1", "true", "yes"}


def main() -> None:
    config = AppConfig.load(CONFIG_PATH)
    enforce_schedule = _truthy_environment("ENFORCE_SCHEDULE")
    force_run = _truthy_environment("FORCE_RUN")
    if enforce_schedule and not config.schedule.should_run(force=force_run):
        print("Outside the configured schedule window; pipeline skipped.")
        return
    run_pipeline_once(config=config)


if __name__ == "__main__":
    main()
