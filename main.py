import json
from pathlib import Path
from datetime import datetime

from agents.profile_extractor import extract_profile_from_cv
from services.cache import (
    generate_text_hash,
    load_cached_profile,
    save_profile_cache
)

from services.jobspy_search import fetch_all_jobs_with_jobspy
from services.jobspy_filter import filter_jobs, split_top_jobs_by_location
from services.job_scoring_pipeline import score_jobs_batch, select_top_jobs
from services.job_manager import load_existing_top_jobs, update_top_jobs
from services.document_generator import generate_documents_for_top_jobs


OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


def save_json(path: str, data):
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
        print("Profile loaded from cache ✔")
        profile = cached_profile
    else:
        print("No profile cache found → extracting with OpenAI")
        profile = extract_profile_from_cv(cv_text)
        save_profile_cache(cv_hash, profile)
        print("Profile extracted and saved to cache ✔")

    save_json("profile/profile_extracted.json", profile)

    return profile


def run_pipeline_once():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1) Profile
    profile = load_or_extract_profile()

    contact_rules = load_json("profile/contact_rules.json")
    location_rules = load_json("profile/location_rules.json")

    print("Contact/location rules loaded ✔")

    # 2) Fetch jobs
    print("\n=== STEP 2: FETCH JOBS WITH JOBSPY ===")

    raw_jobs = fetch_all_jobs_with_jobspy(results_per_query=8)

    print(f"Raw jobs fetched: {len(raw_jobs)}")
    save_json("outputs/jobspy_raw.json", raw_jobs)
    save_json(f"outputs/jobspy_raw_{timestamp}.json", raw_jobs)

    # 3) Filter jobs
    print("\n=== STEP 3: FILTER JOBS ===")

    filtered_jobs, rejected_jobs = filter_jobs(raw_jobs)

    print(f"Filtered jobs: {len(filtered_jobs)}")
    print(f"Rejected jobs: {len(rejected_jobs)}")

    save_json("outputs/jobspy_filtered.json", filtered_jobs)
    save_json("outputs/jobspy_rejected.json", rejected_jobs)

    # 4) Split London / Istanbul candidates
    print("\n=== STEP 4: SPLIT TOP CANDIDATES ===")

    london_candidates, istanbul_candidates = split_top_jobs_by_location(
        filtered_jobs,
        london_limit=20,
        istanbul_limit=20
    )

    print(f"London candidates for AI: {len(london_candidates)}")
    print(f"Istanbul candidates for AI: {len(istanbul_candidates)}")

    save_json("outputs/london_candidates.json", london_candidates)
    save_json("outputs/istanbul_candidates.json", istanbul_candidates)

    # 5) AI score London
    print("\n=== STEP 5: AI SCORE LONDON CANDIDATES ===")

    london_scored = score_jobs_batch(
        jobs=london_candidates,
        profile=profile,
        contact_rules=contact_rules,
        location_rules=location_rules
    )

    save_json("outputs/london_scored.json", london_scored)

    # 6) AI score Istanbul
    print("\n=== STEP 6: AI SCORE ISTANBUL CANDIDATES ===")

    istanbul_scored = score_jobs_batch(
        jobs=istanbul_candidates,
        profile=profile,
        contact_rules=contact_rules,
        location_rules=location_rules
    )

    save_json("outputs/istanbul_scored.json", istanbul_scored)

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

    existing_top_jobs = load_existing_top_jobs()

    top_jobs = update_top_jobs(
        existing=existing_top_jobs,
        new_london=top_london,
        new_istanbul=top_istanbul,
        max_jobs=10
    )

    save_json("outputs/top_jobs.json", top_jobs)
    save_json(f"outputs/top_jobs_{timestamp}.json", top_jobs)

    print(f"Top London jobs: {len(top_london)}")
    print(f"Top Istanbul jobs: {len(top_istanbul)}")

    # 8) Summary print
    print("\n=== TOP LONDON JOBS ===")
    for item in top_jobs["London"]:
        job = item.get("job", {})
        score = item.get("score_result", {})
        rate = score.get("application_decision", {}).get("applicable_rate", 0)
        decision = score.get("application_decision", {}).get("decision", "")

        print(f"- {rate} | {decision} | {job.get('title')} | {job.get('company')}")

    print("\n=== TOP ISTANBUL JOBS ===")
    for item in top_jobs["Istanbul"]:
        job = item.get("job", {})
        score = item.get("score_result", {})
        rate = score.get("application_decision", {}).get("applicable_rate", 0)
        decision = score.get("application_decision", {}).get("decision", "")

        print(f"- {rate} | {decision} | {job.get('title')} | {job.get('company')}")

    print("\nPipeline completed ✔")

    print("\n=== STEP 8: GENERATE CV + COVER LETTER ===")

    master_cv_text = load_cv()

    generated_documents = generate_documents_for_top_jobs(
        top_jobs=top_jobs,
        profile=profile,
        master_cv_text=master_cv_text,
        contact_rules=contact_rules,
        location_rules=location_rules
    )

    save_json("outputs/generated_documents.json", generated_documents)

    print(f"Generated document sets: {len(generated_documents)}")
    print("Saved outputs/generated_documents.json ✔")


if __name__ == "__main__":
    run_pipeline_once()