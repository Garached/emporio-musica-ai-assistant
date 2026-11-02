# Empório da Música: AI customer service agent

Clave is a customer service agent for Empório da Música, a fictional musical instrument store in Campo Grande (MS, Brazil). She answers in Portuguese using the store's catalog, orders and policy manual, through Google Gemini function calling.

## Highlights

- **Hand-built agent loop** with Gemini function calling. No agent framework, so every step is visible and testable.
- **Business rules live in code**, not in the prompt: prices, the PIX discount (and the rule that it doesn't stack with promotions), installment limits, availability.
- **The final reply is checked in code**: every R$ value must come from a tool result, and unofficial contact or payment details (fake PIX keys, links, bank accounts) are blocked.
- **Data quality analysis** of the CSVs and the policy PDF, with a documented decision for each inconsistency.
- **Evals against the real model**: a baseline, fixes, a final run, plus automated and manual red teaming.
- **Provider abstraction**: the agent only talks to a small `LLMClient` interface. Gemini is one implementation.
- **Built with AI under a test-gated, phase-by-phase workflow.** Every prompt is in [`docs/prompts/`](docs/prompts/).

### Example

From [examples/04-devolucao-dentro-do-prazo.md](examples/04-devolucao-dentro-do-prazo.md) (simulated date 2026-02-20, unedited):

> **Cliente:** Pedido 7, final 0123
>
> **Clave:** Oi, Letícia! Vi aqui que o seu pedido do ukulelê Shelby SU-21S Soprano Sunburst foi entregue e o prazo de 7 dias para arrependimento vai até 24/02/2026, com base na previsão de entrega.
> Como o prazo ainda tá aberto, você consegue pedir a devolução. O instrumento precisa estar na embalagem original, sem marcas de uso e com todos os acessórios e manuais.
> Para prosseguir com a troca ou devolução, é só chamar a equipe pelo WhatsApp no (67) 3341-4444 ou mandar um e-mail para contato@emporiodamusica.com.br. Posso te ajudar com mais alguma coisa?
>
> Tools: `get_order_status` `{"phone_last4": "••••", "order_id": 7}` → status=delivered, customer_first_name=••••, …

The identity check, the return deadline and the masking of personal data are all done in code. The model only writes the sentence.

### Quick tour for reviewers

| File | Why look at it |
| --- | --- |
| [src/emporio/agent.py](src/emporio/agent.py) | The agent loop: LLM calls, tool calls, and the checks on the final reply |
| [src/emporio/tools.py](src/emporio/tools.py) | The 7 read-only tools, their JSON Schema and the `run_tool` dispatcher |
| [src/emporio/business_rules.py](src/emporio/business_rules.py) | Prices, PIX, promotions, installments and return windows, all in code |
| [evals/results/final.md](evals/results/final.md) | Latest full eval run (and [red-team.md](evals/results/red-team.md)) |
| [SECURITY.md](SECURITY.md) | Threat model mapped to the OWASP Top 10 for LLM apps |
| [docs/prompts/](docs/prompts/) | Every prompt used to build the project, in order |

## Getting started

### Prerequisites

- Python 3.11 or newer
- A free Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

### Install

Windows (PowerShell):

```powershell
git clone https://github.com/Garached/emporio-musica-ai-assistant.git
cd emporio-musica-ai-assistant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
notepad .env    # set GEMINI_API_KEY
```

macOS / Linux:

```bash
git clone https://github.com/Garached/emporio-musica-ai-assistant.git
cd emporio-musica-ai-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
nano .env       # set GEMINI_API_KEY
```

If PowerShell blocks the activation script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

Optional settings in `.env`: `GEMINI_MODEL` (default `gemini-3.5-flash-lite`), `GEMINI_THINKING_LEVEL` (default `low`) and `EMPORIO_TODAY` (simulated date, see below).

### Run

```bash
emporio                      # chat with Clave
emporio --debug              # also show the tools used after each reply
emporio --today 2026-02-20   # simulate "today" (the data is a snapshot from early 2026)
python -m emporio            # same as emporio
```

`--today` matters for date rules: order 7 is inside the 7-day return window on 2026-02-20, and outside it with the real date.

Chat commands: `/ajuda` (help), `/nova` (new conversation), `/debug` (toggle debug mode), `/sair` (exit). Every session is saved to `transcripts/` (git-ignored).

### Tests

```bash
pytest
```

The tests are offline and free: they use a fake LLM, no API key needed. One integration test is skipped unless `RUN_INTEGRATION=1` is set.

### Evals (real model)

```bash
python -m evals.run_evals --judge            # full suite, saves evals/results/<date>.md
python -m evals.run_evals --judge --only promotions,phishing_link
```

The full suite with `--judge` takes a few hundred requests. The Gemini free tier allows 500 requests per day for this model, so a full run plus a few re-runs can hit the daily limit. The runner then stops, marks the remaining scenarios as skipped, and still saves the report.
