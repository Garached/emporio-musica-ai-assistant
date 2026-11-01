"""The agent loop: LLM <-> tools, built by hand (no agent framework).

One Agent = one conversation. Each user message runs this loop:
call the LLM -> if it asks for tools, run them and send the results back ->
repeat until the LLM answers with plain text (or a safety limit is hit).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from emporio.guards import VerificationGuard, mask_args, mask_result
from emporio.llm.base import LLMClient, Message, ToolCall, ToolResult
from emporio.prompts import build_system_prompt
from emporio.tools import normalize, run_tool, tool_specs

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 6
DEFAULT_MAX_HISTORY = 20
STORE_CONTACT = "(67) 3341-4444 ou contato@emporiodamusica.com.br"

LLM_ERROR_MESSAGE = (
    "Desculpe, estou com uma instabilidade técnica e não consegui responder agora 😕 "
    f"Tente de novo em instantes ou fale com a nossa equipe: {STORE_CONTACT}."
)
# Announce-then-stop safeguard: phrases (normalized, accent-free) that mean "I'm about to check".
ANNOUNCE_PHRASES = (
    "deixa eu ver", "deixe-me ver", "deixe me ver", "vou verificar", "vou consultar", "vou checar",
    "um momento", "so um instante", "so um momento", "ja te falo",
)
NUDGE_MESSAGE = (
    "[Mensagem automática do sistema, não do cliente] Você disse que ia consultar, mas não "
    "chamou nenhuma ferramenta. Chame agora a ferramenta necessária e responda ao cliente "
    "com o resultado, sem anunciar a consulta."
)

MAX_INPUT_CHARS = 2000
TOO_LONG_MESSAGE = (
    "Opa, sua mensagem ficou bem longa 😅 Consegue resumir em até 2.000 caracteres? "
    "Assim eu te ajudo melhor."
)
FALLBACK_MESSAGE = (
    "Desculpe, não consegui concluir essa consulta agora. Pode reformular a pergunta? "
    f"Se preferir, a nossa equipe ajuda você: {STORE_CONTACT}."
)


@dataclass(frozen=True)
class ToolTrace:
    """What happened in one tool call (for debugging and the CLI debug mode).

    `kind` is "tool" for real tool calls and "nudge" for the announce-then-stop
    safeguard (see Agent._should_nudge); nudges are not tool calls.
    """

    name: str
    args: dict[str, Any]
    summary: str
    duration_ms: float
    error: bool = False
    kind: str = "tool"


@dataclass(frozen=True)
class AgentReply:
    """The agent's answer to one user message, plus the tools it used."""

    text: str
    trace: list[ToolTrace] = field(default_factory=list)


def summarize_result(result: dict[str, Any], max_len: int = 160) -> str:
    """Short, human-readable summary of a tool result."""
    if "error" in result:
        prefix = "error (locked)" if result.get("locked") else "error"
        return f"{prefix}: {result['error']}"[:max_len]
    parts = []
    for key, value in result.items():
        if isinstance(value, list):
            parts.append(f"{key}={len(value)} items")
        elif isinstance(value, (int, float, bool)) or (isinstance(value, str) and len(value) <= 40):
            parts.append(f"{key}={value}")
    summary = ", ".join(parts) or json.dumps(result, ensure_ascii=False)
    return summary if len(summary) <= max_len else summary[: max_len - 3] + "..."


def trim_history(messages: list[Message], max_messages: int) -> list[Message]:
    """Keep about the last `max_messages`, always starting at a user message.

    Starting at a user message guarantees we never separate an assistant tool
    call from its tool result. If the current turn alone is longer than the
    limit, the whole turn is kept.
    """
    if len(messages) <= max_messages:
        return messages
    for i in range(len(messages) - max_messages, len(messages)):
        if messages[i].role == "user":
            return messages[i:]
    user_indexes = [i for i, m in enumerate(messages) if m.role == "user"]
    return messages[user_indexes[-1]:] if user_indexes else messages


