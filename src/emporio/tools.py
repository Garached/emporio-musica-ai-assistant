"""Tools the LLM can call. Provider-agnostic: plain functions returning JSON-serializable dicts.

"Not found" situations never raise: they return {"error": "..."}.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from typing import Any, Callable

import pandas as pd

from emporio.business_rules import (
    PriceQuote,
    ReturnEligibility,
    active_promotion,
    availability_label,
    final_price,
    is_purchasable,
    return_eligibility,
)
from emporio.config import STORE_TIMEZONE, current_datetime
from emporio.data import StoreData, load_store_data
from emporio.policies import load_policy_sections

MAX_LIMIT = 20
MAX_ALTERNATIVES = 3
# Filler words ignored in search queries (every remaining word must match).
STOPWORDS = {"a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos",
             "e", "em", "com", "para", "pra", "por"}


# --- helpers ----------------------------------------------------------------------

def normalize(text: str) -> str:
    """Lowercase and strip accents, for accent-insensitive matching."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _clean(value: Any) -> Any:
    """Convert pandas/numpy scalars and NaN into plain JSON-friendly values."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.date().isoformat()
    if pd.api.types.is_scalar(value) and pd.isna(value):
        return None
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    return value


def category_names(store: StoreData | None = None) -> list[str]:
    """All category names, in catalog order."""
    store = store or load_store_data()
    return store.categories["name"].tolist()


def _quote(product: pd.Series, store: StoreData) -> tuple[PriceQuote, dict | None]:
    promo = active_promotion(int(product["product_id"]), store.promotions)
    return final_price(product, promo), promo


def _price_info(quote: PriceQuote, promo: dict | None) -> dict[str, Any]:
    """Compact price block. Promotions always show the original price (policy 6.2)."""
    info: dict[str, Any] = {"price": quote.promotional_price or quote.original_price}
    if quote.has_promotion:
        info.update(
            original_price=quote.original_price,
            discount_percent=quote.discount_percent,
            promotion_name=_clean(promo["description"]) if promo else None,
        )
    info["pix_price"] = quote.pix_price
    if quote.has_promotion:
        # Policy 6.2: PIX does not stack on promotions. Given as data so the model can't miss it.
        info["pix_extra_discount"] = False
    return info


def _effective_price(quote: PriceQuote) -> float:
    """Price the customer actually pays (promotional price if any)."""
    return quote.promotional_price if quote.has_promotion else quote.original_price


def _summary(product: pd.Series, store: StoreData) -> dict[str, Any]:
    """Compact product entry used in search results and alternatives."""
    quote, promo = _quote(product, store)
    return {
        "product_id": int(product["product_id"]),
        "name": product["name"],
        "category": product["category_name"],
        "availability": availability_label(product),
        **_price_info(quote, promo),
    }


def _haystack(product: pd.Series) -> str:
    specs = " ".join(f"{k} {v}" for k, v in product["specs"].items())
    parts = [product["name"], product["description"], product["category_name"], specs]
    return normalize(" ".join(str(p) for p in parts if isinstance(p, str)))


def _find_product(product_id: Any, store: StoreData) -> pd.Series | None:
    try:
        pid = int(product_id)
    except (TypeError, ValueError):
        return None
    rows = store.products[store.products["product_id"] == pid]
    return None if rows.empty else rows.iloc[0]


# --- product tools ------------------------------------------------------------------

def search_products(
    query: str | None = None,
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    only_available: bool = True,
    limit: int = 8,
) -> dict[str, Any]:
    """Search the catalog by text, category and price; results sorted by price.

    Every word of `query` must appear (accent/case-insensitive) in the name,
    description, category or specs. Price filters use the price actually paid
    (promotional price when a promotion is active).
    """
    store = load_store_data()
    if category is not None and category not in category_names(store):
        return {"error": f"Unknown category {category!r}. Valid: {category_names(store)}"}

    products = store.products
    if category is not None:
        products = products[products["category_name"] == category]
    tokens = [t for t in normalize(query or "").split() if t not in STOPWORDS]
    if tokens:
        products = products[products.apply(
            lambda p: all(t in _haystack(p) for t in tokens), axis=1)]

    matches: list[tuple[float, dict]] = []
    for _, product in products.iterrows():
        if only_available and not is_purchasable(product):
            continue
        quote, _promo = _quote(product, store)
        price = _effective_price(quote)
        if min_price is not None and price < float(min_price):
            continue
        if max_price is not None and price > float(max_price):
            continue
        matches.append((price, _summary(product, store)))

    matches.sort(key=lambda m: m[0])
    limit = max(1, min(int(limit), MAX_LIMIT))
    result: dict[str, Any] = {
        "total_found": len(matches),
        "results": [m[1] for m in matches[:limit]],
    }
    if category is not None and store.products[store.products["category_name"] == category].empty:
        result["note"] = f"The current catalog has no products in category {category!r}."
    return result


def _alternatives(product: pd.Series, store: StoreData) -> list[dict[str, Any]]:
    """Up to 3 purchasable products from the same category, closest in price."""
    target = _effective_price(_quote(product, store)[0])
    same_cat = store.products[
        (store.products["category_id"] == product["category_id"])
        & (store.products["product_id"] != product["product_id"])
    ]
    candidates = []
    for _, other in same_cat.iterrows():
        if is_purchasable(other):
            price = _effective_price(_quote(other, store)[0])
            candidates.append((abs(price - target), _summary(other, store)))
    candidates.sort(key=lambda c: c[0])
    return [c[1] for c in candidates[:MAX_ALTERNATIVES]]


def get_product_details(product_id: int) -> dict[str, Any]:
    """Full details of one product. Non-purchasable products include `alternatives`."""
    store = load_store_data()
    product = _find_product(product_id, store)
    if product is None:
        return {"error": f"Product {product_id} not found."}

    details = _summary(product, store)
    details["description"] = product["description"]
    details["specs"] = product["specs"]
    if is_purchasable(product):
        details["stock_quantity"] = int(product["stock_quantity"])
    else:
        details["alternatives"] = _alternatives(product, store)
    return details


def list_active_promotions() -> dict[str, Any]:
    """Active promotions on purchasable products, biggest discount first."""
    store = load_store_data()
    active_ids = store.promotions.loc[store.promotions["is_active"] == 1, "product_id"].unique()
    promotions = []
    for pid in active_ids:
        product = _find_product(pid, store)
        if product is None or not is_purchasable(product):
            continue
        quote, promo = _quote(product, store)
        promotions.append({
            "product_id": int(pid),
            "name": product["name"],
            "category": product["category_name"],
            "promotion_name": _clean(promo["description"]),
            "original_price": quote.original_price,
            "discount_percent": quote.discount_percent,
            "promotional_price": quote.promotional_price,
            "pix_price": quote.pix_price,  # same as the promotional price (policy 6.2)
            "pix_extra_discount": False,
        })
    promotions.sort(key=lambda p: p["discount_percent"], reverse=True)
    return {"total": len(promotions), "promotions": promotions}


# --- order tool ---------------------------------------------------------------------

# Status labels are our interpretation of the raw status codes (assumption).
ORDER_STATUS_LABELS = {
    "pending": "aguardando confirmação do pagamento",
    "confirmed": "pagamento confirmado, em separação",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}

ORDER_NOT_FOUND = (
    "Order not found or the phone digits do not match. Ask the customer to double-check "
    "the order number and the last 4 digits of the phone number registered on the order."
)


def _digits(value: Any) -> str:
    return "".join(c for c in str(value) if c.isdigit())


def _payment_label(method: str) -> str:
    if method.startswith("credit_"):
        return f"Cartão de crédito em {method.removeprefix('credit_')}"
    labels = {"pix": "PIX", "boleto": "Boleto bancário", "debit": "Cartão de débito"}
    return labels.get(method, method)


def _eligibility_dict(elig: ReturnEligibility) -> dict[str, Any]:
    out = asdict(elig)
    for key in ("regret_7_days", "defect_exchange_30_days"):
        if out[key] is not None:
            out[key]["deadline"] = out[key]["deadline"].isoformat()
    return out


def _normalize_last4(phone_last4: Any) -> str:
    """Keep digits only; an int loses leading zeros (0123 -> 123), so pad it back."""
    last4 = _digits(phone_last4)
    return last4.zfill(4) if isinstance(phone_last4, int) else last4


def get_order_status(order_id: int, phone_last4: str, *, today: date | None = None) -> dict[str, Any]:
    """Look up an order after checking the customer's identity.

    Identity check (LGPD): the last 4 digits of the customer's phone must match.
    Email is not used because two customers share the same email address.
    A missing order and wrong digits return the SAME error, so the tool never
    reveals whether an order exists.

    Status label assumptions: pending = aguardando confirmação do pagamento;
    confirmed = pagamento confirmado, em separação; shipped = enviado;
    delivered = entregue; cancelled = cancelado.

    `today` defaults to config.current_datetime() (honors EMPORIO_TODAY).
    """
    last4 = _normalize_last4(phone_last4)
    if len(last4) != 4:
        return {"error": "phone_last4 must be exactly the last 4 digits of the phone number."}

    store = load_store_data()
    try:
        oid = int(order_id)
    except (TypeError, ValueError):
        return {"error": ORDER_NOT_FOUND}
    orders = store.orders[store.orders["order_id"] == oid]
    if orders.empty:
        return {"error": ORDER_NOT_FOUND}
    order = orders.iloc[0]
    customer = store.customers[store.customers["customer_id"] == order["customer_id"]]
    if customer.empty or _digits(customer.iloc[0]["phone"])[-4:] != last4:
        return {"error": ORDER_NOT_FOUND}

    items = store.order_items[store.order_items["order_id"] == oid].merge(
        store.products[["product_id", "name"]], on="product_id", how="left")
    today = today or current_datetime().date()
    order_date = order["order_date"].date()
    delivery = None if pd.isna(order["estimated_delivery"]) else order["estimated_delivery"].date()

    return {
        "order_id": oid,
        "customer_first_name": customer.iloc[0]["name"].split()[0],
        "status": order["status"],
        "status_label": ORDER_STATUS_LABELS.get(order["status"], order["status"]),
        "order_date": order_date.isoformat(),
        "total_brl": float(order["total_brl"]),
        "payment_method": _payment_label(order["payment_method"]),
        "tracking_code": _clean(order["tracking_code"]),
        "estimated_delivery": delivery.isoformat() if delivery else None,
        "items": [
            {"name": _clean(i["name"]), "quantity": int(i["quantity"])} for _, i in items.iterrows()
        ],
        "notes": _clean(order["notes"]),
        "return_eligibility": _eligibility_dict(
            return_eligibility(order["status"], order_date, delivery, today)),
    }


# --- policy and store hours tools -------------------------------------------------

def policy_topics() -> list[str]:
    """All policy section titles, e.g. "4. Política de Trocas e Devoluções"."""
    return list(load_policy_sections())


def get_store_policy(topic: str) -> dict[str, Any]:
    """Return the text of one policy section.

    Accepts the exact title, or a unique accent/case-insensitive fragment of it.
    """
    sections = load_policy_sections()
    if topic in sections:
        return {"topic": topic, "text": sections[topic]}
    wanted = normalize(str(topic))
    matches = [title for title in sections if wanted and wanted in normalize(title)]
    if len(matches) == 1:
        return {"topic": matches[0], "text": sections[matches[0]]}
    return {"error": f"Unknown policy topic {topic!r}. Valid topics: {list(sections)}"}


# Weekday (Mon=0) -> (open, close). None = closed. From policy section 2.
STORE_HOURS: dict[int, tuple[time, time] | None] = {
    **{day: (time(9), time(18)) for day in range(5)},
    5: (time(9), time(13)),
    6: None,
}
WEEKDAYS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]


def _hours_label(hours: tuple[time, time] | None) -> str:
    return "fechado" if hours is None else f"{hours[0]:%H:%M}–{hours[1]:%H:%M}"


def _next_opening(now: datetime) -> datetime:
    """First opening time strictly after `now`."""
    for offset in range(8):
        day = now.date() + timedelta(days=offset)
        hours = STORE_HOURS[day.weekday()]
        if hours is None:
            continue
        opening = datetime.combine(day, hours[0], tzinfo=now.tzinfo)
        if opening > now:
            return opening
    raise RuntimeError("Store hours table has no opening day.")  # unreachable


def get_store_hours_status(*, now: datetime | None = None) -> dict[str, Any]:
    """Tell whether the store is open right now, and when it opens next if closed.

    Uses the store timezone America/Campo_Grande (UTC-4, not Brasília time).
    Hours: Mon–Fri 09:00–18:00, Sat 09:00–13:00, Sun closed.
    Limitation: holidays are not in the data, so they are NOT considered.
    `now` defaults to config.current_datetime() (honors EMPORIO_TODAY).
    """
    now = now or current_datetime()
    if now.tzinfo is None:
        now = now.replace(tzinfo=STORE_TIMEZONE)
    now = now.astimezone(STORE_TIMEZONE)
    hours = STORE_HOURS[now.weekday()]
    is_open = hours is not None and hours[0] <= now.time() < hours[1]

    result: dict[str, Any] = {
        "now": now.strftime("%Y-%m-%d %H:%M"),
        "weekday": WEEKDAYS_PT[now.weekday()],
        "timezone": "America/Campo_Grande (UTC-4)",
        "is_open": is_open,
        "today_hours": _hours_label(hours),
    }
    if is_open:
        result["closes_at"] = f"{hours[1]:%H:%M}"
    else:
        nxt = _next_opening(now)
        result["next_opening"] = {
            "date": nxt.date().isoformat(),
            "weekday": WEEKDAYS_PT[nxt.weekday()],
            "time": f"{nxt:%H:%M}",
        }
    result["note"] = "Holidays are not considered (the store is closed on holidays)."
    return result


# --- registry -----------------------------------------------------------------------

@dataclass(frozen=True)
class Tool:
    """A tool exposed to the LLM: name, description, JSON Schema parameters, callable."""

    name: str
    description: str
    parameters: dict[str, Any]
    function: Callable[..., dict[str, Any]]

    def spec(self) -> dict[str, Any]:
        """Provider-agnostic declaration (name, description, JSON Schema)."""
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


@lru_cache(maxsize=1)
def get_tools() -> dict[str, Tool]:
    """Build the tool registry. Enums (categories, policy topics) come from the data."""
    tools = [
        Tool(
            name="search_products",
            description=(
                "Search the store's musical instrument catalog. Use it whenever the customer "
                "asks what the store has, wants recommendations, or asks prices of several "
                "products. Do NOT use it when you already have the product_id (use "
                "get_product_details) or for accessories (strings, cables, picks, pedals, amps, "
                "cases): the store does not sell them. Results are sorted by price. `price` is "
                "what the customer pays (promotional price if a promotion is active); "
                "`pix_price` is the PIX price. When `original_price` and `discount_percent` are "
                "present, always show them with the promotional price. `total_found` is the "
                "number of matches before the `limit` cut. Never invent products or prices "
                "that are not in the results."
            ),
            parameters=_schema({
                "query": {
                    "type": "string",
                    "description": (
                        "1-3 distinctive keywords: brand, model or feature, e.g. 'takamine gd20', "
                        "'nylon', 'elétrico', 'yamaha'. Accents and case are ignored. Every word "
                        "must match, so do not put category or price words here (use the "
                        "filters). Omit to browse by category/price only."
                    ),
                },
                "category": {
                    "type": "string",
                    "enum": category_names(),
                    "description": "Restrict to one catalog category.",
                },
                "min_price": {"type": "number", "description": "Minimum price paid, in BRL."},
                "max_price": {"type": "number", "description": "Maximum price paid, in BRL."},
                "only_available": {
                    "type": "boolean",
                    "description": (
                        "Default true: only products that can be bought now. Set false only "
                        "when the customer asks about a specific product that may be out of "
                        "stock, discontinued or coming soon."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": f"Max results to return (1-{MAX_LIMIT}, default 8).",
                },
            }),
            function=search_products,
        ),
        Tool(
            name="get_product_details",
            description=(
                "Get full details of ONE product by product_id: description, specs, "
                "availability, stock and price. Use it after search_products when the customer "
                "wants to know more about a specific product, or to confirm availability and "
                "price before answering. If the product cannot be bought (out_of_stock, "
                "discontinued, coming_soon), the result has up to 3 available `alternatives` "
                "from the same category: suggest them."
            ),
            parameters=_schema(
                {"product_id": {"type": "integer", "description": "Product ID from search results."}},
                ["product_id"],
            ),
            function=get_product_details,
        ),
        Tool(
            name="list_active_promotions",
            description=(
                "List all promotions valid right now, on products that can be bought, with "
                "original price, discount % and promotional price. Use it when the customer "
                "asks about promotions, deals, discounts or offers. Any promotion not in this "
                "list is expired or unavailable: never promise it. PIX gives NO extra "
                "discount on promotional items (`pix_extra_discount: false`; `pix_price` equals "
                "the promotional price). Not needed to price a single product (search and "
                "details already apply promotions)."
            ),
            parameters=_schema({}),
            function=list_active_promotions,
        ),
        Tool(
            name="get_order_status",
            description=(
                "Look up an order: status, items, total, payment, tracking code, estimated "
                "delivery, notes (e.g. cancellation reason) and return/exchange eligibility. "
                "REQUIRES the order number AND the last 4 digits of the phone number "
                "registered on the order. If either is missing, ask the customer first; never "
                "guess or reuse digits. On error, do not say or imply whether the order exists: "
                "ask the customer to check both pieces of data. Greet the customer by "
                "`customer_first_name`. `return_eligibility` says whether the 7-day regret "
                "window and the 30-day defect exchange window are still open."
            ),
            parameters=_schema({
                "order_id": {"type": "integer", "description": "Order number given by the customer."},
                "phone_last4": {
                    "type": "string",
                    "description": "Last 4 digits of the customer's registered phone, e.g. '3456'.",
                },
            }, ["order_id", "phone_last4"]),
            function=get_order_status,
        ),
        Tool(
            name="get_store_policy",
            description=(
                "Get the official text of one section of the store's policy manual. Use it for "
                "questions about payment methods and installments, returns and exchanges, "
                "shipping and delivery, promotion rules, warranty, privacy (LGPD) or general "
                "store information. Base the answer only on the returned text. Do NOT use it "
                "to know if the store is open right now (use get_store_hours_status)."
            ),
            parameters=_schema(
                {"topic": {"type": "string", "enum": policy_topics(),
                           "description": "Policy section to read."}},
                ["topic"],
            ),
            function=get_store_policy,
        ),
        Tool(
            name="get_store_hours_status",
            description=(
                "Check whether the store (and human WhatsApp service) is open right now, in "
                "Campo Grande time (UTC-4), today's hours and, if closed, the next opening day "
                "and time. Also returns the current date and time. Use it when the customer "
                "asks if the store is open, until when, or when someone will answer. Holidays "
                "are not considered: mention this if relevant."
            ),
            parameters=_schema({}),
            function=get_store_hours_status,
        ),
    ]
    return {tool.name: tool for tool in tools}


def tool_specs() -> list[dict[str, Any]]:
    """Declarations of all tools, ready to adapt to any LLM provider."""
    return [tool.spec() for tool in get_tools().values()]


def run_tool(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate and run a tool call. Never raises: problems come back as {"error": ...}."""
    tool = get_tools().get(name)
    if tool is None:
        return {"error": f"Unknown tool {name!r}. Available: {list(get_tools())}"}
    args = dict(args or {})
    allowed = set(tool.parameters["properties"])
    unexpected = sorted(set(args) - allowed)
    if unexpected:
        return {"error": f"Unexpected arguments for {name}: {unexpected}. Allowed: {sorted(allowed)}"}
    missing = [p for p in tool.parameters["required"] if args.get(p) in (None, "")]
    if missing:
        return {"error": f"Missing required arguments for {name}: {missing}"}
    try:
        return tool.function(**args)
    except Exception as exc:  # a bad tool call must never crash the conversation
        return {"error": f"Tool {name} failed: {type(exc).__name__}: {exc}"}
