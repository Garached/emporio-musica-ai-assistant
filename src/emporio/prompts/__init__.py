"""Versioned prompt files and the functions that render them."""

from __future__ import annotations

from datetime import datetime
from importlib.resources import files

from emporio.config import STORE_TIMEZONE, current_datetime
from emporio.tools import WEEKDAYS_PT, get_store_hours_status

SYSTEM_PROMPT_FILE = "system_prompt.md"


def store_status_text(now: datetime) -> str:
    """Describe in Portuguese whether the store is open now, reusing the hours tool."""
    status = get_store_hours_status(now=now)
    if status["is_open"]:
        return f"aberta agora (hoje até as {status['closes_at']})"
    nxt = status["next_opening"]
    day = datetime.fromisoformat(nxt["date"]).strftime("%d/%m")
    return f"fechada agora; a equipe volta {nxt['weekday']}, {day}, às {nxt['time']}"


def load_prompt_template(name: str = SYSTEM_PROMPT_FILE) -> str:
    """Read a raw prompt file shipped inside this package."""
    return files(__package__).joinpath(name).read_text(encoding="utf-8")


def build_system_prompt(now: datetime | None = None) -> str:
    """Render the system prompt with the current date, weekday, time and store status.

    Placeholders use {{name}} with plain replacement: str.format would break on
    literal braces and string.Template on "R$".
    `now` defaults to config.current_datetime() (honors EMPORIO_TODAY).
    """
    now = (now or current_datetime()).astimezone(STORE_TIMEZONE)
    values = {
        "{{date}}": now.strftime("%d/%m/%Y"),
        "{{weekday}}": WEEKDAYS_PT[now.weekday()],
        "{{time}}": now.strftime("%H:%M"),
        "{{store_status}}": store_status_text(now),
    }
    prompt = load_prompt_template()
    for placeholder, value in values.items():
        prompt = prompt.replace(placeholder, value)
    return prompt
