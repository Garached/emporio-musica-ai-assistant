"""Load the store's raw CSV data into typed pandas DataFrames."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
CSV_PREFIX = "desafio_tecnico_ai_eng - "


@dataclass(frozen=True)
class StoreData:
    """All store tables, one DataFrame per CSV."""

    categories: pd.DataFrame
    products: pd.DataFrame
    customers: pd.DataFrame
    orders: pd.DataFrame
    order_items: pd.DataFrame
    promotions: pd.DataFrame


def csv_path(table: str, data_dir: Path = RAW_DATA_DIR) -> Path:
    """Return the path of a raw CSV by table name (e.g. "products")."""
    return data_dir / f"{CSV_PREFIX}{table}.csv"


def _read(table: str, data_dir: Path) -> pd.DataFrame:
    return pd.read_csv(csv_path(table, data_dir), encoding="utf-8")


def _parse_specs(raw: object) -> dict:
    """Parse a JSON specs string into a dict (empty dict if missing)."""
    if not isinstance(raw, str) or not raw.strip():
        return {}
    return json.loads(raw)


def load_categories(data_dir: Path = RAW_DATA_DIR) -> pd.DataFrame:
    """Load product categories."""
    return _read("categories", data_dir)


def load_products(categories: pd.DataFrame, data_dir: Path = RAW_DATA_DIR) -> pd.DataFrame:
    """Load products with parsed specs, typed columns and the category name joined in."""
    df = _read("products", data_dir)
    df["price_brl"] = df["price_brl"].astype(float)
    df["stock_quantity"] = df["stock_quantity"].astype(int)
    df["specs"] = df["specs"].map(_parse_specs)
    df["created_at"] = pd.to_datetime(df["created_at"])
    names = categories[["category_id", "name"]].rename(columns={"name": "category_name"})
    return df.merge(names, on="category_id", how="left")


def load_customers(data_dir: Path = RAW_DATA_DIR) -> pd.DataFrame:
    """Load customers."""
    return _read("customers", data_dir)


def load_orders(data_dir: Path = RAW_DATA_DIR) -> pd.DataFrame:
    """Load orders with dates parsed and totals as float."""
    df = _read("orders", data_dir)
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["estimated_delivery"] = pd.to_datetime(df["estimated_delivery"])
    df["total_brl"] = df["total_brl"].astype(float)
    return df


def load_order_items(data_dir: Path = RAW_DATA_DIR) -> pd.DataFrame:
    """Load order line items."""
    return _read("order_items", data_dir)


def load_promotions(data_dir: Path = RAW_DATA_DIR) -> pd.DataFrame:
    """Load promotions with the discount as float."""
    df = _read("promotions", data_dir)
    df["discount_percent"] = df["discount_percent"].astype(float)
    df["is_active"] = df["is_active"].astype(int)
    return df


@lru_cache(maxsize=None)
def load_store_data(data_dir: Path = RAW_DATA_DIR) -> StoreData:
    """Load every table once and cache the result."""
    categories = load_categories(data_dir)
    return StoreData(
        categories=categories,
        products=load_products(categories, data_dir),
        customers=load_customers(data_dir),
        orders=load_orders(data_dir),
        order_items=load_order_items(data_dir),
        promotions=load_promotions(data_dir),
    )
