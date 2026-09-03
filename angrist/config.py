from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "gpt-oss"
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


@dataclass
class Config:
    model: str
    base_url: str
    api_key: str


def load_config(
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    dotenv_path: str | Path | None = None,
) -> Config:
    """Load configuration with precedence: CLI flags > Env vars > .env file > Defaults."""
    if dotenv_path is not None:
        if Path(dotenv_path).exists():
            load_dotenv(dotenv_path=dotenv_path, override=False)
    else:
        load_dotenv(override=False)

    resolved_model = model or os.environ.get("ANGRIST_LLM_MODEL") or DEFAULT_MODEL
    resolved_base_url = (
        base_url or os.environ.get("ANGRIST_LLM_BASE_URL") or DEFAULT_BASE_URL
    ).rstrip("/")
    resolved_api_key = (
        api_key if api_key is not None else os.environ.get("ANGRIST_LLM_API_KEY", "")
    )

    return Config(
        model=resolved_model,
        base_url=resolved_base_url,
        api_key=resolved_api_key,
    )
