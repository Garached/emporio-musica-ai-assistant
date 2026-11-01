"""Run automated data quality checks and write docs/data-quality.md.

Usage:
    python scripts/data_quality_report.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from emporio.business_rules import availability_label
from emporio.data import PROJECT_ROOT, StoreData, load_store_data

REPORT_PATH = PROJECT_ROOT / "docs" / "data-quality.md"


@dataclass
class Check:
    """One check: a title, a short explanation and the offending rows."""

    title: str
    description: str
    rows: pd.DataFrame


def to_markdown(df: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub markdown table (no extra dependency)."""
    if df.empty:
        return "_No issues found._"
    header = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    body = ["| " + " | ".join(_fmt(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, sep, *body])


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return "" if pd.isna(value) else str(value)


# --- checks -------------------------------------------------------------------

def status_stock_mismatch(d: StoreData) -> Check:
    p = d.products
    rows = p[(p["status"] != "active") & (p["stock_quantity"] > 0)]
    return Check(
        "Products whose status and stock disagree",
        "Non-active products (discontinued / coming_soon) that still have stock. "
        "Status is the source of truth: these are NOT purchasable.",
        rows[["product_id", "name", "status", "stock_quantity"]],
    )


def active_zero_stock(d: StoreData) -> Check:
    p = d.products
    rows = p[(p["status"] == "active") & (p["stock_quantity"] <= 0)]
    return Check(
        "Active products with zero stock",
        "Listed as active but cannot be bought right now (reported as out of stock).",
        rows[["product_id", "name", "status", "stock_quantity"]],
    )


def empty_categories(d: StoreData) -> Check:
    used = set(d.products["category_id"])
    rows = d.categories[~d.categories["category_id"].isin(used)]
    return Check(
        "Categories with no products",
        "Categories that exist but have nothing in the catalog.",
        rows[["category_id", "name"]],
    )


def orphan_promotions(d: StoreData) -> Check:
    pr = d.promotions
    rows = pr[~pr["product_id"].isin(d.products["product_id"])]
    return Check(
        "Promotions pointing to missing products",
        "Promotions whose product_id does not exist in products.",
        rows[["promotion_id", "product_id", "discount_percent", "is_active"]],
    )


def multiple_active_promotions(d: StoreData) -> Check:
    active = d.promotions[d.promotions["is_active"] == 1]
    counts = active.groupby("product_id").size()
    rows = active[active["product_id"].isin(counts[counts > 1].index)]
    return Check(
        "Products with more than one active promotion",
        "If found, the highest discount is applied (see business_rules.active_promotion).",
        rows[["promotion_id", "product_id", "discount_percent", "description"]],
    )


def promotions_on_unpurchasable(d: StoreData) -> Check:
    active = d.promotions[d.promotions["is_active"] == 1]
    merged = active.merge(d.products, on="product_id", how="inner")
    merged["availability"] = merged.apply(availability_label, axis=1)
    rows = merged[merged["availability"] != "available"]
    return Check(
        "Active promotions on products that cannot be bought",
        "An active promotion is pointless if the product is not purchasable.",
        rows[["promotion_id", "product_id", "name", "availability", "discount_percent"]],
    )


def order_total_mismatch(d: StoreData) -> Check:
    items = d.order_items.merge(d.products[["product_id", "price_brl"]], on="product_id", how="left")
    items["line_total"] = items["quantity"] * items["price_brl"]
    sums = items.groupby("order_id", as_index=False)["line_total"].sum()
    merged = d.orders.merge(sums, on="order_id", how="left")
    merged["difference"] = (merged["total_brl"] - merged["line_total"]).round(2)
    rows = merged[merged["difference"].abs() > 0.01]
    return Check(
        "Order totals that differ from the sum of their items",
        "Items are priced at the CURRENT list price (the data has no price-at-purchase), "
        "so differences may come from price changes, promotions or PIX discounts at the "
        "time of the order. The agent reports the order total exactly as stored.",
        rows[["order_id", "status", "payment_method", "total_brl", "line_total", "difference"]]
        .rename(columns={"line_total": "items_sum_current_price"}),
    )


def duplicate_customer_contacts(d: StoreData) -> Check:
    c = d.customers
    frames = []
    for field in ("email", "phone"):
        normalized = c[field].str.strip().str.lower()
        dupes = c[normalized.duplicated(keep=False)].assign(duplicated_field=field)
        frames.append(dupes)
    rows = pd.concat(frames, ignore_index=True)
    return Check(
        "Duplicate customer emails / phones",
        "Customers sharing the same email or phone (case-insensitive).",
        rows[["duplicated_field", "customer_id", "name", "email", "phone"]],
    )


def orphan_order_items(d: StoreData) -> Check:
    oi = d.order_items.assign(
        missing_product=~d.order_items["product_id"].isin(d.products["product_id"]),
        missing_order=~d.order_items["order_id"].isin(d.orders["order_id"]),
    )
    rows = oi[oi["missing_product"] | oi["missing_order"]]
    return Check(
        "Order items pointing to missing products or orders",
        "Line items whose product_id or order_id does not exist.",
        rows[["order_id", "product_id", "quantity", "missing_product", "missing_order"]],
    )


def orders_integrity(d: StoreData) -> Check:
    o = d.orders.assign(
        missing_customer=~d.orders["customer_id"].isin(d.customers["customer_id"]),
        no_items=~d.orders["order_id"].isin(d.order_items["order_id"]),
    )
    rows = o[o["missing_customer"] | o["no_items"]]
    return Check(
        "Orders with missing customers or no items",
        "Orders whose customer_id does not exist, or that have no line items.",
        rows[["order_id", "customer_id", "status", "missing_customer", "no_items"]],
    )


def orders_with_unpurchasable_products(d: StoreData) -> Check:
    items = d.order_items.merge(d.products, on="product_id", how="inner")
    items["availability"] = items.apply(availability_label, axis=1)
    items = items.merge(d.orders[["order_id", "order_date", "status"]], on="order_id",
                        suffixes=("_product", "_order"))
    rows = items[items["availability"].isin(["discontinued", "coming_soon"])]
    return Check(
        "Orders containing products that are not sold today",
        "Informational: past orders of products now discontinued or coming_soon. "
        "A coming_soon product in a past order is suspicious.",
        rows[["order_id", "order_date", "status_order", "product_id", "name", "availability"]],
    )


CHECKS = [
    status_stock_mismatch,
    active_zero_stock,
    empty_categories,
    orphan_promotions,
    multiple_active_promotions,
    promotions_on_unpurchasable,
    order_total_mismatch,
    duplicate_customer_contacts,
    orphan_order_items,
    orders_integrity,
    orders_with_unpurchasable_products,
]


POLICY_SECTION = """\
## Policy document inconsistencies

Issues found by reading `data/raw/políticas_da_loja.pdf`, with the decision taken for each.

### a) Two different phone numbers
- **Issue:** (67) 3341-4444 appears on the cover and in the company data table (1.2);
  section 7 (WhatsApp) says (67) 3321-4500.
- **Decision:** use **(67) 3341-4444**. It appears twice, including the official company data table.
- **Applied in:** `src/emporio/policies.py` (`CORRECTIONS`) rewrites the wrong number in the
  extracted policy text, so tools never return it.

### b) Email with an accent in the company table
- **Issue:** table 1.2 writes `contato@empóriodamusica.com.br`; the cover writes
  `contato@emporiodamusica.com.br`.
- **Decision:** use **contato@emporiodamusica.com.br** (cover version). Accented email
  addresses are not reliably deliverable.
- **Applied in:** `src/emporio/policies.py` (`CORRECTIONS`) rewrites the accented email in the
  extracted policy text, so tools never return it.

### c) Conflicting installment rules
- **Issue:** the payment table says credit card has a minimum installment of R$ 100,00;
  section 3.1 gives tiered rules: up to 3x with no minimum (except purchases below R$ 50,00),
  4x–6x with a minimum of R$ 80,00, 7x–12x with a minimum of R$ 100,00.
- **Decision:** apply the more specific **tiered rules of 3.1**. For edge cases the agent
  suggests confirming with the store.
- **Assumption:** "até 3x sem valor mínimo, exceto abaixo de R$ 50,00" is read as a minimum
  installment of R$ 50,00 for 2x–3x. A single payment (1x) has no minimum.
- **Applied in:** `src/emporio/business_rules.py` (`installment_options`), exposed by the
  `get_installment_options` tool, so installment values are computed in code, never by the model.

### d) Catalog described in the manual vs. actual data
- **Issue:** the manual claims 300+ instruments, including wind and orchestral instruments.
  The catalog has {product_count} products and no products in those categories
  ({empty_categories}).
- **Decision:** **the data is the source of truth.** The agent only offers what is in the catalog.

### e) Order dates
- **Issue:** orders are dated up to {last_order_date}.
- **Assumption:** the data is a snapshot. Order statuses are reported exactly as they are in the data.
"""


def build_report(d: StoreData) -> str:
    """Run all checks and return the full markdown report."""
    results = [check(d) for check in CHECKS]
    lines = [
        "# Data Quality Report",
        "",
        "Generated by `scripts/data_quality_report.py` from `data/raw/` (raw data is never modified).",
        "",
        "## Dataset overview",
        "",
        to_markdown(pd.DataFrame(
            [(name, len(getattr(d, name))) for name in
             ("categories", "products", "customers", "orders", "order_items", "promotions")],
            columns=["table", "rows"],
        )),
        "",
        "## Summary of automated checks",
        "",
        to_markdown(pd.DataFrame(
            [(r.title, len(r.rows)) for r in results], columns=["check", "issues"]
        )),
        "",
        "## Automated check details",
        "",
    ]
    for r in results:
        lines += [f"### {r.title}", "", r.description, "", to_markdown(r.rows), ""]

    empty = empty_categories(d).rows["name"].tolist()
    lines.append(POLICY_SECTION.format(
        product_count=len(d.products),
        empty_categories=", ".join(empty) if empty else "none",
        last_order_date=d.orders["order_date"].max().strftime("%B %Y"),
    ))
    return "\n".join(lines)


def main(path: Path = REPORT_PATH) -> None:
    """Build the report and write it to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_report(load_store_data()), encoding="utf-8")
    print(f"Report written to {path}")


if __name__ == "__main__":
    main()
