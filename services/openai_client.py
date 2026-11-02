from __future__ import annotations

import os
from typing import TypeVar

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel


load_dotenv()

Schema = TypeVar("Schema", bound=BaseModel)


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


def structured_completion(
    prompt: str,
    schema: type[Schema],
    *,
    model: str,
    temperature: float = 0,
) -> Schema:
    """One chat call whose reply is validated against `schema` (OpenAI Structured Outputs)."""
    response = get_openai_client().chat.completions.parse(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format=schema,
        temperature=temperature,
    )
    message = response.choices[0].message
    if message.parsed is None:
        raise ValueError(message.refusal or "Model returned no structured output")
    return message.parsed
