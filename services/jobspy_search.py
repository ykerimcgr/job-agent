from __future__ import annotations

from app_config import MarketConfig, SearchConfig


def build_queries(search: SearchConfig, market: MarketConfig | None = None) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    level_terms = search.level_terms
    extra_queries = list(search.extra_queries)
    if market is not None:
        if market.level_terms is not None:
            level_terms = market.level_terms
        extra_queries += market.extra_queries

    def add(query: str) -> None:
        cleaned = " ".join(query.split())
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            queries.append(cleaned)

    if market is not None and market.queries is not None:
        for query in market.queries:
            add(query)
        return queries

    for role in search.target_roles:
        for level in level_terms:
            if level.casefold() not in role.casefold():  # no "Graduate Graduate Analyst"
                add(f"{level} {role}")
        add(role)

    for query in extra_queries:
        add(query)

    return queries


def normalize_jobspy_row(row, search_query: str, market_code: str) -> dict:
    return {
        "title": row.get("title"),
        "company": row.get("company"),
        "location": row.get("location"),
        "target_market": market_code,
        "url": row.get("job_url"),
        "source": row.get("site"),
        "description": row.get("description") or "",
        "date_posted": str(row.get("date_posted")),
        "search_query": search_query,
    }


def search_jobs_with_jobspy(
    search_term: str,
    search: SearchConfig,
    market: MarketConfig,
) -> list[dict]:
    from jobspy import scrape_jobs

    jobs_df = scrape_jobs(
        site_name=search.sources,
        search_term=search_term,
        location=market.search_location,
        results_wanted=search.results_per_query,
        hours_old=search.hours_old,
        country_indeed=market.country_indeed,
        verbose=0,
        linkedin_fetch_description=True,
    )

    if jobs_df is None or jobs_df.empty:
        return []

    return [
        normalize_jobspy_row(row=row, search_query=search_term, market_code=market.code)
        for _, row in jobs_df.iterrows()
    ]


def fetch_jobs_for_market(search: SearchConfig, market: MarketConfig) -> list[dict]:
    all_jobs: list[dict] = []

    for query in build_queries(search, market):
        print(f"JobSpy searching: {query} | {market.code}")
        try:
            all_jobs.extend(search_jobs_with_jobspy(query, search, market))
        except Exception as exc:
            print(f"JobSpy failed for {query} | {market.code}: {exc}")

    return all_jobs
