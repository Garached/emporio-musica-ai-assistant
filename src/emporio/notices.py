"""Closed-store notice (policy 7.1): outside business hours, say when the team is back.

Enforced in code on the first reply of a conversation: if the store is closed and
the reply doesn't already say when it reopens, one standard line is appended,
built from the store-hours logic (tools.get_store_hours_status).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from emporio.tools import normalize


def _day_variants(status: dict[str, Any]) -> list[str]:
    """Ways a reply can name the reopening day: weekday, "amanhã", or dd/mm."""
    nxt = status["next_opening"]
    opening = date.fromisoformat(nxt["date"])
    variants = [normalize(nxt["weekday"]).split("-")[0], opening.strftime("%d/%m")]
    today = datetime.strptime(status["now"], "%Y-%m-%d %H:%M").date()
    if opening == today + timedelta(days=1):
        variants.append("amanha")
    if opening == today:
        variants.append("hoje")
    return variants


def _time_variants(hhmm: str) -> list[str]:
    """ "09:00" -> ["09:00", "9:00", "09h", "9h"] """
    hours, minutes = hhmm.split(":")
    h = str(int(hours))
    variants = [hhmm, f"{h}:{minutes}"]
    if minutes == "00":
        variants += [f"{hours}h", f"{h}h"]
    return variants


def mentions_reopening(text: str, status: dict[str, Any]) -> bool:
    """True if the reply names both the reopening day and the time."""
    normalized = normalize(text)
    day = any(v in normalized for v in _day_variants(status))
    time = any(v in normalized for v in _time_variants(status["next_opening"]["time"]))
    return day and time


def closed_notice(status: dict[str, Any]) -> str | None:
    """The standard line, or None when the store is open."""
    if status["is_open"]:
        return None
    nxt = status["next_opening"]
    day = date.fromisoformat(nxt["date"]).strftime("%d/%m")
    return (f"Nossa loja está fechada agora e a equipe volta {nxt['weekday']}, {day}, "
            f"às {nxt['time']}. Enquanto isso, sigo te ajudando por aqui.")
