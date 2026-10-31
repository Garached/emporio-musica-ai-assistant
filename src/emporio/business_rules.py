"""Pure business rules: availability, promotions and prices. No I/O.

All money math lives here so the LLM never has to calculate prices.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping

import pandas as pd

PIX_DISCOUNT_PERCENT = 5.0
REGRET_WINDOW_DAYS = 7  # policy 4.1, counted from delivery
DEFECT_EXCHANGE_DAYS = 30  # policy 4.2, counted from the purchase date

AVAILABLE = "available"
OUT_OF_STOCK = "out_of_stock"
DISCONTINUED = "discontinued"
COMING_SOON = "coming_soon"

# A product can be a dict or a pandas row (Series); both support product["key"].
Product = Mapping[str, Any] | pd.Series


@dataclass(frozen=True)
class PriceQuote:
    """Price breakdown for one product.

    `promotional_price` is None when there is no active promotion.
    `pix_price` is what the customer pays via PIX.
    """

    original_price: float
    discount_percent: float
    promotional_price: float | None
    pix_price: float

    @property
    def has_promotion(self) -> bool:
        """True if an active promotion was applied."""
        return self.promotional_price is not None


def _to_cents(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def round_money(value: float) -> float:
    """Round a BRL amount to 2 decimals, half-up."""
    return _to_cents(Decimal(str(value)))


def _apply_discount(price: float, percent: float) -> float:
    """Apply a percentage discount using Decimal math to avoid float rounding errors."""
    factor = 1 - Decimal(str(percent)) / 100
    return _to_cents(Decimal(str(price)) * factor)


def availability_label(product: Product) -> str:
    """Return "available", "out_of_stock", "discontinued" or "coming_soon".

    Status is the source of truth: stock only matters for active products.
    """
    status = product["status"]
    if status == DISCONTINUED:
        return DISCONTINUED
    if status == COMING_SOON:
        return COMING_SOON
    if status == "active":
        return AVAILABLE if int(product["stock_quantity"]) > 0 else OUT_OF_STOCK
    raise ValueError(f"Unknown product status: {status!r}")


def is_purchasable(product: Product) -> bool:
    """True only if the product is active AND has stock."""
    return availability_label(product) == AVAILABLE


def active_promotion(product_id: int, promotions: pd.DataFrame) -> dict[str, Any] | None:
    """Return the active promotion with the highest discount for a product, or None."""
    rows = promotions[(promotions["product_id"] == product_id) & (promotions["is_active"] == 1)]
    if rows.empty:
        return None
    best = rows.sort_values("discount_percent", ascending=False).iloc[0]
    return best.to_dict()


def final_price(product: Product, promotion: Mapping[str, Any] | None) -> PriceQuote:
    """Compute the price breakdown for a product.

    Policy 6.2: discounts are not cumulative. With an active promotion, PIX pays the
    promotional price (no extra 5%). Without one, PIX gets 5% off the list price.
    """
    original = round_money(float(product["price_brl"]))
    if promotion is not None:
        percent = float(promotion["discount_percent"])
        promo_price = _apply_discount(original, percent)
        return PriceQuote(original, percent, promo_price, promo_price)
    return PriceQuote(original, 0.0, None, _apply_discount(original, PIX_DISCOUNT_PERCENT))


@dataclass(frozen=True)
class ReturnWindow:
    """One return/exchange window: last valid day (inclusive) and whether it is still open."""

    eligible: bool
    deadline: date
    days_left: int


@dataclass(frozen=True)
class ReturnEligibility:
    """Return/exchange windows for an order. Windows are None when not applicable."""

    applicable: bool
    reason: str
    regret_7_days: ReturnWindow | None = None
    defect_exchange_30_days: ReturnWindow | None = None


def _window(start: date, days: int, today: date) -> ReturnWindow:
    deadline = start + timedelta(days=days)
    return ReturnWindow(today <= deadline, deadline, max((deadline - today).days, 0))


def return_eligibility(
    status: str, order_date: date, estimated_delivery: date | None, today: date
) -> ReturnEligibility:
    """Compute the 7-day regret window and the 30-day defect exchange window.

    - Regret (policy 4.1): 7 calendar days after delivery. The data has no real
      delivery date, so `estimated_delivery` is used as a proxy.
    - Defect exchange (policy 4.2): 30 calendar days after the purchase (order date).
    - Only delivered orders are eligible. Policy 4.1 covers online purchases; the data
      has no sales channel, so every order is treated as online.
    """
    if status != "delivered":
        return ReturnEligibility(
            False, f"Order status is {status!r}; return windows apply only to delivered orders."
        )
    delivered = estimated_delivery or order_date
    return ReturnEligibility(
        applicable=True,
        reason="Regret window counted from estimated_delivery (proxy: the data has no real delivery date).",
        regret_7_days=_window(delivered, REGRET_WINDOW_DAYS, today),
        defect_exchange_30_days=_window(order_date, DEFECT_EXCHANGE_DAYS, today),
    )
