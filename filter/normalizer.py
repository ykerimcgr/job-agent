from __future__ import annotations

import html
import math
import re
import unicodedata
from typing import Any

from .types import Job, NormalizedJob


class TextNormalizer:
    HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
    WHITESPACE_PATTERN = re.compile(r"\s+")

    @classmethod
    def normalize(cls, value: Any) -> str:
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
        text = cls.HTML_TAG_PATTERN.sub(" ", text)
        text = unicodedata.normalize("NFKC", text)
        text = text.casefold()

        text = "".join(
            char for char in unicodedata.normalize("NFD", text)
            if unicodedata.category(char) != "Mn"
        )

        text = cls.WHITESPACE_PATTERN.sub(" ", text).strip()
        return text

    @classmethod
    def join_fields(cls, *values: Any) -> str:
        parts = [cls.normalize(value) for value in values]
        return " ".join(part for part in parts if part)


def normalize_job(job: Job) -> NormalizedJob:
    title = TextNormalizer.normalize(job.get("title"))
    company = TextNormalizer.normalize(job.get("company"))
    location = TextNormalizer.normalize(job.get("location"))
    description = TextNormalizer.normalize(job.get("description"))
    source = TextNormalizer.normalize(job.get("source"))
    url = TextNormalizer.normalize(job.get("url"))
    target_location = str(job.get("target_location") or "").strip()
    search_query = TextNormalizer.normalize(job.get("search_query"))

    full_text = TextNormalizer.join_fields(
        title,
        company,
        location,
        description,
        search_query,
    )

    return NormalizedJob(
        title=title,
        company=company,
        location=location,
        description=description,
        source=source,
        url=url,
        target_location=target_location,
        search_query=search_query,
        full_text=full_text,
    )