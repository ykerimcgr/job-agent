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


def _text(value) -> str:
    # JobSpy rows come from pandas: a missing value is None or NaN (a truthy float).
    if value is None or value != value:
        return ""
    return str(value)


def normalize_jobspy_row(row, search_query: str, market_code: str) -> dict:
    return {
        "title": _text(row.get("title")),
        "company": _text(row.get("company")),
        "location": _text(row.get("location")),
        "target_market": market_code,
        "url": _text(row.get("job_url")),
        "source": _text(row.get("site")),
        "description": _text(row.get("description")),
        "date_posted": _text(row.get("date_posted")),
        "search_query": search_query,
        "is_remote": row.get("is_remote") is True,
    }


def search_plan(search: SearchConfig, market: MarketConfig) -> list[tuple[str, str, bool]]:
    """Every (query, location, remote) search this market runs: its own place first, then extras."""
    queries = build_queries(search, market)
    plan = [(query, market.search_location, False) for query in queries]
    for extra in market.extra_searches:
        plan += [(query, extra.location, extra.remote) for query in (extra.queries or queries)]
    return plan


def scrape_arguments(
    search_term: str,
    search: SearchConfig,
    market: MarketConfig,
    location: str | None = None,
    remote: bool = False,
) -> dict:
    sources = market.sources or search.sources
    location = location or market.search_location
    hours_old = market.hours_old or search.hours_old
    arguments = {
        "site_name": sources,
        "search_term": search_term,
        "location": location,
        "results_wanted": market.results_per_query or search.results_per_query,
        "hours_old": hours_old,
        "country_indeed": market.country_indeed,
        "verbose": 0,
        "linkedin_fetch_description": True,
    }
    if remote:
        arguments["is_remote"] = True
    if "google" in sources:
        # Google Jobs ignores search_term/location/hours_old and needs one natural-language query.
        days = max(1, round(hours_old / 24))
        arguments["google_search_term"] = f"{search_term} jobs near {location} in the last {days} days"
    return arguments


def search_jobs_with_jobspy(
    search_term: str,
    search: SearchConfig,
    market: MarketConfig,
    location: str | None = None,
    remote: bool = False,
) -> list[dict]:
    from jobspy import scrape_jobs

    jobs_df = scrape_jobs(**scrape_arguments(search_term, search, market, location, remote))

    if jobs_df is None or jobs_df.empty:
        return []

    return [
        normalize_jobspy_row(row=row, search_query=search_term, market_code=market.code)
        for _, row in jobs_df.iterrows()
    ]


def fetch_jobs_for_market(search: SearchConfig, market: MarketConfig) -> list[dict]:
    all_jobs: list[dict] = []

    for query, location, remote in search_plan(search, market):
        label = f"{query} | {market.code} | {location}{' (remote)' if remote else ''}"
        print(f"JobSpy searching: {label}")
        try:
            all_jobs.extend(search_jobs_with_jobspy(query, search, market, location, remote))
        except Exception as exc:
            print(f"JobSpy failed for {label}: {exc}")

    return all_jobs
