from __future__ import annotations

from app_config import AppConfig, SearchConfig


def build_queries(search: SearchConfig) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()

    def add(query: str) -> None:
        cleaned = " ".join(query.split())
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            queries.append(cleaned)

    for role in search.target_roles:
        for level in search.level_terms:
            add(f"{level} {role}")
        add(role)

    for query in search.extra_queries:
        add(query)

    return queries


def normalize_jobspy_row(row, search_query: str) -> dict:
    return {
        "title": row.get("title"),
        "company": row.get("company"),
        "location": row.get("location"),
        "target_market": "UK",
        "url": row.get("job_url"),
        "source": row.get("site"),
        "description": row.get("description") or "",
        "date_posted": str(row.get("date_posted")),
        "search_query": search_query,
    }


def search_jobs_with_jobspy(
    search_term: str,
    search: SearchConfig,
) -> list[dict]:
    from jobspy import scrape_jobs

    jobs_df = scrape_jobs(
        site_name=search.sources,
        search_term=search_term,
        location="UK",
        results_wanted=search.results_per_query,
        hours_old=search.hours_old,
        country_indeed="UK",
        verbose=0,
        linkedin_fetch_description=True,
    )

    if jobs_df is None or jobs_df.empty:
        return []

    return [
        normalize_jobspy_row(row=row, search_query=search_term)
        for _, row in jobs_df.iterrows()
    ]


def fetch_all_jobs_with_jobspy(config: AppConfig) -> list[dict]:
    all_jobs: list[dict] = []

    for query in build_queries(config.search):
        print(f"JobSpy searching: {query} | UK")
        try:
            all_jobs.extend(search_jobs_with_jobspy(query, config.search))
        except Exception as exc:
            print(f"JobSpy failed for {query} | UK: {exc}")

    return all_jobs
