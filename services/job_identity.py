import hashlib
import html
import math
import re
import unicodedata
from urllib.parse import urlparse, urlunparse


HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_identity_text(value) -> str:
    if value is None:
        return ""

    if isinstance(value, float) and math.isnan(value):
        return ""

    try:
        if value != value:
            return ""
    except Exception:
        pass

    text = str(value)
    text = html.unescape(text)
    text = HTML_TAG_PATTERN.sub(" ", text)
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()
    text = "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def canonicalize_job_url(url: str) -> str:
    normalized_url = normalize_identity_text(url)

    if not normalized_url:
        return ""

    parsed = urlparse(normalized_url)

    if not parsed.netloc:
        return ""

    cleaned = parsed._replace(query="", fragment="")
    canonical = urlunparse(cleaned).rstrip("/")

    return normalize_identity_text(canonical)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate_source_job_hash(job: dict) -> str:
    source = normalize_identity_text(job.get("source"))
    # URL aliases for source listing identity.
    raw_url = job.get("url") or job.get("job_url") or job.get("jobUrl")
    canonical_url = canonicalize_job_url(raw_url)

    if source and canonical_url:
        return _sha256(f"source_url|{source}|{canonical_url}")

    source_job_id = normalize_identity_text(
        job.get("source_job_id")
        or job.get("job_id")
        or job.get("listing_id")
        or job.get("id")
    )

    if source and source_job_id:
        return _sha256(f"source_id|{source}|{source_job_id}")

    title = normalize_identity_text(job.get("title"))
    company = normalize_identity_text(job.get("company"))
    location = normalize_identity_text(job.get("location"))

    return _sha256(f"source_fallback|{source}|{title}|{company}|{location}")


def generate_canonical_job_hash(job: dict) -> str:
    title = normalize_identity_text(job.get("title"))
    company = normalize_identity_text(job.get("company"))
    location = normalize_identity_text(
        job.get("target_location") or job.get("location")
    )

    return _sha256(f"canonical|{title}|{company}|{location}")
