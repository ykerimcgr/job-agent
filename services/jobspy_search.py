from jobspy import scrape_jobs


CORE_ROLES = [
    "Operations Analyst",
    "Business Operations Analyst",
    "Performance Analyst"
    "MI Analyst",
    "Reporting Analyst",
    "Data Operations Analyst",
    "Business Analyst",
    "Project Coordinator",
    "PMO Analyst",
    "Commercial Analyst",
    "Growth Analyst",
    "Product Analyst"
]

ISTANBUL_QUERIES = [
    "İş Analisti",
    "Junior İş Analisti"
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
    "Growth Analyst"
]


LEVEL_TERMS = [
    "Graduate",
    "Junior",
    "Entry Level",
    "Associate"
]


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
    return {
        "title": row.get("title"),
        "company": row.get("company"),
        "location": row.get("location"),
        "target_location": target_location,
        "url": row.get("job_url"),
        "source": row.get("site"),
        "description": row.get("description") or "",
        "date_posted": str(row.get("date_posted")),
        "search_query": search_query,
    }


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