"""Standard lines appended to replies in code, when the model leaves them out.

- Closed-store notice (policy 7.1): on the first reply of a conversation, if the store
  is closed and the reply doesn't say when it reopens, append the reopening day/time
  (from tools.get_store_hours_status).
- Official contacts in payment replies: if the customer's message is about paying and
  the reply doesn't give the official phone and e-mail, append them (anti-fraud).
"""

from __future__ import annotations

import re
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


# --- official contacts in payment replies -----------------------------------------------

# Keyword heuristic (whole word, accent-insensitive): the customer's message is about
# paying. It can miss other wordings or fire on an unrelated "link"; the cost of a false
# positive is one extra line with the official contacts.
PAYMENT_KEYWORDS = (
    "pix", "pagar", "pago", "paguei", "pagamento", "pagamentos", "boleto", "link", "links",
    "deposito", "depositar", "transferencia", "transferir", "conta bancaria", "comprovante",
    "comprovantes",
)
OFFICIAL_CONTACTS_LINE = (
    "Para pagamentos, use só os canais oficiais da loja: WhatsApp/telefone (67) 3341-4444 "
    "ou e-mail contato@emporiodamusica.com.br."
)
_OFFICIAL_PHONE = re.compile(r"3341[-\s.]?4444")
_OFFICIAL_EMAIL = "contato@emporiodamusica.com.br"


def is_payment_message(text: str) -> bool:
    """True if the customer's message mentions paying (see PAYMENT_KEYWORDS)."""
    normalized = normalize(text)
    return any(re.search(rf"(?<!\w){re.escape(k)}(?!\w)", normalized) for k in PAYMENT_KEYWORDS)


def has_official_contacts(reply: str) -> bool:
    """True if the reply already gives both the official phone and the official e-mail."""
    return bool(_OFFICIAL_PHONE.search(reply)) and _OFFICIAL_EMAIL in reply.casefold()
