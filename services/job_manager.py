import json

from filter.identity import job_identity


def load_existing_top_jobs(path: str = "outputs/top_jobs.json") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def get_rate(job: dict) -> float:
    return (
        job.get("score_result", {})
        .get("application_decision", {})
        .get("applicable_rate", 0)
    )


def merge_jobs(existing_jobs: list[dict], new_jobs: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []

    for item in new_jobs + existing_jobs:
        key = job_identity(item.get("job", {}))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique


def update_top_jobs(
    existing: dict,
    new_jobs: dict,
    max_jobs: int,
) -> dict:
    """Merge this run's top jobs into the archive, per market."""
    archive = dict(existing)
    for code, jobs in new_jobs.items():
        merged = merge_jobs(existing.get(code, []), jobs)
        archive[code] = sorted(merged, key=get_rate, reverse=True)[:max_jobs]
    return archive
