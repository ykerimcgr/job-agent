import json
from pathlib import Path
from datetime import datetime

from agents.profile_extractor import extract_profile_from_cv

from services.cache import generate_text_hash

from services.state_store import (
    load_cached_profile,
    save_profile_cache,
    filter_out_emailed_jobs
)

from services.jobspy_search import fetch_all_jobs_with_jobspy
from services.job_scoring_pipeline import score_jobs_batch, select_top_jobs
from services.job_manager import load_existing_top_jobs, update_top_jobs
from services.document_generator import generate_documents_for_top_jobs
from services.email_sender import send_job_email

from filter import filter_jobs, split_top_jobs_by_location


OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

JOBSPY_DIR = OUTPUT_DIR / "Jobspy"
LONDON_DIR = OUTPUT_DIR / "Ldn"
ISTANBUL_DIR = OUTPUT_DIR / "Ist"
HISTORY_DIR = OUTPUT_DIR / "history"

for folder in [JOBSPY_DIR, LONDON_DIR, ISTANBUL_DIR, HISTORY_DIR]:
    folder.mkdir(parents=True, exist_ok=True)


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_json(path: str):
    with open(path, "r") as f:
        return json.load(f)


def load_cv():
    with open("profile/master_cv.tex", "r") as f:
        return f.read()


def load_or_extract_profile():
    print("\n=== STEP 1: CV → PROFILE ===")

    cv_text = load_cv()
    cv_hash = generate_text_hash(cv_text)

    cached_profile = load_cached_profile(cv_hash)

    if cached_profile:
        profile = cached_profile
        print("Profile loaded from Supabase cache ✔")
    else:
        print("No profile cache found → extracting with OpenAI")
        profile = extract_profile_from_cv(cv_text)
        save_profile_cache(cv_hash, profile)
        print("Profile extracted and saved to Supabase cache ✔")

    save_json("profile/profile_extracted.json", profile)

    return profile


def print_top_jobs(title: str, jobs: list[dict]):
    print(f"\n=== {title} ===")

    if not jobs:
        print("No suitable jobs found.")
        return

    for item in jobs:
        job = item.get("job", {})
        score = item.get("score_result", {})
        decision_data = score.get("application_decision", {})

        rate = decision_data.get("applicable_rate", 0)
        decision = decision_data.get("decision", "")

        print(
            f"- {rate} | {decision} | "
            f"{job.get('title')} | {job.get('company')}"
        )


