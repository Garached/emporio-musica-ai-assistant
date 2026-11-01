"""Announce-then-stop safeguard: one nudge when the model promises a check but calls no tool."""

from emporio.agent import FALLBACK_MESSAGE, NUDGE_MESSAGE, Agent, ToolTrace
from emporio.llm.base import LLMResponse, ToolCall
from emporio.transcript import format_turn
from evals.checks import run_check


class FakeLLM:
    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def generate(self, system_prompt, messages, tools):
        self.calls.append(list(messages))
        return self.script.pop(0)


ANNOUNCE = LLMResponse(text="Olá! Deixe-me ver quais promoções estão ativas na loja neste momento.")
PROMOS = LLMResponse(tool_calls=[ToolCall("c1", "list_active_promotions", {})])
FINAL = LLMResponse(text="Temos o Ohana CK-20 de R$ 549,00 por R$ 439,20 (20% de desconto).")


def make_agent(*script, **kwargs):
    llm = FakeLLM(*script)
    return Agent(llm, prompt_builder=lambda: "p", **kwargs), llm


def test_announce_then_nudge_then_tool_then_answer():
    agent, llm = make_agent(ANNOUNCE, PROMOS, FINAL)
    reply = agent.chat("Tem alguma promoção?")
    assert reply.text == FINAL.text  # the customer only sees the final answer
    assert [t.kind for t in reply.trace] == ["nudge", "tool"]
    assert reply.trace[1].name == "list_active_promotions"
    assert len(llm.calls) == 3
    nudge_msg = llm.calls[1][-1]
    assert nudge_msg.role == "user" and nudge_msg.text == NUDGE_MESSAGE


def test_nudge_happens_only_once_per_turn():
    agent, llm = make_agent(ANNOUNCE, ANNOUNCE)
    reply = agent.chat("Tem alguma promoção?")
    assert reply.text == ANNOUNCE.text  # second announcement is returned as-is
    assert [t.kind for t in reply.trace] == ["nudge"]
    assert len(llm.calls) == 2


def test_nudge_resets_on_the_next_turn():
    agent, _ = make_agent(ANNOUNCE, PROMOS, FINAL, ANNOUNCE, PROMOS, FINAL)
    agent.chat("Tem alguma promoção?")
    second = agent.chat("E agora?")
    assert [t.kind for t in second.trace] == ["nudge", "tool"]


def test_normal_answer_gets_no_nudge():
    agent, llm = make_agent(LLMResponse(text="Oi! Sou a Clave. Como posso ajudar?"))
    reply = agent.chat("Oi")
    assert reply.trace == [] and len(llm.calls) == 1


def test_no_nudge_after_a_tool_already_ran_in_the_turn():
    closing = LLMResponse(text="Um momento de atenção: os preços acima já incluem a promoção.")
    agent, llm = make_agent(PROMOS, closing)
    reply = agent.chat("Promoções?")
    assert reply.text == closing.text
    assert [t.kind for t in reply.trace] == ["tool"]


def test_accent_insensitive_match():
    agent, llm = make_agent(LLMResponse(text="Só um instante que eu confiro!"), PROMOS, FINAL)
    assert agent.chat("Promoções?").text == FINAL.text


def test_nudge_counts_toward_the_iteration_limit():
    agent, llm = make_agent(ANNOUNCE, PROMOS, max_iterations=2)
    reply = agent.chat("Tem alguma promoção?")
    assert reply.text == FALLBACK_MESSAGE
    assert len(llm.calls) == 2


def test_nudge_is_not_a_tool_for_eval_checks_and_shows_in_transcript():
    trace = [ToolTrace("nudge", {}, "asked to call a tool", 0.0, kind="nudge")]
    assert run_check({"type": "tool_not_called", "tool": "*"}, "ok", trace).status == "PASS"
    assert run_check({"type": "tool_called", "tool": "nudge"}, "ok", trace).status == "FAIL"
    from emporio.agent import AgentReply
    assert "- _nudge_: asked to call a tool" in format_turn("x", AgentReply("ok", trace))


def test_dar_uma_olhada_is_nudged_and_algum_momento_is_not():
    peek = LLMResponse(text="Deixa eu dar uma olhada nas promoções pra você!")
    agent, _ = make_agent(peek, PROMOS, FINAL)
    assert [t.kind for t in agent.chat("Promoções?").trace] == ["nudge", "tool"]
    calm = LLMResponse(text="Em algum momento passe na loja para testar os instrumentos.")
    agent2, llm2 = make_agent(calm)
    assert agent2.chat("Oi").trace == [] and len(llm2.calls) == 1
