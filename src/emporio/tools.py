"""Tools the LLM can call. Provider-agnostic: plain functions returning JSON-serializable dicts.

"Not found" situations never raise: they return {"error": "..."}.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import asdict
from datetime import date
from typing import Any

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
from emporio.config import current_datetime
from emporio.data import StoreData, load_store_data

MAX_LIMIT = 20
MAX_ALTERNATIVES = 3


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
    if query and query.strip():
        tokens = normalize(query).split()
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