def run_pipeline_once(send_email: bool = True):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("\n==============================")
    print("AI JOB AGENT PIPELINE STARTED")
    print("==============================")

    # 1) Profile
    profile = load_or_extract_profile()

    contact_rules = load_json("profile/contact_rules.json")
    location_rules = load_json("profile/location_rules.json")

    print("Contact/location rules loaded ✔")

    # 2) Fetch jobs
    print("\n=== STEP 2: FETCH JOBS WITH JOBSPY ===")

    raw_jobs = fetch_all_jobs_with_jobspy(results_per_query=1)

    save_json(JOBSPY_DIR / "jobspy_raw.json", raw_jobs)
    save_json(JOBSPY_DIR / f"jobspy_raw_{timestamp}.json", raw_jobs)


    # 3) Filter jobs
    print("\n=== STEP 3: FILTER JOBS ===")

    filtered_jobs, rejected_jobs = filter_jobs(raw_jobs)

    print(f"Filtered jobs: {len(filtered_jobs)}")
    print(f"Rejected jobs: {len(rejected_jobs)}")

    save_json(JOBSPY_DIR / "jobspy_filtered.json", filtered_jobs)
    save_json(JOBSPY_DIR / "jobspy_rejected.json", rejected_jobs)

    # 3.5) Remove already emailed jobs before AI scoring
    print("\n=== STEP 3.5: REMOVE ALREADY EMAILED JOBS ===")

    fresh_filtered_jobs = filter_out_emailed_jobs(filtered_jobs)

    print(f"Fresh filtered jobs: {len(fresh_filtered_jobs)}")
    print(f"Already emailed jobs removed: {len(filtered_jobs) - len(fresh_filtered_jobs)}")

    save_json(JOBSPY_DIR / "fresh_filtered_jobs.json", fresh_filtered_jobs)

    # 4) Split London / Istanbul candidates
    print("\n=== STEP 4: SPLIT TOP CANDIDATES ===")

    london_candidates, istanbul_candidates = split_top_jobs_by_location(
        fresh_filtered_jobs,
        london_limit=20,
        istanbul_limit=20
    )

    print(f"London candidates for AI: {len(london_candidates)}")
    print(f"Istanbul candidates for AI: {len(istanbul_candidates)}")

    save_json(LONDON_DIR / "london_candidates.json", london_candidates)
    save_json(ISTANBUL_DIR / "istanbul_candidates.json", istanbul_candidates)

    # 5) AI score London
    print("\n=== STEP 5: AI SCORE LONDON CANDIDATES ===")

    london_scored = score_jobs_batch(
        jobs=london_candidates,
        profile=profile,
        contact_rules=contact_rules,
        location_rules=location_rules
    )

    save_json(LONDON_DIR / "london_scored.json", london_scored)

    # 6) AI score Istanbul
    print("\n=== STEP 6: AI SCORE ISTANBUL CANDIDATES ===")

    istanbul_scored = score_jobs_batch(
        jobs=istanbul_candidates,
        profile=profile,
        contact_rules=contact_rules,
        location_rules=location_rules
    )

    save_json(ISTANBUL_DIR / "istanbul_scored.json", istanbul_scored)

    # 7) Select top jobs
    print("\n=== STEP 7: SELECT TOP JOBS ===")

    top_london = select_top_jobs(
        london_scored,
        min_jobs=5,
        max_jobs=10
    )

    top_istanbul = select_top_jobs(
        istanbul_scored,
        min_jobs=5,
        max_jobs=10
    )

    # Fresh recommendations from this run only
    top_jobs_current_run = {
        "London": top_london,
        "Istanbul": top_istanbul
    }

    # Archive / latest best known jobs
    existing_top_jobs = load_existing_top_jobs()

    top_jobs_archive = update_top_jobs(
        existing=existing_top_jobs,
        new_london=top_london,
        new_istanbul=top_istanbul,
        max_jobs=10
    )

    save_json(OUTPUT_DIR / "top_jobs_current_run.json", top_jobs_current_run)
    save_json(OUTPUT_DIR / "top_jobs.json", top_jobs_archive)
    save_json(HISTORY_DIR / f"top_jobs_{timestamp}.json", top_jobs_archive)

    print(f"New top London jobs from this run: {len(top_london)}")
    print(f"New top Istanbul jobs from this run: {len(top_istanbul)}")

    print_top_jobs("CURRENT RUN TOP LONDON JOBS", top_jobs_current_run.get("London", []))
    print_top_jobs("CURRENT RUN TOP ISTANBUL JOBS", top_jobs_current_run.get("Istanbul", []))

    print_top_jobs("ARCHIVED TOP LONDON JOBS", top_jobs_archive.get("London", []))
    print_top_jobs("ARCHIVED TOP ISTANBUL JOBS", top_jobs_archive.get("Istanbul", []))

    # 8) Generate CV + Cover Letter
    print("\n=== STEP 8: GENERATE CV + COVER LETTER ===")

    master_cv_text = load_cv()

    top_jobs=top_jobs_current_run

    generated_documents = generate_documents_for_top_jobs(
        top_jobs=top_jobs,
        profile=profile,
        master_cv_text=master_cv_text,
        contact_rules=contact_rules,
        location_rules=location_rules
    )

    save_json(OUTPUT_DIR / "generated_documents.json", generated_documents)
    save_json(HISTORY_DIR / f"generated_documents_{timestamp}.json", generated_documents)

    print(f"Generated document sets: {len(generated_documents)}")
    print("Saved generated document metadata ✔")

    # 9) Send email
    if send_email:
        print("\n=== STEP 9: SEND EMAIL ===")

        send_job_email(
            top_jobs=top_jobs,
            generated_documents=generated_documents
        )

    print("\n==============================")
    print("AI JOB AGENT PIPELINE COMPLETED ✔")
    print("==============================")



    


if __name__ == "__main__":
    run_pipeline_once(send_email=True)