from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


Job = Dict[str, Any]


@dataclass(frozen=True)
class NormalizedJob:
    title: str
    company: str
    location: str
    description: str
    source: str
    url: str
    target_location: str
    search_query: str
    full_text: str


@dataclass(frozen=True)
class ScoreResult:
    score: int
    quality_flags: List[str]
    risk_flags: List[str]


@dataclass(frozen=True)
class RejectResult:
    rejected: bool
    reason: str = ""