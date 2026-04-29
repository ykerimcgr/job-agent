import json

def load_existing_top_jobs(path="outputs/top_jobs.json"):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return {"London": [], "Istanbul": []}


def get_rate(job):
    return (
        job.get("score_result", {})
        .get("application_decision", {})
        .get("applicable_rate", 0)
    )


def merge_jobs(existing_jobs, new_jobs):
    all_jobs = existing_jobs + new_jobs

    # duplicate kaldır (title + company)
    seen = set()
    unique = []

    for job in all_jobs:
        key = (
            job["job"].get("title", "") +
            job["job"].get("company", "")
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(job)

    return unique


def update_top_jobs(existing, new_london, new_istanbul, max_jobs=10):
    # merge
    london_all = merge_jobs(existing["London"], new_london)
    istanbul_all = merge_jobs(existing["Istanbul"], new_istanbul)

    # sort
    london_sorted = sorted(london_all, key=get_rate, reverse=True)
    istanbul_sorted = sorted(istanbul_all, key=get_rate, reverse=True)

    # cut
    return {
        "London": london_sorted[:max_jobs],
        "Istanbul": istanbul_sorted[:max_jobs]
    }