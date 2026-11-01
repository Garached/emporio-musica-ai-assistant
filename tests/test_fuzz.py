"""Fuzz tests: hostile or malformed tool inputs must never escape run_tool (offline)."""

import json
import time

import pytest

from emporio.formatting import strip_markdown
from emporio.grounding import prices_in
from emporio.tools import run_tool

WEIRD_TEXT = [
    "[", "(((", ".*", "\\", "'; DROP TABLE products;--", "%s%s%n", "{{date}}",
    "<script>alert(1)</script>", "😀🎸🔥", "\x00\x01", "ç" * 500, "a" * 10_000,
    " ".join(["violao"] * 2_000), "   ", "",
]
WEIRD_IDS = [-1, 0, 10**30, "abc", "", "81", 3.7, None, [], {}, "1e309", "0x51", "٣"]
WEIRD_LAST4 = ["12ab", "1234567890", "abcd", "", "-432", "４３２１", None, "😀😀😀😀", 4320, "43210"]


def assert_well_formed(result):
    assert isinstance(result, dict)
    json.dumps(result)  # serializable, no NaN/objects
    if "error" in result:
        assert isinstance(result["error"], str) and result["error"]


@pytest.mark.parametrize("query", WEIRD_TEXT)
def test_search_query_fuzz(query):
    result = run_tool("search_products", {"query": query})
    assert_well_formed(result)
    assert "total_found" in result  # treated as plain text, never as a pattern or command


@pytest.mark.parametrize("args", [
    {"category": "'; DROP TABLE"}, {"category": "Violões\x00"}, {"category": ""},
    {"min_price": -1}, {"max_price": 0}, {"max_price": 1e308}, {"min_price": "abc"},
    {"limit": -5}, {"limit": 0}, {"limit": 10**9}, {"limit": "abc"}, {"limit": 3.7},
    {"only_available": "no"}, {"query": None},
])
def test_search_other_args_fuzz(args):
    assert_well_formed(run_tool("search_products", args))


@pytest.mark.parametrize("product_id", WEIRD_IDS)
@pytest.mark.parametrize("tool", ["get_product_details", "get_installment_options"])
def test_product_id_fuzz(tool, product_id):
    result = run_tool(tool, {"product_id": product_id})
    assert_well_formed(result)
    if product_id != "81":  # a numeric string is accepted as an id
        assert "error" in result


@pytest.mark.parametrize("order_id", WEIRD_IDS)
def test_order_id_fuzz(order_id):
    result = run_tool("get_order_status", {"order_id": order_id, "phone_last4": "4321"})
    assert_well_formed(result)
    assert "error" in result or result.get("order_id") == 5  # never another order's data


@pytest.mark.parametrize("last4", WEIRD_LAST4)
def test_phone_last4_fuzz(last4):
    result = run_tool("get_order_status", {"order_id": 5, "phone_last4": last4})
    assert_well_formed(result)
    assert "error" in result  # none of these are the right 4 digits (4321)


@pytest.mark.parametrize("last4", ["4 3 2 1", "(4321)", 4321])
def test_correct_digits_in_other_formats_are_accepted(last4):
    """Spaces, punctuation or an int with the right digits are the same 4 digits."""
    assert run_tool("get_order_status", {"order_id": 5, "phone_last4": last4})["status"] == "delivered"


@pytest.mark.parametrize("topic", ["", "../../etc/passwd", ".*", "1.", "' OR 1=1", "x" * 5_000])
def test_policy_topic_fuzz(topic):
    result = run_tool("get_store_policy", {"topic": topic})
    assert_well_formed(result)


@pytest.mark.parametrize("name", ["", "__import__", "search_products; rm -rf /", "SEARCH_PRODUCTS", "😀"])
def test_unknown_tool_names(name):
    assert "error" in run_tool(name, {})


@pytest.mark.parametrize("args", ["not a dict", ["a", "b"], 42, ("x",)])
def test_non_dict_args_are_rejected(args):
    result = run_tool("search_products", args)
    assert_well_formed(result)
    assert "error" in result


@pytest.mark.parametrize("text", ["*" * 5_000, "**" * 3_000, "_" * 5_000, "# " * 3_000, "R$ " * 3_000])
def test_text_helpers_handle_pathological_input_fast(text):
    start = time.perf_counter()
    strip_markdown(text)
    prices_in(text)
    assert time.perf_counter() - start < 2.0  # no catastrophic regex backtracking
