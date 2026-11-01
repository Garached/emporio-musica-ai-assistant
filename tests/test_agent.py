"""Agent loop tests with a scripted FAKE LLM client (no network, no API key)."""

import os

import pytest

from emporio.agent import (
    FALLBACK_MESSAGE,
    LLM_ERROR_MESSAGE,
    Agent,
    summarize_result,
    trim_history,
)
from emporio.llm.base import LLMError, LLMResponse, Message, ToolCall, ToolResult


class FakeLLM:
    """Returns scripted responses (or raises scripted exceptions) in order."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []  # history snapshot sent on each call

    def generate(self, system_prompt, messages, tools):
        self.calls.append(list(messages))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def call(name, args, call_id="c1"):
    return ToolCall(id=call_id, name=name, args=args)


def make_agent(llm, **kwargs):
    return Agent(llm, prompt_builder=lambda: "system prompt", **kwargs)


def test_plain_text_reply_without_tools():
    agent = make_agent(FakeLLM(LLMResponse(text="Oi! Sou a Clave.")))
    reply = agent.chat("Oi")
    assert reply.text == "Oi! Sou a Clave."
    assert reply.trace == []
    assert [m.role for m in agent.history] == ["user", "assistant"]


def test_one_tool_call_then_final_answer():
    llm = FakeLLM(
        LLMResponse(tool_calls=[call("search_products", {"query": "takamine gd20"})]),
        LLMResponse(text="Sai por R$ 2.199,00."),
    )
    reply = make_agent(llm).chat("Quanto custa o Takamine GD20?")
    assert reply.text == "Sai por R$ 2.199,00."
    assert [t.name for t in reply.trace] == ["search_products"]
    assert "total_found=1" in reply.trace[0].summary
    # The tool result was sent back to the model on the second call.
    tool_msg = llm.calls[1][-1]
    assert tool_msg.role == "tool"
    assert tool_msg.tool_results[0].content["results"][0]["price"] == 2199.0


def test_several_tool_calls_in_one_response_are_all_executed():
    llm = FakeLLM(
        LLMResponse(tool_calls=[
            call("list_active_promotions", {}, "a"),
            call("get_store_hours_status", {}, "b"),
        ]),
        LLMResponse(text="Pronto!"),
    )
    reply = make_agent(llm).chat("Promoções e horário?")
    assert [t.name for t in reply.trace] == ["list_active_promotions", "get_store_hours_status"]
    results = llm.calls[1][-1].tool_results
    assert [r.call_id for r in results] == ["a", "b"]


def test_tool_error_is_passed_back_to_the_model():
    llm = FakeLLM(
        LLMResponse(tool_calls=[call("get_product_details", {"product_id": 9999})]),
        LLMResponse(text="Não encontrei esse produto."),
    )
    reply = make_agent(llm).chat("Produto 9999?")
    assert reply.text == "Não encontrei esse produto."
    assert reply.trace[0].error is True
    assert "error" in llm.calls[1][-1].tool_results[0].content


def test_unknown_tool_does_not_crash():
    llm = FakeLLM(LLMResponse(tool_calls=[call("hack_the_store", {})]), LLMResponse(text="Ok"))
    reply = make_agent(llm).chat("?")
    assert reply.text == "Ok" and reply.trace[0].error


def test_iteration_limit_returns_fallback():
    looping = [LLMResponse(tool_calls=[call("get_store_hours_status", {}, f"c{i}")]) for i in range(6)]
    llm = FakeLLM(*looping)
    agent = make_agent(llm)
    reply = agent.chat("loop")
    assert reply.text == FALLBACK_MESSAGE
    assert len(llm.calls) == 6
    assert len(reply.trace) == 6
    assert agent.history[-1].role == "assistant"  # history stays well-formed


def test_llm_failure_returns_friendly_error_and_cleans_history():
    llm = FakeLLM(LLMResponse(text="Oi!"), LLMError("503 after retries"))
    agent = make_agent(llm)
    agent.chat("Oi")
    reply = agent.chat("Quanto custa?")
    assert reply.text == LLM_ERROR_MESSAGE
    assert "(67) 3341-4444" in reply.text
    assert [m.role for m in agent.history] == ["user", "assistant"]  # failed turn removed


def test_empty_model_response_returns_fallback():
    reply = make_agent(FakeLLM(LLMResponse(text=None))).chat("Oi")
    assert reply.text == FALLBACK_MESSAGE


def test_system_prompt_is_rebuilt_every_call():
    builds = []
    llm = FakeLLM(
        LLMResponse(tool_calls=[call("get_store_hours_status", {})]),
        LLMResponse(text="Ok"),
    )
    agent = Agent(llm, prompt_builder=lambda: builds.append(1) or "p")
    agent.chat("Está aberto?")
    assert len(builds) == 2


# --- history trimming --------------------------------------------------------------

def _turn_with_tool(i):
    return [
        Message.user(f"q{i}"),
        Message.assistant(LLMResponse(tool_calls=[call("search_products", {}, f"t{i}")])),
        Message.tool([ToolResult(f"t{i}", "search_products", {"total_found": 0})]),
        Message.assistant_text(f"a{i}"),
    ]


@pytest.mark.parametrize("max_messages", range(1, 14))
def test_trimming_never_separates_tool_call_from_result(max_messages):
    history = [m for i in range(4) for m in _turn_with_tool(i)]
    trimmed = trim_history(history, max_messages)
    assert trimmed[0].role == "user"
    for i, msg in enumerate(trimmed):
        if msg.role == "tool":
            assert trimmed[i - 1].tool_calls  # its call is right before it
        if msg.tool_calls:
            assert trimmed[i + 1].role == "tool"


def test_trimming_keeps_short_history_untouched():
    history = _turn_with_tool(0)
    assert trim_history(history, 20) is history


def test_agent_trims_long_conversations():
    replies = [LLMResponse(text=f"r{i}") for i in range(15)]
    agent = make_agent(FakeLLM(*replies), max_history=6)
    for i in range(15):
        agent.chat(f"m{i}")
    assert len(agent.history) <= 7
    assert agent.history[0].role == "user"


def test_summarize_result():
    assert summarize_result({"error": "not found"}) == "error: not found"
    assert summarize_result({"total_found": 3, "results": [1, 2, 3]}) == "total_found=3, results=3 items"


# --- optional real API test ----------------------------------------------------------

@pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="set RUN_INTEGRATION=1 to call Gemini")
def test_real_gemini_answers_a_price_question():
    from emporio.config import load_settings
    from emporio.llm.gemini import GeminiClient

    agent = Agent(GeminiClient.from_settings(load_settings()))
    reply = agent.chat("Quanto custa o Takamine GD20?")
    assert any(t.name in ("search_products", "get_product_details") for t in reply.trace)
    assert "2.199" in reply.text or "2199" in reply.text
