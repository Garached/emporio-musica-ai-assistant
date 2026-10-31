"""Tests for the data loaders and the policy parser (uses the real files in data/raw)."""

import pandas as pd
import pytest

from emporio.data import load_store_data
from emporio.policies import load_policy_sections


@pytest.fixture(scope="module")
def store():
    return load_store_data()


@pytest.mark.parametrize(
    "table, rows",
    [
        ("categories", 9),
        ("products", 65),
        ("customers", 50),
        ("orders", 20),
        ("order_items", 22),
        ("promotions", 25),
    ],
)
def test_tables_load_with_expected_row_counts(store, table, rows):
    assert len(getattr(store, table)) == rows


def test_load_is_cached():
    assert load_store_data() is load_store_data()


def test_specs_are_parsed_as_dicts(store):
    assert store.products["specs"].map(lambda s: isinstance(s, dict)).all()
    yamaha = store.products.set_index("product_id").loc[81, "specs"]
    assert yamaha["strings"] == "nylon"


def test_dtypes(store):
    assert store.products["price_brl"].dtype == float
    assert store.orders["total_brl"].dtype == float
    assert pd.api.types.is_datetime64_any_dtype(store.orders["order_date"])
    assert pd.api.types.is_datetime64_any_dtype(store.products["created_at"])


def test_category_name_joined_into_products(store):
    products = store.products.set_index("product_id")
    assert products.loc[116, "category_name"] == "Ukuleles"
    assert products["category_name"].notna().all()


def test_accents_are_read_correctly(store):
    name = store.products.set_index("product_id").loc[86, "name"]
    assert "Aço" in name


@pytest.fixture(scope="module")
def sections():
    return load_policy_sections()


def test_policy_has_ten_sections(sections):
    assert len(sections) == 10
    assert next(iter(sections)).startswith("1. Sobre")


@pytest.mark.parametrize("keyword", ["Horário", "Pagamento", "Trocas", "Frete", "Garantia"])
def test_policy_sections_found(sections, keyword):
    assert any(keyword in title for title in sections)


def test_policy_text_is_cleaned(sections):
    full_text = "\n".join(sections.values())
    assert "Página" not in full_text
    assert "Manual de Políticas e Procedimentos" not in full_text


def test_policy_section_content(sections):
    hours = next(text for title, text in sections.items() if "Horário" in title)
    assert "09:00 às 18:00" in hours
    whatsapp = next(text for title, text in sections.items() if "WhatsApp" in title)
    # The numbered list inside 7.2 must stay in section 7, not become new sections.
    assert "Fechamento" in whatsapp
