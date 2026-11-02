# 03 — Preço, promoções e produto descontinuado

**O que mostra:** Preço exato do catálogo, promoções com preço original e desconto (sem PIX extra) e produto descontinuado com alternativas e aviso de diferença de preço.

- Modelo: gemini-3.5-flash-lite
- Gerado em 2026-11-01 20:15 por `scripts/record_examples.py`, sem edição. Dígitos de telefone mascarados na lista de ferramentas.

---

**Cliente:** Quanto custa o Takamine GD20?

**Clave:** O Takamine GD20 sai por R$ 2.199,00 no cartão, ou R$ 2.089,05 no PIX.  
  
No cartão, você pode parcelar em até 12x de R$ 183,25 sem juros.  
  
Posso te ajudar com mais alguma coisa?  
  
Nossa loja está fechada agora e a equipe volta segunda-feira, 02/11, às 09:00. Enquanto isso, sigo te ajudando por aqui.

Ferramentas usadas:
- `search_products` `{"query": "takamine gd20"}` → total_found=1, results=1 items (12 ms)
- `get_installment_options` `{"product_id": 95}` → product_id=95, name=Takamine GD20 Dreadnought Natural, availability=available, price=2199.0, has_promotion=False, max_installments=12, max_installment_value=... (2 ms)

---

**Cliente:** Tem alguma promoção rolando?

**Clave:** No momento temos alguns instrumentos em promoção:  
  
- Crafter HT-100 Folk Aço Natural: de R$ 2.399,00 por R$ 1.967,18 (18% de desconto)  
- Taylor 110e Dreadnought Natural: de R$ 5.999,00 por R$ 5.519,08 (8% de desconto)  
- Ohana CK-20 Concert Natural: de R$ 549,00 por R$ 439,20 (20% de desconto)  
- Kalani KAL-700T Tenor Natural: de R$ 359,00 por R$ 323,10 (10% de desconto)  
  
Quer saber mais detalhes sobre algum deles?

Ferramentas usadas:
- `list_active_promotions` `{}` → total=4, promotions=4 items (22 ms)

---

**Cliente:** E o Ibanez Bass 2X, ainda tem?

**Clave:** Poxa, o Ibanez Bass 2X foi descontinuado e não está mais disponível para compra 😕  
  
Como alternativa, temos outros baixos no catálogo, mas os valores deles são bem mais altos (de R$ 7.157,00 a R$ 11.445,00).  
  
Faz sentido ver alguma dessas opções ou prefere dar uma olhada em outra categoria?

Ferramentas usadas:
- `search_products` `{"query": "ibanez bass 2x", "only_available": false}` → total_found=1, results=1 items (12 ms)
- `get_product_details` `{"product_id": 136}` → product_id=136, name=Ibanez Bass 2X Electric Bass, category=Baixos, availability=discontinued, price=441.0, pix_price=418.95, alternatives=3 items (21 ms)

---

## Verificação automática

Feita pelo script em cada resposta: invariantes globais das evals (sem exageros, contato correto, sem PIX extra em promoção, sem markdown, sem alegações de popularidade), checagem de grounding (todo valor em R$ veio de uma ferramenta) e filtro de contatos (nenhum contato, link ou dado de pagamento não oficial).

- ✅ Nenhuma falha.
