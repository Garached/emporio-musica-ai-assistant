# Phase 04 — Agent Loop

**Goal:** Build the hand-written agent loop with Gemini function calling behind a provider-neutral LLM interface. First phase with real LLM calls.

---

Context: Phase 4 of the Empório da Música customer service agent. See
docs/prompts/ for previous phases. Data layer, tools (src/emporio/tools.py,
with a provider-agnostic JSON Schema registry and run_tool dispatcher) and the
system prompt (src/emporio/prompts/) are done and tested. Read them first.

Goal of this phase: the agent loop with Gemini function calling. First phase
with real LLM calls. Build the loop by hand (no agent frameworks like
LangChain): the point is to show how an agent works internally.

0. Model change (happened during development, record it):
   - gemini-2.5-flash is no longer available to new users, and
     gemini-3.8-flash returned repeated 504 DEADLINE_EXCEEDED errors on the
     free tier (a known capacity issue). gemini-3.5-flash-lite works reliably
     on the free tier.
   - Change the default GEMINI_MODEL in config.py and .env.example to
     "gemini-3.5-flash-lite". Keep the model configurable, and add a comment
     in .env.example saying gemini-3.8-flash can be used on a paid tier.
   - Record this model change and its reasons in the GeminiClient docstring
     so it can go in the README later.

1. Provider abstraction: src/emporio/llm/
   - base.py: provider-neutral types and interface. A small message format
     (user / assistant / tool results), a ToolCall type (id, name, args), an
     LLMResponse (text and/or tool calls), and an LLMClient Protocol with one
     method: generate(system_prompt, messages, tools) -> LLMResponse.
     Swapping Gemini for another provider must only require a new client
     class, with no changes to the agent.
   - gemini.py: GeminiClient implementing LLMClient with the official
     google-genai SDK (check the installed SDK version and use its current
     API). Convert our JSON Schema registry into Gemini function
     declarations. Disable automatic function calling: our loop runs the
     tools. Low temperature (0.3) for consistent, factual answers.
   - Use the generateContent API (client.models.generate_content). Google now
     recommends the new stateful Interactions API, but generateContent is
     still fully supported, and its stateless design fits our provider
     abstraction: our Agent owns the conversation history, so swapping
     providers stays easy. Document this choice in the GeminiClient docstring.
   - IMPORTANT: Gemini models (2.5 and 3.x) may return "thought signatures"
     with function calls, and they must be sent back unchanged in the
     following turns. Keep the provider's raw model content inside our
     neutral assistant message (an opaque field only the Gemini client
     reads) and replay it as-is.
   - If the SDK supports a thinking level for the configured model, use a
     low one and make it configurable; if the model doesn't support it,
     don't send it.
   - Set an explicit request timeout (60s) so a slow model never hangs the
     app.
   - Retries: on rate-limit (429), timeouts and temporary server errors (5xx,
     including 504), retry with exponential backoff, honoring the retry delay
     suggested by the API when present, up to a few attempts. The free tier
     has low per-minute limits, so this matters.

2. src/emporio/agent.py: an Agent class
   - Holds the conversation history in memory (one Agent = one conversation).
   - chat(user_message) -> AgentReply(text, trace).
   - Loop: call the LLM; if it returns tool calls, run each one with
     run_tool (it may request several at once), append the results, and call
     the LLM again; repeat until it returns plain text.
   - Safety limit: at most 6 LLM iterations per user message; if exceeded,
     return a friendly fallback message with the store contact.
   - Rebuild the system prompt on every turn (date, time and open/closed
     status can change during a conversation).
   - If the LLM still fails after retries, return a friendly message in
     Portuguese with the store contact instead of crashing.
   - Trace: for each tool call, record name, args, a short result summary and
     duration. Also log it with the logging module (DEBUG level). The CLI
     will use this later for a debug mode, and it's how we see when the agent
     consults data vs. policies.
   - History trimming: keep the last N turns (configurable, default 20
     messages) to control context size, never cutting between a tool call
     and its result.

3. scripts/smoke_chat.py: a tiny script that runs a short conversation with
   the real model (e.g. "Oi!", "Quanto custa o Takamine GD20?", "Vocês
   vendem palheta?") and prints each reply with its tool trace. It's for
   manual checks only, not the final CLI (that's Phase 5). Keep it short:
   the free tier has a low daily request limit.

4. tests/test_agent.py: unit tests with a FAKE LLM client (scripted
   responses, no network, no API key):
   - plain text reply, no tools
   - one tool call, then a final answer; the trace records the tool
   - several tool calls in one response are all executed
   - a tool error is passed back to the model, not raised
   - the 6-iteration safety limit returns the fallback message
   - an LLM failure returns the friendly error message
   - history trimming never separates a tool call from its result
   Optionally, one integration test with the real Gemini API, skipped unless
   RUN_INTEGRATION=1 is set (so the default test run is free and offline).
   Run pytest; all tests must pass.

5. Save this exact prompt to docs/prompts/04-agent-loop.md with a short
   header.

Code style: type hints, short docstrings, small functions, no over-engineering.

Git rules: small logical commits (e.g. model default change, llm base types,
gemini client, agent loop, smoke script, tests, prompt). Short English
Conventional Commit messages. Do NOT push.

When done, run scripts/smoke_chat.py once and show me the output, then
summarize files, commits, test results and any decision I should know about.

---

## Earlier update (sent before this prompt)

This update arrived before the Phase 4 prompt. Its config parts were applied
then (commit "feat: default to gemini-3.8-flash and add thinking level
setting"); the model default was later changed again by step 0 above.

UPDATE (model changed): gemini-2.5-flash is no longer available to new users.
- Change the default GEMINI_MODEL in config.py and .env.example to
  "gemini-3.8-flash". Keep the model configurable.
- Thought signatures also apply to Gemini 3.x models: keep the raw model
  content and replay it unchanged, as described above, regardless of version.
- Use the generateContent API (client.models.generate_content). Google now
  recommends the new stateful Interactions API, but generateContent is still
  fully supported, and its stateless design fits our provider abstraction:
  our Agent owns the conversation history, so swapping providers stays easy.
  Document this choice in the GeminiClient docstring.
- If the SDK supports a thinking level for this model, use a low one (faster
  and cheaper, enough for customer service) and make it configurable.
