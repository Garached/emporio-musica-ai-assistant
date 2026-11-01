# Example conversations

Five multi-turn conversations with Clave, recorded with the real model by
[`scripts/record_examples.py`](../scripts/record_examples.py). Replies are **unedited**.
Each file lists the tool calls below every reply, with phone digits and personal fields
masked (`••••`).

| File | Scenario | What it shows | Tools used |
| --- | --- | --- | --- |
| [01-catalogo-violoes.md](01-catalogo-violoes.md) | Beginner looking for a guitar up to R$ 1.000 | Category + price filter, refining by nylon, product details, PIX price from the system. Also shows the dispatcher rejecting an invented argument (`ByCategory`) and the model retrying correctly | `search_products`, `get_product_details` |
| [02-informacoes-loja.md](02-informacoes-loja.md) | Store information | Official address, Saturday hours, installment rule for 10x of R$ 1.299 | `get_store_policy` |
| [03-preco-promocao-descontinuado.md](03-preco-promocao-descontinuado.md) | Price, promotions, discontinued item | Exact catalog price; promotions with original price and discount, and no extra PIX discount; discontinued bass with alternatives and a warning about the price gap | `search_products`, `list_active_promotions`, `get_product_details` |
| [04-devolucao-dentro-do-prazo.md](04-devolucao-dentro-do-prazo.md) | Return within the 7-day window (non-trivial, simulated date 2026-02-20) | Policy first, then identity check (order + last 4 phone digits), order lookup, deadline counted from the delivery forecast, and handoff to the store for the return itself | `get_store_policy`, `get_order_status` |
| [05-fora-do-escopo-e-seguranca.md](05-fora-do-escopo-e-seguranca.md) | Out of scope and security | Accessories (not sold), off-topic question, prompt injection asking for 50% off, order lookup with wrong digits (nothing revealed) | `get_order_status` |

## How to regenerate

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/record_examples.py              # all five
python scripts/record_examples.py --only 04    # just one
python scripts/record_examples.py --delay 6    # slower pacing for the free tier
```

This needs `GEMINI_API_KEY` in `.env`. Each run overwrites the files, and replies vary
between runs because the model is not deterministic.
