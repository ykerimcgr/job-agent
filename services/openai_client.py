from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


def get_openai_api_key() -> str:
    return (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("OPEN_AI_SECRET_KEY")
        or ""
    ).strip()


def get_openai_client() -> OpenAI:
    api_key = get_openai_api_key()
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is missing. The legacy OPEN_AI_SECRET_KEY name "
            "is also supported."
        )
    return OpenAI(api_key=api_key)