class Agent:
    """A customer service conversation driven by an LLM with tools."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        max_history: int = DEFAULT_MAX_HISTORY,
        tools: list[dict[str, Any]] | None = None,
        tool_runner: Callable[[str, dict[str, Any]], dict[str, Any]] = run_tool,
        prompt_builder: Callable[[], str] = build_system_prompt,
    ) -> None:
        self.llm = llm
        self.max_iterations = max_iterations
        self.max_history = max_history
        self.tools = tools if tools is not None else tool_specs()
        # One guard per conversation: order lookups lock after repeated failed verifications.
        self.verification_guard = VerificationGuard(tool_runner)
        self._run_tool = self.verification_guard
        self._build_prompt = prompt_builder
        self.history: list[Message] = []

    def chat(self, user_message: str) -> AgentReply:
        """Answer one user message, running tools as the LLM requests them."""
        if len(user_message) > MAX_INPUT_CHARS:
            # Rejected before the LLM: limits cost and the room for prompt-injection payloads.
            logger.warning("Rejected message with %d chars (max %d)", len(user_message), MAX_INPUT_CHARS)
            return AgentReply(TOO_LONG_MESSAGE)
        user_msg = Message.user(user_message)
        self.history.append(user_msg)
        trace: list[ToolTrace] = []

        for _ in range(self.max_iterations):
            self.history = trim_history(self.history, self.max_history)
            try:
                # Rebuilt every call: date, time and open/closed status can change.
                response = self.llm.generate(self._build_prompt(), self.history, self.tools)
            except Exception as exc:
                # Traceback only at DEBUG level, so the chat UI stays clean.
                logger.error("LLM call failed: %s", exc, exc_info=logger.isEnabledFor(logging.DEBUG))
                self._drop_turn(user_msg)
                return AgentReply(LLM_ERROR_MESSAGE, trace)

            self.history.append(Message.assistant(response))
            if not response.tool_calls:
                text = (response.text or "").strip()
                if self._should_nudge(text, trace):
                    self._nudge(trace)
                    continue  # counts toward max_iterations
                return AgentReply(text or FALLBACK_MESSAGE, trace)

            results = [self._execute(call, trace) for call in response.tool_calls]
            self.history.append(Message.tool(results))

        logger.warning("Max iterations (%d) reached", self.max_iterations)
        self.history.append(Message.assistant_text(FALLBACK_MESSAGE))
        return AgentReply(FALLBACK_MESSAGE, trace)

    def _should_nudge(self, text: str, trace: list[ToolTrace]) -> bool:
        """Announce-then-stop safeguard (heuristic).

        True when the model answered with plain text that only announces a check
        ("deixe-me ver...", "vou verificar...") while no tool has run in this turn,
        and we haven't nudged yet. It's a phrase list, so it can miss other wordings
        or, rarely, nudge a reply that didn't need it.
        """
        if any(t.kind == "nudge" for t in trace) or any(t.kind == "tool" for t in trace):
            return False
        normalized = normalize(text)
        return any(phrase in normalized for phrase in ANNOUNCE_PHRASES)

    def _nudge(self, trace: list[ToolTrace]) -> None:
        """Ask the model once to actually call the tool; the customer never sees this."""
        self.history.append(Message.user(NUDGE_MESSAGE))
        trace.append(ToolTrace("nudge", {}, "announced a check without calling a tool; asked to call it now",
                               0.0, kind="nudge"))
        logger.debug("nudge: model announced a check without calling a tool")

    def _drop_turn(self, user_msg: Message) -> None:
        """Remove an unfinished turn so the next message starts from a clean history."""
        for i in range(len(self.history) - 1, -1, -1):
            if self.history[i] is user_msg:
                self.history = self.history[:i]
                return

    def _execute(self, call: ToolCall, trace: list[ToolTrace]) -> ToolResult:
        """Run one tool call, record it in the trace and log it.

        The tool gets the real args; the trace and logs get masked copies (LGPD),
        since they end up in debug output, transcripts and eval reports.
        """
        start = time.perf_counter()
        result = self._run_tool(call.name, call.args)
        duration_ms = (time.perf_counter() - start) * 1000
        entry = ToolTrace(call.name, mask_args(call.args), summarize_result(mask_result(result)),
                          duration_ms, "error" in result)
        trace.append(entry)
        logger.debug("tool %s args=%s -> %s (%.0f ms)", entry.name, entry.args, entry.summary, duration_ms)
        return ToolResult(call_id=call.id, name=call.name, content=result)
