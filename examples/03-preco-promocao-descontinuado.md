# 03 — Preço, promoções e produto descontinuado

**O que mostra:** Preço exato do catálogo, promoções com preço original e desconto (sem PIX extra) e produto descontinuado com alternativas e aviso de diferença de preço.

- Modelo: gemini-3.5-flash-lite
- Gerado em 2026-10-31 21:39 por `scripts/record_examples.py`, sem edição. Dígitos de telefone mascarados na lista de ferramentas.

---

**Cliente:** Quanto custa o Takamine GD20?

**Clave:** O violão Takamine GD20 custa R$ 2.199,00 no cartão ou R$ 2.089,05 no PIX. Posso te ajudar com mais alguma coisa?

Ferramentas usadas:
- `search_products` `{"query": "takamine gd20"}` → total_found=1, results=1 items (28 ms)

---

**Cliente:** Tem alguma promoção rolando?

**Clave:** Temos algumas promoções ativas no momento:  
  
- Crafter HT-100 Folk Aço Natural: de R$ 2.399,00 por R$ 1.967,18 (18% de desconto)  
- Taylor 110e Dreadnought Natural: de R$ 5.999,00 por R$ 5.519,08 (8% de desconto)  
- Ohana CK-20 Concert Natural: de R$ 549,00 por R$ 439,20 (20% de desconto)  
- Kalani KAL-700T Tenor Natural: de R$ 359,00 por R$ 323,10 (10% de desconto)  
  
Lembrando que para esses itens em promoção o valor no PIX é o mesmo preço promocional, sem desconto extra. Quer saber mais detalhes sobre algum deles?

Ferramentas usadas:
- `list_active_promotions` `{}` → total=4, promotions=4 items (24 ms)

---

**Cliente:** E o Ibanez Bass 2X, ainda tem?

**Clave:** O Ibanez Bass 2X Electric Bass foi descontinuado, então não temos mais ele no catálogo.  
  
Como opções de baixos disponíveis, temos algumas alternativas, mas vale notar que elas estão em uma faixa de preço bem mais alta que o modelo original:  
  
- Music Man Bass 4X Electric Bass: R$ 7.157,00 no cartão ou R$ 6.799,15 no PIX  
- Music Man Bass 1X Electric Bass: R$ 8.732,00 no cartão ou R$ 8.295,40 no PIX  
- Yamaha Bass 3X Electric Bass: R$ 11.445,00 no cartão ou R$ 10.872,75 no PIX  
  
Faz sentido olhar alguma delas ou prefere buscar outro modelo?

Ferramentas usadas:
- `search_products` `{"query": "ibanez bass 2x", "only_available": false}` → total_found=1, results=1 items (27 ms)
- `get_product_details` `{"product_id": 136}` → product_id=136, name=Ibanez Bass 2X Electric Bass, category=Baixos, availability=discontinued, price=441.0, pix_price=418.95, alternatives=3 items (26 ms)

---

