"""Tests for availability, promotion and pricing rules."""

import pandas as pd
import pytest

from emporio.business_rules import (
    active_promotion,
    availability_label,
    final_price,
    installment_options,
    is_purchasable,
    minimum_installment,
    round_money,
)
from emporio.data import load_store_data


@pytest.fixture(scope="module")
def store():
    return load_store_data()


def product(store, product_id: int) -> pd.Series:
    return store.products.set_index("product_id", drop=False).loc[product_id]


# --- availability (real cases) ---------------------------------------------------

@pytest.mark.parametrize(
    "product_id, label",
    [
        (136, "discontinued"),  # discontinued but has stock
        (130, "coming_soon"),   # coming_soon with stock
        (96, "out_of_stock"),   # active with zero stock
        (81, "available"),
    ],
)
def test_availability_label_real_cases(store, product_id, label):
    assert availability_label(product(store, product_id)) == label


@pytest.mark.parametrize("product_id, expected", [(136, False), (130, False), (96, False), (81, True)])
def test_is_purchasable_real_cases(store, product_id, expected):
    assert is_purchasable(product(store, product_id)) is expected


def test_status_beats_stock():
    assert not is_purchasable({"status": "discontinued", "stock_quantity": 50})


def test_unknown_status_raises():
    with pytest.raises(ValueError):
        availability_label({"status": "archived", "stock_quantity": 1})


# --- promotions ------------------------------------------------------------------

def test_active_promotion_found(store):
    promo = active_promotion(121, store.promotions)
    assert promo is not None and promo["discount_percent"] == 20


def test_inactive_promotions_ignored(store):
    # Product 96 only has inactive promotions (18% and 40%).
    assert active_promotion(96, store.promotions) is None


def test_highest_active_discount_wins():
    promotions = pd.DataFrame(
        {
            "promotion_id": [1, 2, 3],
            "product_id": [10, 10, 10],
            "discount_percent": [10.0, 25.0, 50.0],
            "is_active": [1, 1, 0],
        }
    )
    assert active_promotion(10, promotions)["promotion_id"] == 2


# --- pricing ---------------------------------------------------------------------

def test_final_price_with_promotion_has_no_pix_on_top(store):
    p = product(store, 121)  # R$ 549.00, 20% active promotion
    quote = final_price(p, active_promotion(121, store.promotions))
    assert quote.original_price == 549.0
    assert quote.discount_percent == 20.0
    assert quote.promotional_price == 439.2
    assert quote.pix_price == 439.2  # policy 6.2: not cumulative
    assert quote.has_promotion


def test_final_price_without_promotion_gives_pix_discount(store):
    p = product(store, 81)  # R$ 599.90, no promotion
    quote = final_price(p, active_promotion(81, store.promotions))
    assert quote.original_price == 599.9
    assert quote.discount_percent == 0.0
    assert quote.promotional_price is None
    assert quote.pix_price == 569.91  # 599.90 * 0.95 = 569.905 -> 569.91
    assert not quote.has_promotion


def test_money_rounding_is_half_up():
    assert round_money(2.675) == 2.68
    assert final_price({"price_brl": 799.9}, None).pix_price == 759.91  # 759.905


# --- installments (policy 3.1) -----------------------------------------------------------

def _option(plan, n):
    return next(o for o in plan.options if o.installments == n)


def test_installments_1299():
    plan = installment_options(1299.00)
    assert (_option(plan, 10).value, _option(plan, 10).allowed) == (129.90, True)
    assert plan.max_installments == 12
    assert _option(plan, 12).value == 108.25


def test_installments_599_90():
    plan = installment_options(599.90)
    assert (_option(plan, 6).value, _option(plan, 6).allowed) == (99.98, True)
    assert (_option(plan, 7).value, _option(plan, 7).allowed) == (85.70, False)  # < R$ 100
    assert plan.max_installments == 6


def test_installments_120():
    plan = installment_options(120.00)
    assert (_option(plan, 3).value, _option(plan, 3).allowed) == (40.00, False)  # < R$ 50
    assert plan.max_installments == 2


def test_installment_tiers_and_single_payment():
    assert [minimum_installment(n) for n in (1, 2, 3, 4, 6, 7, 12)] == [0, 50, 50, 80, 80, 100, 100]
    plan = installment_options(30.00)
    assert plan.max_installments == 1 and len(plan.options) == 12
