# 04 — Devolução dentro do prazo (não trivial)

**O que mostra:** Pedido de devolução: verificação de identidade, consulta do pedido, cálculo do prazo de arrependimento (a partir da previsão de entrega) e política de trocas.

- Modelo: gemini-3.5-flash-lite
- Data simulada: 2026-02-20 10:00 (horário de Campo Grande)
- Gerado em 2026-11-01 20:16 por `scripts/record_examples.py`, sem edição. Dígitos de telefone mascarados na lista de ferramentas.

---

**Cliente:** Me arrependi da minha compra, posso devolver?

**Clave:** Pode sim! Para compras online, você tem até 7 dias corridos após o recebimento para pedir a devolução por arrependimento, sem precisar justificar.  
  
O instrumento precisa estar na embalagem original, sem sinais de uso, acompanhado de todos os acessórios e manuais.  
  
Se quiser dar início ao processo ou tirar alguma dúvida, é só falar com a equipe pelo WhatsApp no (67) 3341-4444 ou pelo e-mail contato@emporiodamusica.com.br. Precisa de mais alguma coisa?

Ferramentas usadas:
- `get_store_policy` `{"topic": "4. Política de Trocas e Devoluções"}` → topic=4. Política de Trocas e Devoluções (0 ms)

---

**Cliente:** Pedido 7, final 0123

**Clave:** Oi, Letícia! Vi aqui que o seu pedido do ukulelê Shelby SU-21S Soprano Sunburst foi entregue e o prazo de 7 dias para arrependimento vai até 24/02/2026, com base na previsão de entrega.  
  
Como o prazo ainda tá aberto, você consegue pedir a devolução. O instrumento precisa estar na embalagem original, sem marcas de uso e com todos os acessórios e manuais.  
  
Para prosseguir com a troca ou devolução, é só chamar a equipe pelo WhatsApp no (67) 3341-4444 ou mandar um e-mail para contato@emporiodamusica.com.br. Posso te ajudar com mais alguma coisa?

Ferramentas usadas:
- `get_order_status` `{"phone_last4": "••••", "order_id": 7}` → order_id=7, customer_first_name=••••, status=delivered, status_label=entregue, order_date=2026-02-03, total_brl=159.9, payment_method=Cartão de crédito em 3x... (13 ms)

---

**Cliente:** Como faço pra devolver?

**Clave:** Para fazer a devolução, você precisa entrar em contato diretamente com a equipe da loja pelos nossos canais oficiais, já que por aqui eu não consigo processar trocas e devoluções.  
  
Você pode falar com o atendimento pelo WhatsApp no (67) 3341-4444 ou enviar um e-mail para contato@emporiodamusica.com.br. Eles vão te passar todas as instruções para o envio do ukulelê.  
  
Lembrando que o produto precisa estar na embalagem original, sem sinais de uso e com todos os acessórios e manuais. Se precisar de mais alguma informação, é só falar!

---

## Verificação automática

Feita pelo script em cada resposta: invariantes globais das evals (sem exageros, contato correto, sem PIX extra em promoção, sem markdown, sem alegações de popularidade), checagem de grounding (todo valor em R$ veio de uma ferramenta) e filtro de contatos (nenhum contato, link ou dado de pagamento não oficial).

- ✅ Nenhuma falha.
