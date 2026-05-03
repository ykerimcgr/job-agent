from __future__ import annotations

from typing import Optional

from .config import FilterConfig
from .pipeline import JobFilter
from .types import Job


def explain_job(
    job: Job,
    config: Optional[FilterConfig] = None,
) -> Job:
    cfg = config or FilterConfig()
    job_filter = JobFilter(config=cfg)

    job_copy = dict(job)

    reject_result = job_filter.rejector.check(job_copy)

    if reject_result.rejected:
        job_copy["decision"] = "rejected"
        job_copy["reject_reason"] = reject_result.reason
        return job_copy

    score_result = job_filter.scorer.score(job_copy)

    job_copy["pre_score"] = score_result.score
    job_copy["quality_flags"] = score_result.quality_flags
    job_copy["risk_flags"] = score_result.risk_flags

    if score_result.score < cfg.min_score:
        job_copy["decision"] = "rejected"
        job_copy["reject_reason"] = "low_score"
    else:
        job_copy["decision"] = "accepted"

    return job_copy