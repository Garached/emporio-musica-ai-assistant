"""Offline tests for the Gemini client: conversions, signature replay and retries."""

import httpx
import pytest
from google.genai import errors, types

from emporio.llm.base import LLMError, LLMResponse, Message, ToolCall, ToolResult
from emporio.llm.gemini import (
    GeminiClient,
    parse_response,
    suggested_retry_delay,
    to_gemini_content,
    to_gemini_tool,
)
from emporio.tools import tool_specs


class FakeModels:
    def __init__(self, *script, thinking=True):
        self.script = list(script)
        self.thinking = thinking
        self.configs = []

    def get(self, model):
        return types.Model(name=model, thinking=self.thinking)

    def generate_content(self, model, contents, config):
        self.configs.append(config)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeGenaiClient:
    def __init__(self, models):
        self.models = models


def text_response(text):
    content = types.Content(role="model", parts=[types.Part(text=text)])
    return types.GenerateContentResponse(candidates=[types.Candidate(content=content)])


def api_error(code, retry_delay=None):
    details = []
    if retry_delay:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay})
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, {"error": {"code": code, "message": "x", "details": details}})


def make_client(models, sleeps):
    return GeminiClient("key", "gemini-test", client=FakeGenaiClient(models), sleep=sleeps.append)


# --- conversions -----------------------------------------------------------------

def test_tool_specs_become_function_declarations():
    tool = to_gemini_tool(tool_specs())
    names = [d.name for d in tool.function_declarations]
    assert names == [s["name"] for s in tool_specs()]
    search = tool.function_declarations[0]
    assert "category" in search.parameters_json_schema["properties"]


def test_raw_model_content_is_replayed_unchanged():
    raw = types.Content(role="model", parts=[types.Part(
        function_call=types.FunctionCall(name="search_products", args={"query": "x"}),
        thought_signature=b"secret-signature",
    )])
    parsed = parse_response(types.GenerateContentResponse(candidates=[types.Candidate(content=raw)]))
    message = Message.assistant(parsed)
    assert to_gemini_content(message) is raw
    assert parsed.tool_calls[0].name == "search_products"


def test_tool_results_become_function_responses():
    msg = Message.tool([ToolResult("abc", "search_products", {"total_found": 0})])
    part = to_gemini_content(msg).parts[0]
    assert part.function_response.name == "search_products"
    assert part.function_response.id == "abc"
    assert part.function_response.response == {"total_found": 0}


def test_thought_parts_are_not_shown_as_text():
    content = types.Content(role="model", parts=[
        types.Part(text="internal reasoning", thought=True),
        types.Part(text="Olá!"),
    ])
    parsed = parse_response(types.GenerateContentResponse(candidates=[types.Candidate(content=content)]))
    assert parsed.text == "Olá!"


def test_assistant_without_raw_is_rebuilt():
    msg = Message.assistant(LLMResponse(tool_calls=[ToolCall("local-1", "get_store_hours_status", {})]))
    content = to_gemini_content(msg)
    assert content.role == "model"
    assert content.parts[0].function_call.id is None  # local ids are not sent to Gemini


# --- config ------------------------------------------------------------------------

def test_config_disables_afc_and_sets_thinking_when_supported():
    models = FakeModels(text_response("oi"), thinking=True)
    make_client(models, []).generate("sys", [Message.user("oi")], tool_specs())
    config = models.configs[0]
    assert config.automatic_function_calling.disable is True
    assert config.temperature == 0.3
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW


def test_thinking_not_sent_when_unsupported():
    models = FakeModels(text_response("oi"), thinking=False)
    make_client(models, []).generate("sys", [Message.user("oi")], tool_specs())
    assert models.configs[0].thinking_config is None


# --- retries -----------------------------------------------------------------------

def test_retries_429_honoring_suggested_delay():
    sleeps = []
    models = FakeModels(api_error(429, "7s"), text_response("ok"))
    result = make_client(models, sleeps).generate("sys", [Message.user("oi")], [])
    assert result.text == "ok"
    assert sleeps == [7.0]


def test_retries_504_and_timeouts_with_backoff():
    sleeps = []
    models = FakeModels(api_error(504), httpx.ReadTimeout("slow"), text_response("ok"))
    result = make_client(models, sleeps).generate("sys", [Message.user("oi")], [])
    assert result.text == "ok"
    assert sleeps == [2.0, 4.0]


def test_gives_up_after_max_retries():
    sleeps = []
    models = FakeModels(*[api_error(503) for _ in range(4)])
    with pytest.raises(LLMError):
        make_client(models, sleeps).generate("sys", [Message.user("oi")], [])
    assert len(sleeps) == 3


def test_client_errors_are_not_retried():
    sleeps = []
    with pytest.raises(LLMError):
        make_client(FakeModels(api_error(400)), sleeps).generate("sys", [Message.user("oi")], [])
    assert sleeps == []


def test_exhausted_quota_with_long_delay_is_not_retried():
    sleeps = []
    with pytest.raises(LLMError):
        make_client(FakeModels(api_error(429, "3600s")), sleeps).generate("sys", [Message.user("oi")], [])
    assert sleeps == []


def test_suggested_retry_delay_parsing():
    assert suggested_retry_delay(api_error(429, "33s")) == 33.0
    assert suggested_retry_delay(api_error(429)) is None
