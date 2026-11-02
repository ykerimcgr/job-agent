"""The single definition of "the same job", shared by dedup, archive and emailed-state."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse

from .normalizer import TextNormalizer


LINKEDIN_JOB_ID = re.compile(r"/jobs/view/(?:[^/]*-)?(\d+)")
NON_ALNUM = re.compile(r"[^a-z0-9]+")
COMPANY_SUFFIX = re.compile(r"\s+(ltd|limited|plc|inc|llc|llp|a s|as|san ve tic)$")
TRACKING_PARAMS = ("utm_", "ref", "trk", "from", "tracking")


def source_job_id(url: str | None) -> str:
    """Stable id of a listing on its own site, or "" when the URL cannot identify it."""
    parsed = urlparse((url or "").strip())
    host = parsed.netloc.casefold().removeprefix("www.")
    if not host:
        return ""
    query = dict(parse_qsl(parsed.query))

    if "indeed." in host:
        job_key = query.get("jk") or query.get("vjk")
        return f"indeed:{job_key}" if job_key else ""
    if "linkedin." in host:
        match = LINKEDIN_JOB_ID.search(parsed.path)
        job_id = match.group(1) if match else query.get("currentJobId")
        return f"linkedin:{job_id}" if job_id else ""

    kept = sorted(
        (key, value)
        for key, value in query.items()
        if not key.casefold().startswith(TRACKING_PARAMS)
    )
    suffix = f"?{urlencode(kept)}" if kept else ""
    return f"url:{host}{parsed.path.rstrip('/')}{suffix}".casefold()


def _simplify(value) -> str:
    return NON_ALNUM.sub(" ", TextNormalizer.normalize(value)).strip()


def content_key(job: dict) -> str:
    """Title + company + market: catches the same job posted on several sites."""
    title = _simplify(job.get("title"))
    if not title:
        return ""
    company = COMPANY_SUFFIX.sub("", _simplify(job.get("company")))
    market = str(job.get("target_market") or "").upper()
    return f"{title}|{company}|{market}"


def job_identity(job: dict) -> str:
    """Hash used for the emailed-jobs table and the local archive."""
    key = content_key(job) or source_job_id(job.get("url")) or legacy_emailed_hash(job)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def legacy_emailed_hash(job: dict) -> str:
    # shortcut: pre-refactor emailed_jobs rows used this hash; drop once those rows are older than a few weeks.
    raw = "|".join(
        (job.get(field) or "").casefold().strip()
        for field in ("title", "company", "location", "url")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
