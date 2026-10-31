"""Application settings loaded from environment variables / a `.env` file."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_MODEL = "gemini-2.5-flash"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings for the agent."""

    gemini_api_key: str
    gemini_model: str = DEFAULT_MODEL


def load_settings() -> Settings:
    """Load settings from the environment, reading a `.env` file if present.

    Raises:
        ConfigError: If GEMINI_API_KEY is not set.
    """
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "GEMINI_API_KEY is not set.\n"
            "Create a `.env` file in the project root (copy `.env.example`) "
            "and add your key:\n"
            "    GEMINI_API_KEY=your-key-here\n"
            "Get a free key at https://aistudio.google.com/apikey"
        )

    model = os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
    return Settings(gemini_api_key=api_key, gemini_model=model)
