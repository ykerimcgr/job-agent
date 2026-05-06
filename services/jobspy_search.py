from jobspy import scrape_jobs
import re
import unicodedata
import html

from services.job_identity import (
    canonicalize_job_url,
    generate_canonical_job_hash,
    generate_source_job_hash,
    normalize_identity_text,
)


CORE_ROLES = [
    "Operations Analyst",
    "Business Operations Analyst",
    "Performance Analyst",
    "MI Analyst",
    "Reporting Analyst",
    "Data Operations Analyst",
    "Business Analyst",
    "Project Coordinator",
    "PMO Analyst",
    "Commercial Analyst",
    "Growth Analyst",
    "Product Analyst",
]

ISTANBUL_QUERIES = [
    "İş Analisti",
    "Junior İş Analisti",
    "Veri Analisti",
    "Junior Veri Analisti",
    "Raporlama Uzmanı",
    "Raporlama Analisti",
    "Operasyon Uzmanı",
    "Operasyon Analisti",
    "İş Geliştirme Uzmanı",
    "CRM Analisti",
    "Ürün Analisti",
    "Finansal Analist",
    "Business Analyst",
    "Data Analyst",
    "Operations Analyst",
    "Product Analyst",
    "Growth Analyst",
]


LEVEL_TERMS = [
    "Graduate",
    "Junior",
    "Entry Level",
    "Associate",
]


HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
MARKDOWN_ESCAPE_PATTERN = re.compile(r"\\([\\`*_{}\[\]()#+.!&-])")
LONG_SEPARATOR_PATTERN = re.compile(r"(^|\s)-{3,}(\s|$)")

SPONSORSHIP_NEGATIVE_TERMS = [
    "no sponsorship",
    "cannot sponsor",
    "unable to sponsor",
    "not sponsor",
    "does not provide sponsorship",
    "already have the right to work",
    "no visa",
    "visa not provided",
]

SPONSORSHIP_POSITIVE_TERMS = [
    "visa sponsorship available",
    "offers sponsorship",
    "sponsorship available",
    "can sponsor",
    "will sponsor",
    "skilled worker visa",
]

RIGHT_TO_WORK_REQUIRED_TERMS = [
    "must have right to work",
    "right to work in the uk",
    "already have the right to work",
    "eligible to work in the uk",
    "must be authorized to work",
    "work authorization required",
]


def normalize_text(value) -> str:
    if value is None:
        return ""

    text = str(value)
    text = html.unescape(text)
    text = HTML_TAG_PATTERN.sub(" ", text)
    text = MARKDOWN_ESCAPE_PATTERN.sub(r"\1", text)
    text = text.replace("**", " ")
    text = text.replace("*", " ")
    text = text.replace("•", " ")
    text = LONG_SEPARATOR_PATTERN.sub(" ", text)
    text = unicodedata.normalize("NFKC", text)

    return normalize_identity_text(text)


def canonicalize_url(url: str) -> str:
    return canonicalize_job_url(url)


def detect_sponsorship_signal(description_clean: str) -> tuple[str, str]:
    if not description_clean:
        return "unclear", ""

    for term in SPONSORSHIP_NEGATIVE_TERMS:
        if term in description_clean:
            return "negative", term

    for term in SPONSORSHIP_POSITIVE_TERMS:
        if term in description_clean:
            return "positive", term

    return "unclear", ""


def detect_right_to_work_required(description_clean: str) -> bool:
    if not description_clean:
        return False
    return any(term in description_clean for term in RIGHT_TO_WORK_REQUIRED_TERMS)


def generate_stable_job_hash(
    title: str,
    company: str,
    location: str,
    target_location: str,
    url: str,
) -> str:
    # Backward-compatible wrapper name; this now maps to canonical_job_hash.
    return generate_canonical_job_hash({
        "title": title,
        "company": company,
        "location": location,
        "target_location": target_location,
        "url": url,
    })


def build_queries_for_location(location: str):
    if location == "London":
        queries = []
        for role in CORE_ROLES:
            for level in LEVEL_TERMS:
                queries.append(f"{level} {role}")
        return queries

    if location == "Istanbul":
        return ISTANBUL_QUERIES

    return []


def normalize_jobspy_row(row, target_location: str, search_query: str) -> dict:
    description_original = row.get("description") or ""
    description_clean = normalize_text(description_original)
    sponsorship_signal, sponsorship_text_found = detect_sponsorship_signal(
        description_clean
    )
    right_to_work_required = detect_right_to_work_required(description_clean)

    title = row.get("title")
    company = row.get("company")
    location = row.get("location")
    url = row.get("job_url")

    source = row.get("site")

    normalized_job = {
        "title": title,
        "company": company,
        "location": location,
        "target_location": target_location,
        "url": url,
        "source": source,
        "source_job_id": row.get("job_id") or row.get("id"),
        "description": description_original,
        "description_markdown": description_original,
        "description_clean": description_clean,
        "sponsorship_signal": sponsorship_signal,
        "sponsorship_text_found": sponsorship_text_found,
        "right_to_work_required": right_to_work_required,
        "date_posted": str(row.get("date_posted")),
        "search_query": search_query,
    }

    source_job_hash = generate_source_job_hash(normalized_job)
    canonical_job_hash = generate_canonical_job_hash(normalized_job)

    normalized_job["source_job_hash"] = source_job_hash
    normalized_job["canonical_job_hash"] = canonical_job_hash
    # Keep legacy field name for compatibility.
    normalized_job["job_hash"] = source_job_hash

    return normalized_job


def search_jobs_with_jobspy(
    search_term: str,
    location: str,
    results_wanted: int = 25
) -> list[dict]:
    country_indeed = "UK" if location.lower() == "london" else "Turkey"

    jobs_df = scrape_jobs(
        site_name=["indeed", "linkedin"],
        search_term=search_term,
        location=location,
        results_wanted=results_wanted,
        hours_old=168,
        country_indeed=country_indeed,
        verbose=0,
        linkedin_fetch_description=True
    )

    jobs = []

    for _, row in jobs_df.iterrows():
        jobs.append(
            normalize_jobspy_row(
                row=row,
                target_location=location,
                search_query=search_term
            )
        )

    return jobs


def fetch_all_jobs_with_jobspy(
    results_per_query: int = 10
) -> list[dict]:
    locations = ["London", "Istanbul"]

    all_jobs = []

    for location in locations:
        queries = build_queries_for_location(location)
        
        for query in queries:
            print(f"JobSpy searching: {query} | {location}")

            try:
                jobs = search_jobs_with_jobspy(
                    search_term=query,
                    location=location,
                    results_wanted=results_per_query
                )
                all_jobs.extend(jobs)

            except Exception as e:
                print(f"JobSpy failed for {query} | {location}: {e}")

    return all_jobs
