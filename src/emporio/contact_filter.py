"""Output contact filter: no invented contact or payment details reach the customer.

A fake PIX key, bank account or payment link could send a customer's money to a
fraudster, and the data has none of these. So, like prices (grounding.py), contact
and payment details in Clave's reply are checked in code: only the official
contacts and values that appeared in tool results in this conversation are allowed.
Values the customer wrote (e.g. a phishing URL) are NOT allowed to be repeated.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

OFFICIAL_EMAIL = "contato@emporiodamusica.com.br"
# (67) 3341-4444 in any common format: with/without area code or +55.
OFFICIAL_PHONE_DIGITS = frozenset({"33414444", "6733414444", "556733414444"})

_TLDS = r"(?:com|net|org|xyz|io|app|info|biz|site|online|store|shop|link|me|ly|co|br)"
_TRAILING = ".,;:!?)»\"'"

# (kind, pattern). Order matters: matched spans are blanked so they aren't matched twice.
# "chave pix <value>" comes first: the data has no PIX key, so ANY value presented as one
# (even an official contact or the real CNPJ) is flagged.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("pix_key", re.compile(r"chave\s+pix\s*(?:da\s+loja\s*)?(?:[ée]|:|=)\s*\S+", re.I)),
    ("url", re.compile(r"https?://\S+|\bwww\.\S+", re.I)),
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.I)),
    ("domain", re.compile(rf"(?<![@\w.-])(?:[a-z0-9-]+\.)+{_TLDS}(?:\.br)?\b(?:/\S*)?", re.I)),
    ("pix_key_uuid", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)),
    ("cnpj", re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")),
    ("cpf", re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")),
    ("phone", re.compile(r"(?<![\d/])(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?9?\d{4}[-\s.]?\d{4}(?![\d/])")),
    ("bank_agency", re.compile(r"ag[eê]ncia\s*(?:n[ºo°.]*\s*)?:?\s*\d{3,5}(?:-\d)?", re.I)),
    ("bank_account", re.compile(
        r"\bconta(?:\s+corrente|\s+poupan[cç]a)?\s*(?:n[ºo°.]*\s*)?:?\s*\d[\d.]{3,}(?:-[\dxX])?", re.I)),
]

_NUMERIC_KINDS = {"cnpj", "cpf", "phone"}


def canonical(kind: str, value: str) -> str:
    """Comparable form: digits only for numbers, lowercase without trailing punctuation otherwise."""
    if kind in _NUMERIC_KINDS:
        return re.sub(r"\D", "", value)
    return value.strip().rstrip(_TRAILING).lower()


def detect_contacts(text: str) -> list[tuple[str, str]]:
    """Every contact/payment-like value in a text, as (kind, matched text)."""
    found = []
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            found.append((kind, match.group(0).strip().rstrip(_TRAILING)))
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    return found


def official_values() -> set[str]:
    """Canonical forms of the official contacts."""
    return {OFFICIAL_EMAIL} | set(OFFICIAL_PHONE_DIGITS)


def allowed_from_text(text: str) -> set[str]:
    """Canonical contact values found in a trusted text (e.g. a tool result)."""
    return {canonical(kind, value) for kind, value in detect_contacts(text)}


def unofficial_contacts(reply: str, allowed: Iterable[str]) -> list[str]:
    """Contact/payment details in the reply that are neither official nor from tool results."""
    known = set(allowed)
    return [value for kind, value in detect_contacts(reply) if canonical(kind, value) not in known]


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings(v)]
    return []


def allowed_from_result(result: Any) -> set[str]:
    """Canonical contact values present in a tool result (e.g. the CNPJ in the policy text)."""
    return {v for text in _strings(result) for v in allowed_from_text(text)}
