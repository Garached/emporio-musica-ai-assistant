"""Provider-neutral LLM types and the client interface.

The agent only talks to these types. Supporting another provider means writing a
new class that implements `LLMClient`; the agent does not change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, Sequence

Role = Literal["user", "assistant", "tool"]


class LLMError(Exception):
    """The LLM call failed (after retries, or with a non-retryable error)."""


@dataclass(frozen=True)
class ToolCall:
    """A tool the model asked us to run."""

    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """The result of running a ToolCall, sent back to the model."""

    call_id: str
    name: str
    content: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    """One model response: text and/or tool calls.

    `raw` is the provider's original content, kept so it can be replayed
    unchanged (e.g. Gemini thought signatures). Only the provider client reads it.
    """

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None


@dataclass(frozen=True)
class Message:
    """One entry of the conversation history.

    - user: `text` from the customer.
    - assistant: model `text` and/or `tool_calls`, plus the opaque `raw` content.
    - tool: `tool_results` for the previous assistant tool calls.
    """

    role: Role
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    raw: Any = None

    @classmethod
    def user(cls, text: str) -> Message:
        return cls(role="user", text=text)

    @classmethod
    def assistant(cls, response: LLMResponse) -> Message:
        return cls(role="assistant", text=response.text,
                   tool_calls=list(response.tool_calls), raw=response.raw)

    @classmethod
    def assistant_text(cls, text: str) -> Message:
        return cls(role="assistant", text=text)

    @classmethod
    def tool(cls, results: list[ToolResult]) -> Message:
        return cls(role="tool", tool_results=results)


class LLMClient(Protocol):
    """Anything that can generate a response from a system prompt, history and tools.

    `tools` are provider-agnostic specs: {"name", "description", "parameters"}
    where `parameters` is a JSON Schema object (see emporio.tools.tool_specs).
    Implementations raise LLMError when the call fails.
    """

    def generate(
        self, system_prompt: str, messages: Sequence[Message], tools: Sequence[dict[str, Any]]
    ) -> LLMResponse: ...
