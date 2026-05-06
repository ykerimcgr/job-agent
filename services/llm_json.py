import json
import re


FENCED_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)


def parse_llm_json(content: str) -> dict:
    if not content or not str(content).strip():
        raise ValueError("Failed to parse LLM JSON: empty content")

    text = str(content).strip()
    decoder = json.JSONDecoder()

    candidates = []

    # Prefer fenced payloads when present.
    fenced_matches = FENCED_BLOCK_PATTERN.findall(text)
    candidates.extend(fenced_matches)
    # Also try the full text in case JSON is not fenced.
    candidates.append(text)

    for candidate in candidates:
        s = candidate.strip()
        if not s:
            continue

        # Try exact parse first.
        try:
            value = json.loads(s)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass

        # Then scan for the first decodable JSON object.
        for idx, ch in enumerate(s):
            if ch != "{":
                continue
            try:
                value, _ = decoder.raw_decode(s[idx:])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue

    raise ValueError("Failed to parse LLM JSON: no valid JSON object found")

