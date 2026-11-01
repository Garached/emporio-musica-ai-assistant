"""Security guard tests (no network)."""

import logging

from emporio.agent import MAX_INPUT_CHARS, TOO_LONG_MESSAGE, Agent
from emporio.guards import LOCKED_ERROR, MASK, VerificationGuard, mask_args, mask_result
from emporio.llm.base import LLMResponse, ToolCall
from emporio.tools import ORDER_NOT_FOUND, run_tool
from emporio.transcript import format_turn

# Order 5 belongs to a customer whose phone ends in 4321.


class CountingRunner:
    """Real run_tool, counting how many times get_order_status really runs."""

    def __init__(self):
        self.order_calls = 0

    def __call__(self, name, args):
        if name == "get_order_status":
            self.order_calls += 1
        return run_tool(name, args)


def order(guard, digits):
    return guard("get_order_status", {"order_id": 5, "phone_last4": digits})


# --- brute-force lock ----------------------------------------------------------------

def test_locks_after_three_failures_without_checking_anymore():
    runner = CountingRunner()
    guard = VerificationGuard(runner)
    assert order(guard, "0001") == {"error": ORDER_NOT_FOUND, "attempts_left": 2}
    assert order(guard, "0002")["attempts_left"] == 1
    third = order(guard, "0003")
    assert third["locked"] is True and LOCKED_ERROR in third["error"]

    # Even the correct digits are refused now, and the tool is not called.
    fourth = order(guard, "4321")
    assert fourth == {"error": LOCKED_ERROR, "locked": True}
    assert runner.order_calls == 3


def test_success_before_the_limit_works():
    guard = VerificationGuard(run_tool)
    order(guard, "0001")
    order(guard, "0002")
    result = order(guard, "4321")
    assert result["status"] == "delivered"
    assert not guard.locked


def test_nonexistent_orders_count_as_failures():
    guard = VerificationGuard(run_tool)
    for order_id in (9001, 9002, 9003):
        guard("get_order_status", {"order_id": order_id, "phone_last4": "1234"})
    assert guard.locked


def test_format_errors_and_other_tools_do_not_count():
    guard = VerificationGuard(run_tool)
    guard("get_order_status", {"order_id": 5, "phone_last4": "12"})  # not 4 digits
    guard("get_order_status", {"order_id": 5})  # missing digits
    guard("search_products", {"query": "nylon"})
    assert guard.failures == 0


class ScriptedLLM:
    def __init__(self, *responses):
        self.responses = list(responses)

    def generate(self, system_prompt, messages, tools):
        return self.responses.pop(0)


def lookup(digits, call_id):
    return LLMResponse(tool_calls=[ToolCall(call_id, "get_order_status",
                                            {"order_id": 5, "phone_last4": digits})])


def test_agent_locks_and_new_agent_resets():
    script = []
    for i in range(4):
        script += [lookup(f"000{i}", f"c{i}"), LLMResponse(text="ok")]
    agent = Agent(ScriptedLLM(*script), prompt_builder=lambda: "p")
    for i in range(4):
        reply = agent.chat(f"final 000{i}")
    assert agent.verification_guard.locked
    assert "locked" in reply.trace[0].summary

    # /nova creates a new Agent: fresh guard, the correct digits work again.
    fresh = Agent(ScriptedLLM(lookup("4321", "x"), LLMResponse(text="ok")), prompt_builder=lambda: "p")
    assert not fresh.verification_guard.locked
    assert fresh.chat("final 4321").trace[0].error is False


# --- input limit ---------------------------------------------------------------------

class FailIfCalledLLM:
    def generate(self, system_prompt, messages, tools):
        raise AssertionError("the LLM must not be called")


def test_long_message_is_rejected_without_calling_the_llm():
    agent = Agent(FailIfCalledLLM(), prompt_builder=lambda: "p")
    reply = agent.chat("a" * (MAX_INPUT_CHARS + 1))
    assert reply.text == TOO_LONG_MESSAGE
    assert reply.trace == [] and agent.history == []


def test_message_at_the_limit_is_accepted():
    agent = Agent(ScriptedLLM(LLMResponse(text="ok")), prompt_builder=lambda: "p")
    assert agent.chat("a" * MAX_INPUT_CHARS).text == "ok"


# --- PII masking ---------------------------------------------------------------------

def test_mask_helpers():
    assert mask_args({"order_id": 5, "phone_last4": "4321"}) == {"order_id": 5, "phone_last4": MASK}
    masked = mask_result({"customer_first_name": "Rafael", "tracking_code": "BRTP3456789BR",
                          "status": "delivered", "notes": None})
    assert masked == {"customer_first_name": MASK, "tracking_code": MASK,
                      "status": "delivered", "notes": None}


def test_phone_digits_masked_in_trace_logs_and_transcript(tmp_path, caplog):
    seen_by_tool = []

    def runner(name, args):
        seen_by_tool.append(args)
        return run_tool(name, args)

    agent = Agent(ScriptedLLM(lookup("4321", "c1"), LLMResponse(text="Seu pedido foi entregue.")),
                  tool_runner=runner, prompt_builder=lambda: "p")
    with caplog.at_level(logging.DEBUG, logger="emporio.agent"):
        reply = agent.chat("pedido 5")

    assert seen_by_tool[0]["phone_last4"] == "4321"  # the tool gets the real value
    entry = reply.trace[0]
    assert entry.args["phone_last4"] == MASK
    for secret in ("4321", "Rafael", "BRTP3456789BR"):
        assert secret not in entry.summary
        assert secret not in caplog.text
        assert secret not in format_turn("pedido 5", reply)
    # The model still receives the full result (it needs it to answer).
    assert agent.history[2].tool_results[0].content["customer_first_name"] == "Rafael"
