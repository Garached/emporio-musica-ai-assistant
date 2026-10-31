# Phase 02 — Agent Tools

**Goal:** Build the provider-agnostic tools the LLM will call via function calling (plain Python functions + a JSON Schema registry and a safe dispatcher). No LLM calls.

---

Context: Phase 2 of the Empório da Música customer service agent. See
docs/prompts/ for previous phases. The data layer (src/emporio/data.py),
business rules (business_rules.py) and policies (policies.py) are done and
tested. Read them before starting and reuse them; do not duplicate logic.

Goal of this phase: the TOOLS the LLM will call via function calling.
Still NO LLM calls in this phase. Tools must be provider-agnostic: plain Python
functions that return JSON-serializable dicts, plus a registry describing them
with JSON Schema (we'll adapt it to Gemini in a later phase, and it should be
easy to adapt to other providers too).

1. src/emporio/tools.py: implement these tools. Keep outputs compact (the
   LLM's context is limited): return only the fields the agent needs.
   Never raise for "not found" cases: return {"error": "..."} with a short,
   clear message instead.

   a) search_products(query=None, category=None, min_price=None,
      max_price=None, only_available=True, limit=8)
      - Text search over name, description and specs, case- and
        accent-insensitive (e.g. "takamine gd20", "nylon", "eletrico").
      - `category` must be one of the existing category names (expose them
        as an enum in the schema, so the LLM picks a valid one).
      - Price filters apply to the price the customer actually pays
        (promotional price when there is an active promotion).
      - Each result: product_id, name, category, availability label,
        price info from business_rules.final_price, sorted by price.
      - Also return `total_found` so the agent knows if results were cut.

   b) get_product_details(product_id)
      - Full details: description, specs, availability, price info.
      - If the product is NOT purchasable, include up to 3 purchasable
        `alternatives` from the same category, closest in price
        (policy 7.3: suggest similar available products).

   b2) list_active_promotions()
      - Only active promotions on purchasable products, with original price,
        discount % and promotional price (policy 6.2: always show the
        original price together with the discount).

   c) get_order_status(order_id, phone_last4)
      - Identity check (LGPD): the last 4 digits of the phone must match the
        order's customer. Email is NOT used because two customers share the
        same email (see docs/data-quality.md).
      - If the order does not exist OR the digits don't match, return the
        SAME generic error, so the tool never reveals whether an order
        exists.
      - On success: status (plus a Portuguese label), order date, total
        exactly as stored, payment method, tracking code, estimated delivery,
        items (name + quantity), notes (e.g. cancellation reason), and the
        customer's first name only (for a personal greeting).
      - Status label assumptions (document them in the docstring):
        pending = aguardando confirmação do pagamento; confirmed = pagamento
        confirmado, em separação; shipped = enviado; delivered = entregue;
        cancelled = cancelado.
      - Also include `return_eligibility`, computed by a new pure function in
        business_rules.py: the 7-day regret window (counted from delivery;
        the data has no real delivery date, so use estimated_delivery as a
        proxy and say so) and the 30-day defect exchange window (from the
        order date). Only meaningful for delivered orders.

   d) get_store_policy(topic)
      - `topic` is an enum of the policy section titles from
        policies.load_policy_sections(); returns that section's text.

   e) get_store_hours_status()
      - Current date/time in the store's timezone: America/Campo_Grande
        (UTC-4, NOT Brasília time). Returns whether the store is open now
        and, if closed, the next opening day/time. Hours: Mon-Fri 09:00-18:00,
        Sat 09:00-13:00, Sun closed. Holidays are not in the data: mention
        this limitation in the docstring.

   "Today" must be injectable: read an optional EMPORIO_TODAY setting
   (ISO date or datetime) from config, falling back to the real current
   time. The data is a snapshot from early 2026, so this lets us demo the
   return-window rules realistically. Add it to config.py and .env.example.

2. A TOOL REGISTRY in tools.py: for each tool, its name, a clear description
   written for the LLM (when to use it and when NOT to), its JSON Schema
   parameters, and the Python callable. Descriptions are prompts too: make
   them precise. Plus a `run_tool(name, args)` dispatcher that validates the
   tool name, calls it, and catches unexpected exceptions into
   {"error": ...} so a bad tool call never crashes the conversation.

3. tests/test_tools.py: real cases:
   - "takamine gd20" finds the GD20 at R$ 2199.00
   - category Violões + max_price 1000 returns only purchasable items
     priced <= 1000 and excludes product 96 (out of stock)
   - details of product 96 include alternatives, all purchasable
   - promotions list has exactly the active, purchasable ones
   - order lookup: correct digits succeed; wrong digits and a non-existent
     order return the SAME error message
   - return eligibility with an injected "today" inside and outside the
     7-day window
   - store hours with injected datetimes: Saturday 12:00 open; Saturday
     14:00 closed with next opening Monday 09:00; Sunday closed
   - get_store_policy for the returns section mentions 7 days
   - run_tool with an unknown tool name returns an error, no exception
   Run pytest; everything (old and new tests) must pass.

4. Save this exact prompt to docs/prompts/02-agent-tools.md with a short
   header.

Code style: type hints, short docstrings, small functions, no over-engineering.

Git rules: small logical commits (e.g. product tools, order tool + return
rules, policy and hours tools, registry, tests, prompt). Short English
Conventional Commit messages. Do NOT push.

When done, summarize: tools created, commits, test results, and any decision
you had to make that I should know about.
