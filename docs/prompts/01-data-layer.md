# Phase 01 — Data Layer

**Goal:** Build a clean, tested data layer (CSV loaders, business rules, policy PDF parsing, data quality report). No LLM calls.

---

Context: Phase 1 of the Empório da Música customer service agent (see
docs/prompts/00-project-setup.md for the project context). Raw data lives in
data/raw/ and must never be modified. The CSV file names contain spaces
(e.g. "desafio_tecnico_ai_eng - products.csv") and the policy PDF name has an
accent ("políticas_da_loja.pdf"), so handle paths carefully with pathlib.

Goal of this phase: a clean, tested data layer. NO LLM calls in this phase.

1. src/emporio/data.py
   - Load all 6 CSVs into pandas DataFrames with correct dtypes
     (dates as dates, money as float, specs parsed from JSON into dicts).
   - Join category names into products.
   - Expose a single `load_store_data()` function returning a frozen dataclass
     `StoreData` with one attribute per table. Cache it (functools.lru_cache)
     so files are read only once.

2. src/emporio/business_rules.py: pure functions, no I/O:
   - `is_purchasable(product)`: True only if status == "active" AND stock > 0.
     Status is the source of truth: a "discontinued" product with stock is NOT
     purchasable; "coming_soon" is NOT purchasable.
   - `availability_label(product)`: one of "available", "out_of_stock",
     "discontinued", "coming_soon".
   - `active_promotion(product_id, promotions)`: only promotions with
     is_active == 1. If several are active for the same product, pick the
     highest discount.
   - `final_price(product, promotion)`: returns original price, discount %,
     promotional price, and PIX price. PIX gives 5% off the list price ONLY
     when there is no active promotion (policy 6.2: discounts are not
     cumulative). Round money to 2 decimals.
   Money math must live in code, never be left to the LLM.

3. src/emporio/policies.py
   - Extract the text of the policy PDF with pypdf, clean it (remove the
     repeated page headers/footers like "Página N" and the manual title line),
     and split it into sections by their top-level numbers (1. Sobre..., 2.
     Horário..., etc.). Expose `load_policy_sections()` returning a dict
     {section_title: text}, cached.

4. scripts/data_quality_report.py
   - Runs automated checks and writes docs/data-quality.md. Checks to include:
     products whose status and stock disagree; active products with zero
     stock; categories with no products; promotions pointing to missing
     products; order totals that differ from the sum of their items;
     duplicate customer emails/phones; order items pointing to missing
     products or orders.
   - The report must also contain a hand-written section "Policy document
     inconsistencies" with these known issues and the decision for each:
     a) Two phone numbers: (67) 3341-4444 (cover + company data table) vs
        (67) 3321-4500 (WhatsApp section). Decision: use 3341-4444, it appears
        twice including the official company data table.
     b) Email written with an accent in the company table
        ("empóriodamusica"). Decision: use contato@emporiodamusica.com.br
        (cover page version; accented emails are not reliably deliverable).
     c) Installments: table says minimum installment R$100 for credit card,
        section 3.1 gives tiered rules (up to 3x no minimum except below
        R$50; 4-6x min R$80; 7-12x min R$100). Decision: apply the more
        specific tiered rules of 3.1, and the agent suggests confirming with
        the store for edge cases.
     d) The manual claims 300+ instruments and sells wind/orchestral
        instruments, but the catalog has 64 products and no products in
        those categories. Decision: the data is the source of truth.
     e) Orders are dated up to March 2026. Assumption: the data is a
        snapshot; order statuses are reported as they are in the data.
   - Run the script and commit the generated report.

5. tests/test_data.py and tests/test_business_rules.py
   - Cover: all tables load with the expected row counts; specs parse as
     dicts; the purchasable rules (use real cases: product 136 discontinued
     with stock, 130 coming_soon, 96 active with zero stock); active
     promotion selection; final price with promo (no PIX discount on top)
     and without promo (PIX = 5% off); policy sections are found
     (e.g. "Horário" and "Trocas" sections exist).
   - Run pytest and make sure everything passes.

6. Save this exact prompt to docs/prompts/01-data-layer.md with a short
   header (phase name and goal).

Code style: type hints, short docstrings, small functions, no over-engineering.

Git rules: small logical commits as you go (e.g. one for loaders, one for
business rules, one for policies, one for the report, one for tests, one for
the prompt). Short English messages, Conventional Commits. Do NOT push.

When done, give me a short summary: files created, commits made, test
results, and the main findings of the data quality report.
