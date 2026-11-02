# 02 — Informações da loja

**O que mostra:** Endereço oficial, horário de sábado e regra de parcelamento por faixa (seção 3.1).

- Modelo: gemini-3.5-flash-lite
- Gerado em 2026-11-01 20:15 por `scripts/record_examples.py`, sem edição. Dígitos de telefone mascarados na lista de ferramentas.

---

**Cliente:** Qual o endereço de vocês?

**Clave:** O endereço da Empório da Música é Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, 79202-333.  
  
Precisa de mais alguma informação?  
  
Nossa loja está fechada agora e a equipe volta segunda-feira, 02/11, às 09:00. Enquanto isso, sigo te ajudando por aqui.

---

**Cliente:** Vocês abrem sábado?

**Clave:** Sim, aos sábados a loja abre das 09:00 às 13:00.  
  
Mais alguma dúvida que eu possa ajudar?

Ferramentas usadas:
- `get_store_policy` `{"topic": "2. Horário de Funcionamento"}` → topic=2. Horário de Funcionamento (0 ms)

---

**Cliente:** Posso parcelar em 10x um violão de R$ 1.299?

**Clave:** Sim, o Yamaha FG800 Dreadnought Natural que custa R$ 1.299,00 pode ser parcelado em até 12x sem juros. Em 10x, fica por 10 parcelas de R$ 129,90.  
  
Quer saber mais sobre ele ou ver outra opção?

Ferramentas usadas:
- `search_products` `{"min_price": 1290, "max_price": 1300, "query": "violão"}` → total_found=2, results=2 items (45 ms)
- `get_installment_options` `{"product_id": 92}` → product_id=92, name=Yamaha FG800 Dreadnought Natural, availability=available, price=1299.0, has_promotion=False, max_installments=12, max_installment_value=1... (2 ms)

---

## Verificação automática

Feita pelo script em cada resposta: invariantes globais das evals (sem exageros, contato correto, sem PIX extra em promoção, sem markdown, sem alegações de popularidade), checagem de grounding (todo valor em R$ veio de uma ferramenta) e filtro de contatos (nenhum contato, link ou dado de pagamento não oficial).

- ✅ Nenhuma falha.
