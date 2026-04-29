import hashlib
import math


# =========================
# HARD REJECT (GLOBAL)
# =========================

HARD_REJECT_TITLE_KEYWORDS = [
    "senior",
    "sr ",
    "lead",
    "principal",
    "manager",
    "director",
    "head of",
    "vp ",
    "vice president",
    "engineer",
    "developer",
    "software",
    "backend",
    "frontend",
    "security engineer",
    "visual designer",
    "designer",
    "sales",
    "satış",
    "muhasebe",
    "kimyasal",
    "hukuk",
    "legal",
    "medya",
    "pazarlama uzmanı"
]

HARD_REJECT_DESCRIPTION_KEYWORDS = [
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
]


# =========================
# LOCATION KEYWORDS
# =========================

LOCATION_KEYWORDS = {
    "London": ["london", "greater london"],
    "Istanbul": ["istanbul", "i̇stanbul", "türkiye", "turkey"],
}


# =========================
# TARGET ROLES (EN)
# =========================

TARGET_ROLE_KEYWORDS = [
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
]


# =========================
# ISTANBUL ROLE KEYWORDS (TR)
# =========================

ISTANBUL_ROLE_KEYWORDS = [
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
    "growth analyst"
]


# =========================
# LEVEL KEYWORDS (LONDON)
# =========================

LEVEL_KEYWORDS = [
    "graduate",
    "junior",
    "entry level",
    "entry-level",
    "associate",
]


# =========================
# SKILLS
# =========================

SKILL_KEYWORDS = [
    "sql",
    "excel",
    "python",
    "power bi",
    "tableau",
    "dashboard",
    "reporting",
    "kpi",
    "analytics",
    "data analysis",
    "stakeholder",
    "process",
    "workflow",
    "automation",
]


# =========================
# SOFT RISKS
# =========================

SOFT_RISK_KEYWORDS = [
    "apprenticeship",
    "bootcamp",
    "training",
    "course",
    "commission",
    "door to door",
    "sales",
    "3+ years",
    "4+ years",
]


# =========================
# HELPERS
# =========================

def normalize_text(value) -> str:
    if value is None:
        return ""

    if isinstance(value, float) and math.isnan(value):
        return ""

    return str(value).lower().strip()


def combined_text(job: dict) -> str:
    return " ".join([
        normalize_text(job.get("title")),
        normalize_text(job.get("company")),
        normalize_text(job.get("location")),
        normalize_text(job.get("description")),
        normalize_text(job.get("search_query")),
    ])


def is_target_location(job: dict) -> bool:
    target = job.get("target_location")
    location = normalize_text(job.get("location"))

    if not target:
        return False

    allowed = LOCATION_KEYWORDS.get(target, [])
    return any(k in location for k in allowed)


# =========================
# HARD REJECT
# =========================

def hard_reject(job: dict) -> tuple[bool, str]:
    title = normalize_text(job.get("title"))
    description = normalize_text(job.get("description"))

    # ❗ DESCRIPTION ZORUNLU
    if not description:
        return True, "missing_description"

    for kw in HARD_REJECT_TITLE_KEYWORDS:
        if kw in title:
            return True, f"title_reject:{kw}"

    for kw in HARD_REJECT_DESCRIPTION_KEYWORDS:
        if kw in description:
            return True, f"description_reject:{kw}"

    if not is_target_location(job):
        return True, "location_mismatch"

    return False, ""


# =========================
# PRE SCORE
# =========================

def calculate_pre_score(job: dict):
    title = normalize_text(job.get("title"))
    text = combined_text(job)
    target = job.get("target_location")

    score = 0
    quality_flags = []
    risk_flags = []

    # -------------------------
    # LOCATION MATCH
    # -------------------------
    if is_target_location(job):
        score += 15
        quality_flags.append("location_match")

    # -------------------------
    # LONDON LOGIC
    # -------------------------
    if target == "London":

        # Junior zorunlu
        if any(k in title for k in LEVEL_KEYWORDS):
            score += 25
            quality_flags.append("junior_level")

        else:
            score -= 20
            risk_flags.append("not_junior")

        # Role match
        for kw in TARGET_ROLE_KEYWORDS:
            if kw in title:
                score += 20
                quality_flags.append(f"role:{kw}")
                break

    # -------------------------
    # ISTANBUL LOGIC
    # -------------------------
    if target == "Istanbul":

        # Junior şart değil
        if any(k in title for k in ISTANBUL_ROLE_KEYWORDS):
            score += 20
            quality_flags.append("istanbul_role_match")

        # İngilizce role da kabul
        for kw in TARGET_ROLE_KEYWORDS:
            if kw in title:
                score += 10
                quality_flags.append(f"role:{kw}")
                break

    # -------------------------
    # SKILLS
    # -------------------------
    for kw in SKILL_KEYWORDS:
        if kw in text:
            score += 3

    # -------------------------
    # DESCRIPTION BONUS
    # -------------------------
    if job.get("description"):
        score += 10

    # -------------------------
    # SOURCE BONUS
    # -------------------------
    source = normalize_text(job.get("source"))

    if "linkedin" in source:
        score += 5

    if "indeed" in source:
        score += 3

    # -------------------------
    # URL BONUS
    # -------------------------
    if job.get("url"):
        score += 5

    # -------------------------
    # SOFT RISK
    # -------------------------
    for kw in SOFT_RISK_KEYWORDS:
        if kw in text:
            score -= 8
            risk_flags.append(kw)

    score = max(0, min(100, score))

    return score, quality_flags, risk_flags


# =========================
# DUPLICATE
# =========================

def generate_duplicate_key(job: dict):
    raw = "|".join([
        normalize_text(job.get("title")),
        normalize_text(job.get("company")),
        normalize_text(job.get("target_location")),
    ])

    return hashlib.sha256(raw.encode()).hexdigest()


def remove_duplicates(jobs):
    seen = set()
    unique = []

    for job in jobs:
        key = generate_duplicate_key(job)

        if key in seen:
            continue

        seen.add(key)
        unique.append(job)

    return unique


# =========================
# MAIN FILTER
# =========================

def filter_jobs(jobs):
    accepted = []
    rejected = []

    for job in jobs:
        reject, reason = hard_reject(job)

        if reject:
            job["reject_reason"] = reason
            rejected.append(job)
            continue

        score, qf, rf = calculate_pre_score(job)

        job["pre_score"] = score
        job["quality_flags"] = qf
        job["risk_flags"] = rf

        if score < 40:
            job["reject_reason"] = "low_score"
            rejected.append(job)
            continue

        accepted.append(job)

    accepted = remove_duplicates(accepted)

    accepted = sorted(
        accepted,
        key=lambda x: x.get("pre_score", 0),
        reverse=True
    )

    return accepted, rejected


# =========================
# SPLIT
# =========================

def split_top_jobs_by_location(jobs, london_limit=20, istanbul_limit=20):
    london = []
    istanbul = []

    for job in jobs:
        if job.get("target_location") == "London":
            london.append(job)

        elif job.get("target_location") == "Istanbul":
            istanbul.append(job)

    return (
        london[:london_limit],
        istanbul[:istanbul_limit]
    )