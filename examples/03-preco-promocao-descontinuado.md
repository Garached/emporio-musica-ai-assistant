# 03 — Preço, promoções e produto descontinuado

**O que mostra:** Preço exato do catálogo, promoções com preço original e desconto (sem PIX extra) e produto descontinuado com alternativas e aviso de diferença de preço.

- Modelo: gemini-3.5-flash-lite
- Gerado em 2026-11-01 19:22 por `scripts/record_examples.py`, sem edição. Dígitos de telefone mascarados na lista de ferramentas.

---

**Cliente:** Quanto custa o Takamine GD20?

**Clave:** O Takamine GD20 Dreadnought Natural sai por R$ 2.199,00 no cartão ou R$ 2.089,05 no PIX. Você pode parcelar em até 12x de R$ 183,25 sem juros no cartão de crédito.  
  
Precisa de mais alguma informação sobre ele?

Ferramentas usadas:
- `search_products` `{"query": "takamine gd20"}` → total_found=1, results=1 items (32 ms)
- `get_installment_options` `{"product_id": 95}` → product_id=95, name=Takamine GD20 Dreadnought Natural, availability=available, price=2199.0, has_promotion=False, max_installments=12, max_installment_value=... (7 ms)

---

**Cliente:** Tem alguma promoção rolando?

**Clave:** Temos algumas promoções ativas no momento:  
  
- Crafter HT-100 Folk Aço Natural: de R$ 2.399,00 por R$ 1.967,18 (18% de desconto)  
- Taylor 110e Dreadnought Natural: de R$ 5.999,00 por R$ 5.519,08 (8% de desconto)  
- Ohana CK-20 Concert Natural (ukulele): de R$ 549,00 por R$ 439,20 (20% de desconto)  
- Kalani KAL-700T Tenor Natural (ukulele): de R$ 359,00 por R$ 323,10 (10% de desconto)  
  
Algum desses chamou sua atenção?

Ferramentas usadas:
- `list_active_promotions` `{}` → total=4, promotions=4 items (33 ms)

---

**Cliente:** E o Ibanez Bass 2X, ainda tem?

**Clave:** Poxa, o Ibanez Bass 2X está descontinuado e não faz mais parte do catálogo da loja.  
  
Temos algumas alternativas de baixos disponíveis, mas vale notar que os preços são bem diferentes do Ibanez (que custava R$ 441,00):  
  
- Music Man Bass 4X Electric Bass por R$ 7.157,00 (ou R$ 6.799,15 no PIX)  
- Music Man Bass 1X Electric Bass por R$ 8.732,00 (ou R$ 8.295,40 no PIX)  
- Yamaha Bass 3X Electric Bass por R$ 11.445,00 (ou R$ 10.872,75 no PIX)  
  
Alguma dessas opções faz sentido para você?

Ferramentas usadas:
- `search_products` `{"query": "ibanez bass 2x", "only_available": false}` → total_found=1, results=1 items (37 ms)
- `get_product_details` `{"product_id": 136}` → product_id=136, name=Ibanez Bass 2X Electric Bass, category=Baixos, availability=discontinued, price=441.0, pix_price=418.95, alternatives=3 items (32 ms)

---

## Verificação automática

Feita pelo script em cada resposta: invariantes globais das evals (sem exageros, contato correto, sem PIX extra em promoção, sem markdown, sem alegações de popularidade) e checagem de grounding (todo valor em R$ veio de uma ferramenta).

- ✅ Nenhuma falha.
