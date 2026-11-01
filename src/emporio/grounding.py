"""Output grounding: every R$ value in a reply must come from tool results.

The model communicates; code computes. Any money value in Clave's reply that no
tool returned in this conversation (and that the customer didn't say) is treated
as invented or self-computed and blocked by the agent.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

TOLERANCE = 0.01  # R$ 0,01

_BRL = re.compile(r"R\$\s?(\d[\d.]*(?:,\d{1,2})?)")
_PLAIN_NUMBER = re.compile(r"\d[\d.]*(?:,\d{1,2})?")


def parse_brl(raw: str) -> float:
    """Parse a BRL amount: "1.967,18", "2.199", "1000", "439.20" -> float."""
    if "," in raw:
        return float(raw.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d+\.\d{2}", raw):
        return float(raw)
    return float(raw.replace(".", ""))


def prices_in(text: str) -> list[float]:
    """All R$ amounts mentioned in a text (Brazilian format)."""
    return [parse_brl(m) for m in _BRL.findall(text)]


def numbers_in_text(text: str) -> list[float]:
    """Every number in a text, read as BRL-style (used for what the customer wrote)."""
    values = []
    for raw in _PLAIN_NUMBER.findall(text):
        try:
            values.append(parse_brl(raw.rstrip(".")))
        except ValueError:
            continue
    return values


def numbers_in_result(value: Any) -> list[float]:
    """All numbers in a tool result: numeric fields plus R$ amounts inside strings
    (e.g. policy text, price-gap notes). Booleans are ignored."""
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, str):
        return prices_in(value)
    if isinstance(value, dict):
        return [n for v in value.values() for n in numbers_in_result(v)]
    if isinstance(value, (list, tuple)):
        return [n for v in value for n in numbers_in_result(v)]
    return []


def ungrounded_values(reply: str, grounded: Iterable[float], tolerance: float = TOLERANCE) -> list[float]:
    """R$ values in the reply that don't match any grounded value (within tolerance)."""
    known = list(grounded)
    return [p for p in prices_in(reply) if not any(abs(p - g) <= tolerance for g in known)]


def format_brl(value: float) -> str:
    """1967.18 -> "R$ 1.967,18"."""
    return "R$ " + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
