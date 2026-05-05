from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List
import re


@dataclass(frozen=True)
class FilterConfig:
    location_keywords: Dict[str, List[str]] = field(default_factory=lambda: {
        "London": [
            "london",
            "greater london",
            "city of london",
            "london area",
            "united kingdom",
            "uk",
        ],
        "Istanbul": [
            "istanbul",
            "i̇stanbul",
            "turkiye",
            "türkiye",
            "turkey",
        ],
    })

    hard_reject_title_keywords: List[str] = field(default_factory=lambda: [
        "senior",
        "sr",
        "lead",
        "principal",
        "manager",
        "director",
        "head of",
        "vp",
        "vice president",
        "software engineer",
        "backend engineer",
        "frontend engineer",
        "devops engineer",
        "full stack",
        "full-stack",
        "software developer",
        "backend developer",
        "frontend developer",
        "security engineer",
        "visual designer",
        "designer",
        "muhasebe",
        "kimyasal",
        "hukuk",
        "legal",
        "medya",
        "pazarlama uzmanı",
    ])

    hard_reject_description_keywords: List[str] = field(default_factory=lambda: [
        "5+ years",
        "6+ years",
        "7+ years",
        "8+ years",
        "10+ years",
        "minimum 5 years",
        "at least 5 years",
        "extensive experience",
        "lead a team",
        "manage a team",
    ])

    hard_reject_apprentice_keywords: List[str] = field(default_factory=lambda: [
        r"\bapprentice\b",
        r"\bapprenticeship\b",
        r"\bdegree apprenticeship\b",
        r"\bhigher apprenticeship\b",
        r"\badvanced apprenticeship\b",
        r"\blevel\s*[2-7]\b.*\bapprentice",
        r"\bapprentice\b.*\blevel\s*[2-7]\b",
        r"\blevel\s*[2-7]\s+programme\b",
        r"\blevel\s*[2-7]\s+program\b",
        r"\bdata technician\s+level\s*[2-7]\b",
        r"\bbusiness administration\s+level\s*[2-7]\b",
    ])



    target_role_keywords: List[str] = field(default_factory=lambda: [
        "operations analyst",
        "business operations analyst",
        "performance analyst",
        "mi analyst",
        "reporting analyst",
        "data operations analyst",
        "business analyst",
        "project coordinator",
        "pmo analyst",
        "commercial analyst",
        "growth analyst",
        "product analyst",
    ])

    istanbul_role_keywords: List[str] = field(default_factory=lambda: [
        "iş analisti",
        "veri analisti",
        "raporlama analisti",
        "raporlama uzmanı",
        "operasyon analisti",
        "iş geliştirme uzmanı",
        "crm analisti",
        "ürün analisti",
        "business analyst",
        "data analyst",
        "operations analyst",
        "product analyst",
        "growth analyst",
    ])

    level_keywords: List[str] = field(default_factory=lambda: [
        "graduate",
        "junior",
        "entry level",
        "entry-level",
        "associate",
        "early career",
        "0-2 years",
        "0 to 2 years",
    ])

    skill_keywords: List[str] = field(default_factory=lambda: [
        "sql",
        "excel",
        "python",
        "dashboard",
        "reporting",
        "kpi",
        "analytics",
        "data analysis",
        "data science",
        "stakeholder",
        "process",
        "workflow",
        "automation",
    ])

    soft_risk_keywords: List[str] = field(default_factory=lambda: [
        "bootcamp",
        "training",
        "course",
        "commission",
        "door to door",
        "3+ years",
        "4+ years",
    ])

    source_bonus: Dict[str, int] = field(default_factory=lambda: {
        "linkedin": 3,
        "indeed": 3,
    })

    min_score: int = 40
    max_score: int = 100

    reject_if_missing_description: bool = True

    location_score: int = 15
    london_level_bonus: int = 25
    london_missing_level_penalty: int = 10
    london_role_bonus: int = 25
    istanbul_role_bonus: int = 25
    istanbul_english_role_bonus: int = 10
    skill_bonus: int = 3
    description_bonus: int = 8
    missing_description_penalty: int = 10
    url_bonus: int = 5
    soft_risk_penalty: int = 8