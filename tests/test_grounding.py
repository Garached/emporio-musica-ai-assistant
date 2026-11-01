"""Output grounding (R$ values must come from tools) and the empty-response retry."""

from emporio.agent import FALLBACK_MESSAGE, Agent
from emporio.grounding import numbers_in_result, numbers_in_text, prices_in, ungrounded_values
from emporio.guards import MASK
from emporio.llm.base import LLMResponse, ToolCall
from emporio.transcript import format_turn


class FakeLLM:
    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def generate(self, system_prompt, messages, tools):
        self.calls.append(list(messages))
        return self.script.pop(0)


def make_agent(*script):
    llm = FakeLLM(*script)
    return Agent(llm, prompt_builder=lambda: "p"), llm


SEARCH_GD20 = LLMResponse(tool_calls=[ToolCall("c1", "search_products", {"query": "takamine gd20"})])
GROUNDED = LLMResponse(text="O Takamine GD20 sai por R$ 2.199,00 ou R$ 2.089,05 no PIX.")
INVENTED = LLMResponse(text="Temos o Giannini Cerrado por R$ 428,00 e o SF 14 por R$ 513,00.")


# --- helpers ---------------------------------------------------------------------------

def test_parsing_helpers():
    assert prices_in("R$ 1.299,00, R$1000 e R$ 99,98") == [1299.0, 1000.0, 99.98]
    assert numbers_in_text("até R$1000, pedido 8") == [1000.0, 8.0]
    result = {"price": 599.9, "in_stock": True, "options": [{"value": 99.98}],
              "text": "Frete grátis acima de R$ 500,00."}
    assert sorted(numbers_in_result(result)) == [99.98, 500.0, 599.9]  # booleans ignored


def test_tolerance_is_one_cent():
    assert ungrounded_values("R$ 99,99", [99.98]) == []
    assert ungrounded_values("R$ 100,00", [99.98]) == [100.0]


# --- agent behavior ------------------------------------------------------------------------

def test_grounded_prices_pass_without_nudge():
    agent, llm = make_agent(SEARCH_GD20, GROUNDED)
    reply = agent.chat("Quanto custa o Takamine GD20?")
    assert reply.text == GROUNDED.text
    assert [t.kind for t in reply.trace] == ["tool"]


def test_invented_price_gets_one_nudge_then_grounded_answer():
    agent, llm = make_agent(INVENTED, SEARCH_GD20, GROUNDED)
    reply = agent.chat("Quais violões vocês têm?")
    assert reply.text == GROUNDED.text
    assert [t.kind for t in reply.trace] == ["grounding", "tool"]
    nudge = llm.calls[1][-1]
    assert nudge.role == "user" and "R$ 428,00" in nudge.text and "R$ 513,00" in nudge.text


def test_still_invented_after_nudge_returns_fallback():
    agent, llm = make_agent(INVENTED, INVENTED)
    reply = agent.chat("Quais violões vocês têm?")
    assert reply.text == FALLBACK_MESSAGE
    assert "428" not in reply.text
    assert agent.history[-1].text == FALLBACK_MESSAGE  # the invented reply is not kept


def test_self_computed_values_are_blocked():
    savings = LLMResponse(text="Sai por R$ 2.199,00 e você economiza R$ 109,95 no PIX!")
    agent, _ = make_agent(SEARCH_GD20, savings, SEARCH_GD20, GROUNDED)
    reply = agent.chat("Quanto custa o Takamine GD20?")
    assert reply.text == GROUNDED.text
    assert "grounding" in [t.kind for t in reply.trace]


def test_prices_from_an_earlier_turn_count_as_grounded():
    agent, llm = make_agent(SEARCH_GD20, GROUNDED, LLMResponse(text="No PIX fica R$ 2.089,05."))
    agent.chat("Quanto custa o Takamine GD20?")
    reply = agent.chat("E no PIX?")
    assert reply.text == "No PIX fica R$ 2.089,05." and reply.trace == []


def test_values_said_by_the_customer_count_as_grounded():
    agent, _ = make_agent(LLMResponse(text="Beleza, vou buscar opções até R$ 1.000 pra você."))
    reply = agent.chat("Quero um violão até R$1000")
    assert "R$ 1.000" in reply.text and reply.trace == []


def test_reply_without_prices_is_not_checked():
    agent, _ = make_agent(LLMResponse(text="Oi! Sou a Clave, como posso ajudar?"))
    assert agent.chat("Oi").trace == []


# --- empty response retry ------------------------------------------------------------------

def test_empty_response_is_retried_once():
    agent, llm = make_agent(LLMResponse(text=None), LLMResponse(text="Oi! Como posso ajudar?"))
    reply = agent.chat("Oi")
    assert reply.text == "Oi! Como posso ajudar?"
    assert [t.kind for t in reply.trace] == ["retry"]
    assert len(llm.calls) == 2
    assert all(m.text for m in agent.history if m.role == "assistant")  # empty message dropped


# --- rejected drafts are kept (masked) for debugging -------------------------------------

def test_grounding_nudge_keeps_rejected_draft():
    agent, _ = make_agent(INVENTED, SEARCH_GD20, GROUNDED)
    reply = agent.chat("Quais violões vocês têm?")
    nudge = reply.trace[0]
    assert nudge.kind == "grounding" and nudge.rejected_draft == INVENTED.text
    assert reply.trace[1].rejected_draft is None  # real tool calls have no draft


def test_blocked_reply_is_recorded_with_its_draft():
    agent, _ = make_agent(INVENTED, LLMResponse(text="Então fica R$ 777,00."))
    reply = agent.chat("Quais violões vocês têm?")
    assert [t.kind for t in reply.trace] == ["grounding", "blocked"]
    assert reply.trace[1].rejected_draft == "Então fica R$ 777,00."


def test_rejected_drafts_are_masked():
    lookup = LLMResponse(tool_calls=[ToolCall("o1", "get_order_status", {"order_id": 5, "phone_last4": "4321"})])
    leaky = LLMResponse(text="Oi Rafael (final 4321)! Rastreio BRTP3456789BR, total R$ 999,00.")
    ok = LLMResponse(text="Oi! Seu pedido foi entregue. Total: R$ 4.599,00.")
    agent, _ = make_agent(lookup, leaky, ok)
    reply = agent.chat("Pedido 5, final 4321")
    draft = next(t for t in reply.trace if t.kind == "grounding").rejected_draft
    for secret in ("Rafael", "4321", "BRTP3456789BR"):
        assert secret not in draft
    assert draft.count(MASK) == 3 and "R$ 999,00" in draft
    assert "rejected draft: «" in format_turn("Pedido 5", reply)
    assert "Rafael" not in format_turn("Pedido 5", reply)
