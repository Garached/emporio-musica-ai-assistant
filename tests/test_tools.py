"""Tests for the LLM tools and the tool registry (real data from data/raw)."""

import json
from datetime import date, datetime

import pytest

from emporio.business_rules import is_purchasable, return_eligibility
from emporio.config import STORE_TIMEZONE, current_datetime
from emporio.data import load_store_data
from emporio.tools import (
    ORDER_NOT_FOUND,
    get_order_status,
    get_product_details,
    get_store_hours_status,
    get_store_policy,
    list_active_promotions,
    run_tool,
    search_products,
    tool_specs,
)

# Order 5: delivered, customer phone (67) 98765-4321, ordered 2026-01-05,
# estimated delivery 2026-01-18.
ORDER_ID = 5
PHONE_LAST4 = "4321"


def store_time(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=STORE_TIMEZONE)


# --- products ---------------------------------------------------------------------

def test_search_finds_takamine_gd20():
    result = search_products("takamine gd20")
    assert result["total_found"] == 1
    product = result["results"][0]
    assert product["product_id"] == 95
    assert product["price"] == 2199.00


def test_search_is_accent_insensitive():
    with_accent = search_products("elétrico", limit=20)
    without = search_products("eletrico", limit=20)
    assert with_accent["total_found"] == without["total_found"] > 0


def test_search_category_and_max_price():
    result = search_products(category="Violões", max_price=1000, limit=20)
    products = load_store_data().products.set_index("product_id", drop=False)
    ids = [r["product_id"] for r in result["results"]]
    assert ids and 96 not in ids  # 96 is out of stock
    assert all(r["price"] <= 1000 for r in result["results"])
    assert all(r["category"] == "Violões" for r in result["results"])
    assert all(is_purchasable(products.loc[pid]) for pid in ids)
    prices = [r["price"] for r in result["results"]]
    assert prices == sorted(prices)


def test_search_unknown_category_returns_error():
    assert "error" in search_products(category="Pianos")


def test_search_price_filter_uses_promotional_price():
    # Product 121: list R$ 549.00, 20% off -> R$ 439.20.
    ids = [r["product_id"] for r in search_products(max_price=440, limit=20)["results"]]
    assert 121 in ids


def test_details_of_unavailable_product_include_purchasable_alternatives():
    details = get_product_details(96)
    assert details["availability"] == "out_of_stock"
    alternatives = details["alternatives"]
    assert 1 <= len(alternatives) <= 3
    products = load_store_data().products.set_index("product_id", drop=False)
    for alt in alternatives:
        assert alt["category"] == "Violões"
        assert is_purchasable(products.loc[alt["product_id"]])


def test_details_not_found_returns_error():
    assert "error" in get_product_details(9999)


def test_active_promotions_are_exactly_the_active_purchasable_ones():
    store = load_store_data()
    products = store.products.set_index("product_id", drop=False)
    active_ids = store.promotions.loc[store.promotions["is_active"] == 1, "product_id"]
    expected = {int(pid) for pid in active_ids if is_purchasable(products.loc[pid])}

    result = list_active_promotions()
    assert {p["product_id"] for p in result["promotions"]} == expected == {90, 94, 121, 127}
    for promo in result["promotions"]:
        assert promo["original_price"] > promo["promotional_price"]


# --- orders -----------------------------------------------------------------------

def test_order_lookup_with_correct_digits():
    result = get_order_status(ORDER_ID, PHONE_LAST4, today=date(2026, 1, 22))
    assert result["status"] == "delivered"
    assert result["status_label"] == "entregue"
    assert result["total_brl"] == 4599.0
    assert result["customer_first_name"] == "Rafael"
    assert result["items"] == [{"name": "Crafter D-8 Dreadnought Natural", "quantity": 1}]


def test_wrong_digits_and_missing_order_return_the_same_error():
    wrong_digits = get_order_status(ORDER_ID, "0000")
    missing_order = get_order_status(9999, PHONE_LAST4)
    assert wrong_digits == missing_order == {"error": ORDER_NOT_FOUND}


