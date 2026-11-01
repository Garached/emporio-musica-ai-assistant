"""Application settings loaded from environment variables / a `.env` file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

DEFAULT_MODEL = "gemini-3.5-flash-lite"

# Low thinking: faster and cheaper, enough for customer service.
DEFAULT_THINKING_LEVEL = "low"
THINKING_LEVELS = ("minimal", "low", "medium", "high")

# Campo Grande (MS) is UTC-4 with no daylight saving time. NOT Brasília time.
STORE_TIMEZONE = ZoneInfo("America/Campo_Grande")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings for the agent."""

    gemini_api_key: str
    gemini_model: str = DEFAULT_MODEL
    gemini_thinking_level: str = DEFAULT_THINKING_LEVEL


def load_settings() -> Settings:
    """Load settings from the environment, reading a `.env` file if present.

    Raises:
        ConfigError: If GEMINI_API_KEY is not set or GEMINI_THINKING_LEVEL is invalid.
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
    level = os.getenv("GEMINI_THINKING_LEVEL", "").strip().lower() or DEFAULT_THINKING_LEVEL
    if level not in THINKING_LEVELS:
        raise ConfigError(
            f"Invalid GEMINI_THINKING_LEVEL={level!r}. Use one of: {', '.join(THINKING_LEVELS)}."
        )
    return Settings(gemini_api_key=api_key, gemini_model=model, gemini_thinking_level=level)


@lru_cache(maxsize=1)
def _load_env_once() -> None:
    load_dotenv()


def parse_today(raw: str, real_now: datetime) -> datetime:
    """Parse an EMPORIO_TODAY value into a store-local datetime.

    - Date only ("2026-03-20"): that date with the real current time of day.
    - Naive datetime ("2026-03-20T14:30"): interpreted as store-local time.
    - Aware datetime: converted to the store timezone.

    Raises:
        ConfigError: If the value is not a valid ISO date or datetime.
    """
    raw = raw.strip()
    try:
        if len(raw) == 10:
            day = date.fromisoformat(raw)
            return datetime.combine(day, real_now.timetz())
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ConfigError(
            f"Invalid EMPORIO_TODAY={raw!r}. Use an ISO date (2026-03-20) "
            "or datetime (2026-03-20T14:30)."
        ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=STORE_TIMEZONE)
    return parsed.astimezone(STORE_TIMEZONE)


def current_datetime() -> datetime:
    """Return "now" in the store timezone, honoring the optional EMPORIO_TODAY override.

    The data is a snapshot from early 2026; overriding "today" makes date-based
    rules (e.g. return windows) demoable. Does not require GEMINI_API_KEY.
    """
    _load_env_once()
    real_now = datetime.now(STORE_TIMEZONE)
    raw = os.getenv("EMPORIO_TODAY", "").strip()
    return parse_today(raw, real_now) if raw else real_now
