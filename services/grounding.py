"""Reject reworded CV / cover-letter text that claims something the master CV does not say."""
from __future__ import annotations

import re


WORD = re.compile(r"[^\W\d_][\w+#&]*(?:[./-][\w+#&]+)*")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
SENTENCE_START = re.compile(r"(?:^|[.!?:;]\s+)([^\W\d_][\w+#&]*(?:[./-][\w+#&]+)*)")
# Words that appear in requirement text but say nothing about a specific skill.
GENERIC = {
    "experience", "knowledge", "understanding", "ability", "abilities", "strong",
    "skills", "skill", "working", "proven", "excellent", "good", "degree", "familiarity",
    "proficiency", "proficient", "years", "year", "related", "relevant", "field",
    "similar", "role", "with", "including", "preferred", "required", "desirable",
    "essential", "minimum", "least", "plus", "using", "within", "environment",
    "background", "enthusiasm", "passion", "interest", "motivated", "team", "opportunity",
}


# Connecting words a skill line may use even when the CV happens not to contain them.
FUNCTION_WORDS = {
    "with", "from", "into", "using", "across", "through", "including", "such", "that", "this",
    "their", "over", "within", "between", "based", "also", "both", "and", "for", "the",
}


def _stem(word: str) -> str:
    # shortcut: 6-letter prefix stands in for a real stemmer ("automating" ~ "automation").
    word = word.casefold().strip("./-+")  # "90GB+" and "GB" are the same word
    return word[:6]


def vocabulary(text: str) -> set[str]:
    return {_stem(word) for word in WORD.findall(text)}


def risky_vocabulary(unmet_requirements: list[str], known: set[str]) -> set[str]:
    """Words from requirements the candidate does not fully meet, minus words the CV already uses."""
    return {
        _stem(word)
        for text in unmet_requirements
        for word in WORD.findall(text)
        if len(word) >= 4 and word.casefold() not in GENERIC and _stem(word) not in known
    }


def unsupported_terms(
    text: str,
    *,
    source: str,
    known: set[str],
    risky: set[str],
    strict: bool = False,
) -> list[str]:
    """Numbers not in `source`, capitalised names the CV never uses, and unmet-requirement words.

    strict (skill lists): every word must already be a CV word, whatever its capitalisation.
    """
    problems = [number for number in NUMBER.findall(text) if number not in NUMBER.findall(source)]
    sentence_starts = {match.group(1) for match in SENTENCE_START.finditer(text)}
    for word in WORD.findall(text):
        stem = _stem(word)
        if stem in risky:  # risky words are never CV words, so check them before `known`
            problems.append(word)
        elif stem in known or word == "I":
            continue
        elif strict:
            if len(word) >= 4 and word.casefold() not in FUNCTION_WORDS:
                problems.append(word)
        elif word[0].isupper() and word not in sentence_starts:
            problems.append(word)
    return problems
