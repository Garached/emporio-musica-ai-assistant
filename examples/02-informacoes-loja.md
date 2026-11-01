# 02 — Informações da loja

**O que mostra:** Endereço oficial, horário de sábado e regra de parcelamento por faixa (seção 3.1).

- Modelo: gemini-3.5-flash-lite
- Gerado em 2026-11-01 19:21 por `scripts/record_examples.py`, sem edição. Dígitos de telefone mascarados na lista de ferramentas.

---

**Cliente:** Qual o endereço de vocês?

**Clave:** A nossa loja fica na Rua 14 de Maio, 3200, no Centro de Campo Grande - MS (CEP 79202-333).  
  
Posso te ajudar com mais alguma coisa por aqui?

---

**Cliente:** Vocês abrem sábado?

**Clave:** Sim, aos sábados nós abrimos das 09:00 às 13:00.  
  
Precisa de ajuda com mais alguma coisa?

Ferramentas usadas:
- `get_store_policy` `{"topic": "2. Horário de Funcionamento"}` → topic=2. Horário de Funcionamento (0 ms)

---

**Cliente:** Posso parcelar em 10x um violão de R$ 1.299?

**Clave:** Sim, dá para parcelar em até 12x sem juros no cartão. Para um violão de R$ 1.299,00, em 10x fica em 10 parcelas de R$ 129,90.  
  
Se preferir no PIX, ele sai por R$ 1.234,05.  
  
Posso te ajudar com mais alguma coisa?

Ferramentas usadas:
- `search_products` `{"max_price": 1300, "min_price": 1290}` → total_found=3, results=3 items (177 ms)
- `get_installment_options` `{"product_id": 92}` → product_id=92, name=Yamaha FG800 Dreadnought Natural, availability=available, price=1299.0, has_promotion=False, max_installments=12, max_installment_value=1... (5 ms)

---

## Verificação automática

Feita pelo script em cada resposta: invariantes globais das evals (sem exageros, contato correto, sem PIX extra em promoção, sem markdown, sem alegações de popularidade) e checagem de grounding (todo valor em R$ veio de uma ferramenta).

- ✅ Nenhuma falha.
