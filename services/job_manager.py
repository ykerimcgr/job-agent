import json


def load_existing_top_jobs(path: str = "outputs/top_jobs.json") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {"UK": []}

    return {"UK": data.get("UK", [])}


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
        job = item.get("job", {})
        key = "|".join(
            [
                str(job.get("title", "")).casefold().strip(),
                str(job.get("company", "")).casefold().strip(),
                str(job.get("url", "")).casefold().strip(),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique


def update_top_jobs(
    existing: dict,
    new_jobs: list[dict],
    max_jobs: int,
) -> dict:
    merged = merge_jobs(existing.get("UK", []), new_jobs)
    return {"UK": sorted(merged, key=get_rate, reverse=True)[:max_jobs]}
