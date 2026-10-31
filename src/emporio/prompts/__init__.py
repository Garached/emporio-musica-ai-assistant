"""Versioned prompt files and the functions that render them."""

from __future__ import annotations

from datetime import datetime
from importlib.resources import files

from emporio.config import STORE_TIMEZONE, current_datetime
from emporio.tools import WEEKDAYS_PT

SYSTEM_PROMPT_FILE = "system_prompt.md"


def load_prompt_template(name: str = SYSTEM_PROMPT_FILE) -> str:
    """Read a raw prompt file shipped inside this package."""
    return files(__package__).joinpath(name).read_text(encoding="utf-8")


def build_system_prompt(now: datetime | None = None) -> str:
    """Render the system prompt with the current date, weekday and time.

    Placeholders use {{name}} with plain replacement: str.format would break on
    literal braces and string.Template on "R$".
    `now` defaults to config.current_datetime() (honors EMPORIO_TODAY).
    """
    now = (now or current_datetime()).astimezone(STORE_TIMEZONE)
    values = {
        "{{date}}": now.strftime("%d/%m/%Y"),
        "{{weekday}}": WEEKDAYS_PT[now.weekday()],
        "{{time}}": now.strftime("%H:%M"),
    }
    prompt = load_prompt_template()
    for placeholder, value in values.items():
        prompt = prompt.replace(placeholder, value)
    return prompt
