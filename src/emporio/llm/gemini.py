"""Google Gemini implementation of LLMClient (official google-genai SDK)."""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any, Callable, Sequence

import httpx
from google import genai
from google.genai import errors, types

from emporio.config import Settings
from emporio.llm.base import LLMError, LLMResponse, Message, ToolCall

logger = logging.getLogger(__name__)

LOCAL_ID_PREFIX = "local-"  # ids we invent when Gemini does not send one


class GeminiClient:
    """LLMClient backed by Gemini `generateContent` with manual function calling.

    Why generateContent: Google now recommends the stateful Interactions API, but
    generateContent is still fully supported and is stateless. That fits our
    provider abstraction: the Agent owns the conversation history and sends it on
    every call, so swapping providers only needs a new client class.

    Model choice (changed during development):
    - gemini-2.5-flash is no longer available to new users.
    - gemini-3.8-flash returned repeated 504 DEADLINE_EXCEEDED errors on the free
      tier (a known capacity issue).
    - gemini-3.5-flash-lite works reliably on the free tier, so it is the default.
      The model stays configurable (GEMINI_MODEL); gemini-3.8-flash is fine on a
      paid tier.

    Behavior:
    - Automatic function calling is disabled: our agent loop runs the tools.
    - Thought signatures: Gemini 2.5/3.x models may attach signatures to function
      calls that must be sent back unchanged. The raw model `Content` is stored in
      `LLMResponse.raw` / `Message.raw` and replayed as-is.
    - Thinking level is sent only if the model supports thinking.
    - Requests time out after 60s. 429, timeouts and 5xx are retried with
      exponential backoff, honoring the API's suggested retry delay.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        thinking_level: str | None = "low",
        temperature: float = 0.3,
        timeout_s: float = 60.0,
        max_retries: int = 3,
        base_delay_s: float = 2.0,
        max_delay_s: float = 60.0,
        client: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self.thinking_level = thinking_level
        self.temperature = temperature
        self.max_retries = max_retries
        self.base_delay_s = base_delay_s
        self.max_delay_s = max_delay_s
        self._sleep = sleep
        self._client = client or genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000))
        )
        self._thinking_supported: bool | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> GeminiClient:
        """Build a client from the app settings."""
        return cls(settings.gemini_api_key, settings.gemini_model,
                   thinking_level=settings.gemini_thinking_level)

    # --- public API ---------------------------------------------------------------

    def generate(
        self, system_prompt: str, messages: Sequence[Message], tools: Sequence[dict[str, Any]]
    ) -> LLMResponse:
        """Send the conversation to Gemini and return a neutral LLMResponse."""
        contents = [to_gemini_content(m) for m in messages]
        config = self._config(system_prompt, tools)
        response = self._call_with_retry(contents, config)
        return parse_response(response)

    # --- request building ---------------------------------------------------------

    def _config(self, system_prompt: str, tools: Sequence[dict[str, Any]]) -> types.GenerateContentConfig:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=self.temperature,
            tools=[to_gemini_tool(tools)] if tools else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        if self.thinking_level and self._supports_thinking():
            config.thinking_config = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel(self.thinking_level.upper())
            )
        return config

    def _supports_thinking(self) -> bool:
        """Ask the API once whether the model supports thinking (cached)."""
        if self._thinking_supported is None:
            try:
                info = self._client.models.get(model=self.model)
                self._thinking_supported = bool(getattr(info, "thinking", False))
            except Exception as exc:  # metadata lookup is best-effort
                logger.warning("Could not check thinking support for %s: %s", self.model, exc)
                self._thinking_supported = False
            logger.debug("Model %s thinking supported: %s", self.model, self._thinking_supported)
        return self._thinking_supported

    # --- retries ------------------------------------------------------------------

    def _call_with_retry(self, contents: list[types.Content], config: types.GenerateContentConfig) -> Any:
        for attempt in range(self.max_retries + 1):
            try:
                return self._client.models.generate_content(
                    model=self.model, contents=contents, config=config)
            except Exception as exc:
                delay = self._retry_delay(exc, attempt)
                if delay is None or attempt == self.max_retries:
                    raise LLMError(f"Gemini request failed: {exc}") from exc
                logger.warning("Gemini call failed (%s); retry %d/%d in %.1fs",
                               type(exc).__name__, attempt + 1, self.max_retries, delay)
                self._sleep(delay)
        raise LLMError("unreachable")  # pragma: no cover

    def _retry_delay(self, exc: Exception, attempt: int) -> float | None:
        """Seconds to wait before retrying, or None if the error is not retryable."""
        if isinstance(exc, httpx.TransportError):  # timeouts, connection drops
            return self._backoff(attempt)
        if not isinstance(exc, errors.APIError):
            return None
        if exc.code == 429 or (exc.code or 0) >= 500:
            suggested = suggested_retry_delay(exc)
            if suggested is not None:
                # A very long suggested wait means the quota is exhausted (e.g. daily limit).
                return suggested if suggested <= self.max_delay_s else None
            return self._backoff(attempt)
        return None

    def _backoff(self, attempt: int) -> float:
        return min(self.base_delay_s * 2**attempt, self.max_delay_s)


# --- conversions (module-level so they are easy to test) ---------------------------

def to_gemini_tool(specs: Sequence[dict[str, Any]]) -> types.Tool:
    """Convert our JSON Schema tool specs into one Gemini Tool with function declarations."""
    declarations = []
    for spec in specs:
        params = spec.get("parameters") or {}
        declarations.append(types.FunctionDeclaration(
            name=spec["name"],
            description=spec["description"],
            parameters_json_schema=params if params.get("properties") else None,
        ))
    return types.Tool(function_declarations=declarations)


def to_gemini_content(message: Message) -> types.Content:
    """Convert a neutral Message into Gemini Content."""
    if message.role == "user":
        return types.Content(role="user", parts=[types.Part(text=message.text or "")])
    if message.role == "assistant":
        if isinstance(message.raw, types.Content):
            return message.raw  # replay unchanged: keeps thought signatures
        parts = [types.Part(text=message.text)] if message.text else []
        parts += [types.Part(function_call=types.FunctionCall(
            id=_gemini_id(c.id), name=c.name, args=c.args)) for c in message.tool_calls]
        return types.Content(role="model", parts=parts or [types.Part(text="")])
    parts = [types.Part(function_response=types.FunctionResponse(
        id=_gemini_id(r.call_id), name=r.name, response=r.content)) for r in message.tool_results]
    return types.Content(role="user", parts=parts)


def parse_response(response: Any) -> LLMResponse:
    """Extract visible text and function calls; keep the raw Content for replay."""
    candidates = getattr(response, "candidates", None) or []
    content = candidates[0].content if candidates else None
    if content is None or not content.parts:
        return LLMResponse(text=None, tool_calls=[], raw=content)
    texts, calls = [], []
    for part in content.parts:
        if part.function_call is not None:
            fc = part.function_call
            calls.append(ToolCall(id=fc.id or f"{LOCAL_ID_PREFIX}{uuid.uuid4().hex[:8]}",
                                  name=fc.name, args=dict(fc.args or {})))
        elif part.text and not part.thought:
            texts.append(part.text)
    return LLMResponse(text="".join(texts) or None, tool_calls=calls, raw=content)


def suggested_retry_delay(exc: errors.APIError) -> float | None:
    """Read google.rpc.RetryInfo.retryDelay (e.g. "33s") from an API error, if present."""
    body = exc.details if isinstance(exc.details, dict) else {}
    for detail in body.get("error", {}).get("details", []) or []:
        if str(detail.get("@type", "")).endswith("RetryInfo"):
            match = re.fullmatch(r"([\d.]+)s", str(detail.get("retryDelay", "")))
            if match:
                return float(match.group(1))
    return None


def _gemini_id(call_id: str) -> str | None:
    return None if call_id.startswith(LOCAL_ID_PREFIX) else call_id