def test_cancelled_order_shows_reason_and_no_return_window():
    result = get_order_status(18, "7654")
    assert result["status"] == "cancelled"
    assert result["notes"] == "Item fora de estoque no momento do pedido"
    assert result["return_eligibility"]["applicable"] is False


def test_return_window_inside_7_days():
    elig = get_order_status(ORDER_ID, PHONE_LAST4, today=date(2026, 1, 22))["return_eligibility"]
    assert elig["regret_7_days"] == {"eligible": True, "deadline": "2026-01-25", "days_left": 3}
    assert elig["defect_exchange_30_days"]["eligible"] is True


def test_return_window_outside_7_days_but_inside_30():
    elig = get_order_status(ORDER_ID, PHONE_LAST4, today=date(2026, 1, 30))["return_eligibility"]
    assert elig["regret_7_days"]["eligible"] is False
    assert elig["defect_exchange_30_days"] == {
        "eligible": True, "deadline": "2026-02-04", "days_left": 5,
    }


def test_return_eligibility_last_day_is_inclusive():
    elig = return_eligibility("delivered", date(2026, 1, 5), date(2026, 1, 18), date(2026, 1, 25))
    assert elig.regret_7_days.eligible and elig.regret_7_days.days_left == 0


def test_injected_today_from_env(monkeypatch):
    monkeypatch.setenv("EMPORIO_TODAY", "2026-01-30T10:00")
    assert current_datetime() == store_time("2026-01-30T10:00")
    elig = get_order_status(ORDER_ID, PHONE_LAST4)["return_eligibility"]
    assert elig["regret_7_days"]["eligible"] is False


# --- policies and hours -----------------------------------------------------------

def test_returns_policy_mentions_7_days():
    result = get_store_policy("4. Política de Trocas e Devoluções")
    assert "7 (sete) dias" in result["text"]


def test_unknown_policy_topic_returns_error():
    assert "error" in get_store_policy("astrologia")


def test_saturday_noon_is_open():
    status = get_store_hours_status(now=store_time("2026-03-21T12:00"))  # Saturday
    assert status["is_open"] is True
    assert status["closes_at"] == "13:00"


def test_saturday_afternoon_closed_until_monday():
    status = get_store_hours_status(now=store_time("2026-03-21T14:00"))
    assert status["is_open"] is False
    assert status["next_opening"] == {
        "date": "2026-03-23", "weekday": "segunda-feira", "time": "09:00",
    }


def test_sunday_is_closed():
    status = get_store_hours_status(now=store_time("2026-03-22T10:00"))
    assert status["is_open"] is False
    assert status["today_hours"] == "fechado"


def test_hours_use_campo_grande_time_not_utc():
    # 21:30 UTC on a Friday = 17:30 in Campo Grande (UTC-4): still open.
    status = get_store_hours_status(now=datetime.fromisoformat("2026-03-20T21:30+00:00"))
    assert status["is_open"] is True


# --- registry ---------------------------------------------------------------------

def test_run_tool_unknown_name_returns_error():
    result = run_tool("delete_database", {})
    assert "error" in result


def test_run_tool_rejects_hidden_and_missing_args():
    assert "error" in run_tool("get_order_status", {"order_id": 5, "phone_last4": "4321", "today": "x"})
    assert "error" in run_tool("get_product_details", {})


def test_run_tool_catches_exceptions():
    assert "error" in run_tool("search_products", {"limit": "not-a-number"})


def test_specs_are_valid_and_json_serializable():
    specs = tool_specs()
    assert len(specs) == 6
    for spec in specs:
        assert spec["description"] and spec["parameters"]["type"] == "object"
    json.dumps(specs)


@pytest.mark.parametrize(
    "name, args",
    [
        ("search_products", {"query": "nylon"}),
        ("get_product_details", {"product_id": 96}),
        ("list_active_promotions", {}),
        ("get_order_status", {"order_id": ORDER_ID, "phone_last4": PHONE_LAST4}),
        ("get_store_policy", {"topic": "8. Garantia"}),
        ("get_store_hours_status", {}),
    ],
)
def test_every_tool_output_is_json_serializable(name, args):
    result = run_tool(name, args)
    assert "error" not in result
    json.dumps(result)
