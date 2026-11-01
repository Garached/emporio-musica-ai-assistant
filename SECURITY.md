# Security

Threat model for Clave, the customer service agent of Empório da Música, mapped to the
[OWASP Top 10 for LLM Applications (2025)](https://genai.owasp.org/llm-top-10/).

This is a technical-challenge project: a local CLI, one user per process, read-only data
from CSV/PDF files. The notes below say what is protected today and what a production
deployment would still need.

## What we protect

| Asset | Where | Sensitivity |
| --- | --- | --- |
| Customer personal data (name, phone, e-mail) | `data/raw/*customers.csv` | High (LGPD) |
| Orders (items, totals, tracking codes) | `data/raw/*orders.csv`, `*order_items.csv` | High: linked to a person |
| Gemini API key | `.env` (git-ignored) | High: cost and abuse |
| Catalog, prices, promotions, policies | `data/raw/` | Public, but must be correct |

**Trust boundaries.** Customer messages are untrusted. Model output is untrusted. Tool
results come from our own files but are passed to the model as data, never as
instructions.

**Principle.** Anything security-critical is enforced in code, not only in the prompt.
A prompt can be talked around; code can't.

## OWASP LLM Top 10 (2025)

### LLM01 Prompt Injection
- **Here:** customers can try to override the rules ("ignore your instructions", "I'm the
  manager", fake "SYSTEM OVERRIDE", fake coupons).
- **Mitigations:**
  - The tools are read-only and can't grant discounts. Prices and discounts are computed in
    code ([business_rules.py](src/emporio/business_rules.py)), so an injected "50% off"
    has nothing to act on.
  - Identity checks and the brute-force lock are in code
    ([tools.py](src/emporio/tools.py) `get_order_status`, [guards.py](src/emporio/guards.py)).
  - The prompt treats tool output as data, not instructions
    ([system_prompt.md](src/emporio/prompts/system_prompt.md), "Segurança").
  - Messages over 2,000 characters are rejected before the LLM is called
    ([agent.py](src/emporio/agent.py) `MAX_INPUT_CHARS`).
  - Red-team evals cover this ([evals/scenarios.json](evals/scenarios.json):
    `prompt_injection`, `english_injection`, `fake_manager`, `fake_discount_code`,
    `grandma_jailbreak`, `base64_injection`, `social_engineering_multiturn`,
    `price_sycophancy`).
- **Residual:** the model can still be persuaded to *say* something wrong (for example,
  promise a discount in text). It can't *do* anything harmful, but a production
  deployment should add output checks for price and discount claims, and monitoring.

### LLM02 Sensitive Information Disclosure
- **Here:** order lookups could leak another customer's data. Logs and transcripts could
  store personal data.
- **Mitigations:**
  - **Verification:** an order is shown only if the last 4 phone digits match. E-mail is
    not used, because two customers share one ([docs/data-quality.md](docs/data-quality.md)).
  - **No enumeration:** a missing order and wrong digits return the *same* error.
  - **Brute-force lock:** after 3 failed checks in a conversation, `get_order_status` is
    locked and the tool is no longer called ([guards.py](src/emporio/guards.py)
    `VerificationGuard`).
  - **Minimal data:** the tool returns the first name only. No tool returns phones,
    e-mails or full names, and no tool lists customers.
  - **Masking:** `phone_last4`, first name and tracking code are masked (`••••`) in the
    debug trace, logs, transcripts and eval reports. The tool still gets the real value
    (`mask_args` / `mask_result` in [guards.py](src/emporio/guards.py)).
  - **Repository hygiene:** transcripts and eval runs are git-ignored
    ([.gitignore](.gitignore)).
- **Residual / production:**
  - 4 digits is weak authentication. Production needs real authentication (login, or a
    one-time code sent to the registered phone).
  - The lock is per conversation: a new conversation (`/nova`, restarting the app) resets
    it. Production needs a server-side lock per order, customer and IP address.
  - What the customer types (e.g. "telefone final 0123") is saved unmasked in the local
    transcript. Production needs a retention policy (e.g. delete after N days) and
    encryption at rest.
  - Conversation content, including order details, is sent to Google. On the free tier
    Google may use it to improve its models. Production must use a paid tier/agreement
    where customer data is not used for training.

### LLM03 Supply Chain
- **Here:** Python dependencies (google-genai, pandas, pypdf, rich...).
- **Mitigations:**
  - Only well-known packages, plus the official Google SDK.
  - `pip-audit` on the installed versions found **no known vulnerabilities** (41 packages
    plus pip, 2026-10-31).
- **Residual / production:** [requirements.txt](requirements.txt) uses minimum versions
  (`>=`), not pins. Production needs a lock file with hashes (pip-tools/uv) and automated
  dependency scanning in CI (pip-audit, Dependabot).

### LLM04 Data and Model Poisoning
- **Here:** we don't train or fine-tune. The "data" is the catalog and the policy PDF.
- **Mitigations:**
  - Known errors in the PDF (wrong phone, accented e-mail) are corrected in code
    ([policies.py](src/emporio/policies.py) `CORRECTIONS`).
  - Data inconsistencies are reported automatically
    ([scripts/data_quality_report.py](scripts/data_quality_report.py)).
  - Policy text reaches the model as tool output, which the prompt marks as data.
- **Residual:** anyone who can edit `data/raw/` controls what Clave says. Production needs
  access control and change review for the data sources.

### LLM05 Improper Output Handling
- **Here:** model output is shown in a terminal and saved to markdown files.
- **Mitigations:**
  - Output is never executed and never used in SQL, shell or HTML.
  - The CLI prints replies as `rich.Text`, so model output can't inject terminal markup.
  - Markdown emphasis is stripped before display ([formatting.py](src/emporio/formatting.py)).
  - **Output grounding check:** before a reply is sent, every R$ value in it must match a
    number returned by a tool in this conversation (or written by the customer), within
    R$ 0,01. Otherwise the model gets one nudge; if the reply is still ungrounded, the
    customer gets the fallback message with the store contact instead
    ([grounding.py](src/emporio/grounding.py), `Agent._finish` in [agent.py](src/emporio/agent.py)).
  - An empty model response is retried once before falling back.
  - Tool arguments from the model are validated before running:
    - unknown or missing arguments are rejected ([tools.py](src/emporio/tools.py) `run_tool`);
    - categories and policy topics are enums;
    - IDs are converted to integers;
    - result limits are clamped.
- **Residual:** if replies were later rendered in a web page, they would need HTML
  escaping there.

### LLM06 Excessive Agency
- **Here:** the agent can only call seven read-only tools. It can't create orders, issue
  refunds, change data or send messages.
- **Mitigations:**
  - Read-only tools, a tool allow-list with schemas ([tools.py](src/emporio/tools.py)
    `get_tools`), and at most 6 LLM iterations per message ([agent.py](src/emporio/agent.py)).
  - Returns and complaints are handed off to humans, by design (system prompt).
- **Residual:** low. If write actions are added later (orders, refunds), they need
  explicit user confirmation and server-side authorization.

### LLM07 System Prompt Leakage
- **Here:** customers may ask Clave to reveal her instructions.
- **Mitigations:**
  - The prompt contains **no secrets**. It's in this public repository anyway, and
    security doesn't depend on keeping it secret: all critical rules are in code.
  - The prompt tells Clave not to reveal it, and the `reveal_prompt` eval checks this.
- **Residual:** leakage is possible but low impact.

### LLM08 Vector and Embedding Weaknesses
- **Not applicable:** no RAG, embeddings or vector database. Policies are split into
  sections by code and fetched by exact topic ([policies.py](src/emporio/policies.py)).

### LLM09 Misinformation
- **Here:** wrong prices, stock, promotions, deadlines or policies would hurt customers
  (and the manual notes this may count as misleading advertising).
- **Mitigations:**
  - All money math is in code (`Decimal`, half-up rounding). The rule that PIX doesn't
    stack on promotions is sent as data (`pix_extra_discount: false`).
  - Installments are computed in code too: `get_installment_options` applies the tiered
    minimums of policy 3.1, and the prompt forbids calculating installments
    ([business_rules.py](src/emporio/business_rules.py) `installment_options`).
  - **Output grounding (code):** R$ values the model invents or computes by itself (prices
    of non-existent products, "savings", totals) are blocked before reaching the customer.
    This was added after a recorded example listed three invented products with prices.
    See LLM05.
  - The prompt forbids popularity, sales and review claims (there is no such data), and a
    global eval invariant checks every reply for them.
  - Search reports `unavailable_matches`, and a price-gap note is generated in code.
  - The prompt forbids stating facts without calling a tool.
  - The open/closed status and return windows are computed in code.
  - Evals cover these cases ([evals/results/](evals/results/)).
- **Residual:** the model can still phrase things wrongly. The grounding check covers R$
  values only: a wrong product name, spec or date with no price is not caught, and a real
  price attached to the wrong product would pass (it was returned by a tool). The evals
  sample behavior and don't prove it (single runs; the judge is the same model).
  Production needs regular eval runs, sampled human review and customer feedback loops.

### LLM10 Unbounded Consumption
- **Here:** free-tier quota and cost; very long messages; tool loops.
- **Mitigations:**
  - Input limit of 2,000 characters.
  - At most 6 LLM iterations per message.
  - History trimmed to 20 messages.
  - 60 s request timeout.
  - Bounded retries with backoff; the client gives up when the quota is exhausted
    ([gemini.py](src/emporio/llm/gemini.py)).
  - Search results capped at 20.
- **Residual / production:** per-user/IP rate limiting, spending caps and alerts on the
  API key, and usage monitoring.

## Payment fraud

- **Risk:** the most damaging thing a store assistant can say is a fake payment detail. If
  Clave invented a PIX key, bank account or payment link (or confirmed a phishing link), a
  customer could send money to a fraudster. The data has **no PIX key, bank account or
  payment link**, so any such detail in a reply would be invented.
- **Mitigations:**
  - Clave only gives the official contacts (phone/WhatsApp, e-mail, address), fixed in the
    prompt and corrected in the policy text ([policies.py](src/emporio/policies.py)).
  - Red-team evals: `fake_pix_key` (asks for the store's PIX key; must not invent one or
    use the CNPJ as a key) and `phishing_link` (asks whether a suspicious payment link is the
    store's; must not confirm it and must warn). Both pass
    ([evals/results/red-team.md](evals/results/red-team.md)).
  - The output grounding check blocks invented R$ amounts, but it does not cover keys,
    accounts or links.
- **Residual / production:** this rule is enforced by the prompt and tested by evals, not
  blocked in code. A production deployment should add an output filter that blocks
  URLs, e-mail addresses and CNPJ/CPF-like numbers other than the official contacts, and
  publish its official payment channels so customers can check them.

## Secrets

- The API key is read from `.env` (git-ignored); [.env.example](.env.example) has
  placeholders only.
- **History scan (2026-10-31):** all 58 commits searched.
  - No Gemini key pattern (`AIza…`).
  - No `api_key/secret/token/password` assignment with a real value.
  - No private keys.
  - `.env` was never committed.
- **Production:** use a secrets manager (e.g. GCP Secret Manager), rotate keys, restrict
  the key to the Generative Language API, and add pre-commit secret scanning (gitleaks).

## Not covered (honest list)

- Real customer authentication. Session handling and multi-user isolation (the CLI is
  single-user and local).
- Server-side rate limiting, abuse detection, monitoring and alerting.
- Encryption at rest and a retention policy for transcripts.
- Moderation of model output beyond the provider's default safety filters.
- Robustness against new jailbreaks: tested with 13 red-team scenarios (single runs),
  partly judged by the same model.
- A code-level filter for payment details (PIX keys, accounts, links): see "Payment fraud".
- Pinned, hashed dependencies.

## Security tests

- **Unit tests** (offline, in `pytest`):
  - [tests/test_guards.py](tests/test_guards.py): brute-force lock, input limit, PII masking.
  - [tests/test_tools.py](tests/test_tools.py): verification and identical errors.
  - [tests/test_grounding.py](tests/test_grounding.py): output grounding and masked
    rejected drafts.
- **Fuzzing** ([tests/test_fuzz.py](tests/test_fuzz.py), about 100 cases): regex
  metacharacters, SQL-like strings, emojis, control characters and 10,000-character
  queries; negative, zero, huge and non-numeric product/order IDs; phone digits with
  letters, 10 digits or full-width digits; path-like policy topics; unknown tool names and
  non-object arguments; pathological input for the markdown and price regexes. No
  exception escapes `run_tool` and every output is a JSON-serializable dict.
  - **Found and fixed:** non-object arguments (e.g. a string) raised an exception before
    validation; `run_tool` now rejects them with an error.
- **Static analysis (2026-11-01):** `bandit -r src evals scripts` (bandit 1.9.4, 2,748
  lines) found **no issues**. A grep for `eval(`, `exec(`, `pickle`, `subprocess`,
  `os.system`, `shell=True`, `yaml.load` and `__import__` found no uses. The only matches
  were `re.compile` (regex), the word "eval" in docstrings, and `"__import__"` as fuzz-test
  data.
- **Red-team evals against the real model** (13 scenarios, all passing; results in
  [evals/results/red-team.md](evals/results/red-team.md)):
  - Round 1: `reveal_prompt`, `fake_manager`, `other_customer_data`, `brute_force`,
    `english_injection`, `fake_discount_code`.
  - Round 2: `fake_pix_key`, `phishing_link`, `order_existence_oracle`, `price_sycophancy`,
    `social_engineering_multiturn`, `grandma_jailbreak`, `base64_injection`.
