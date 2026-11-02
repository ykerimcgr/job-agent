from __future__ import annotations

import re


# Text arrives normalized (casefolded, accents stripped), so "üç" is "uc" and "dört" is "dort".
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10,
    "bir": 1, "iki": 2, "uc": 3, "dort": 4, "bes": 5, "alti": 6, "altı": 6, "yedi": 7,
    "sekiz": 8, "dokuz": 9,
}
YEARS_PATTERN = re.compile(
    r"(?<![\w.])(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")"
    r"\s*\+?\s*(?:(?:-|to|–)\s*\d{1,2}\s*\+?\s*)?"
    r"(?:years?|yrs?|y[iı]l(?:l[iı]k)?)\b"
    r"[^.;\n]{0,40}?(?:experience|deneyim|tecrube)"
)


def required_years(text: str) -> int | None:
    """Smallest 'N years ... experience' figure in the text (English or Turkish), if any."""
    values = []
    for match in YEARS_PATTERN.finditer(text or ""):
        token = match.group(1)
        value = int(token) if token.isdigit() else NUMBER_WORDS[token]
        if value <= 15:
            values.append(value)
    return min(values) if values else None
