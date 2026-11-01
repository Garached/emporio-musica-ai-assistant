# Phase 05 — CLI

**Goal:** A polished interactive terminal chat with Clave (rich), with commands, a debug mode showing tool calls, a simulated "today", and automatic markdown transcripts.

---

Context: Phase 5 of the Empório da Música customer service agent. See
docs/prompts/ for previous phases. The agent loop (src/emporio/agent.py) works
with Gemini and returns AgentReply(text, trace). Read it first.

Goal of this phase: a polished interactive CLI to chat with Clave, using
`rich`. Keep it simple: the focus is the agent, but the experience should
feel finished.

1. src/emporio/cli.py
   - Welcome panel: store name, slogan ("Sua música começa aqui."), the
     model in use, and a one-line hint of the available commands.
   - Input prompt "Você:"; Clave's replies clearly styled (name + color),
     printed as plain text (not rendered as markdown).
   - While waiting for the model, show a spinner like
     "Clave está digitando...".
   - Commands (Portuguese, with a slash):
     /ajuda  - list commands
     /nova   - start a new conversation (fresh Agent, history cleared)
     /debug  - toggle debug mode: after each reply, show the tool trace
               (tool name, args, result summary, duration) in a dim style.
               This makes visible when Clave consults data vs. policies.
     /sair   - exit
   - Ctrl+C or Ctrl+D exits gracefully with a goodbye message, no traceback.
   - If configuration is missing (e.g. no API key), show the friendly config
     error and exit cleanly.
   - Make sure accents and emojis print correctly on Windows PowerShell
     (force UTF-8 output if needed).

2. Command-line options (argparse):
   - --debug: start with debug mode on.
   - --today YYYY-MM-DD[THH:MM]: override "today" for this session (same
     effect as EMPORIO_TODAY). The data is a snapshot from early 2026, so this
     is how we demo return-window rules.

3. Transcripts (conversation persistence):
   - Every session is saved automatically to transcripts/ as a markdown file
     named with date and time (e.g. transcripts/2026-10-31_2130.md), updated
     after each message so nothing is lost if the app is closed.
   - Format: a header (date, model, the "today" in use), then each turn as
     "**Cliente:** ..." / "**Clave:** ...", with the tool calls of each turn
     listed below the reply in a compact, readable way.
   - /nova starts a new transcript file.
   - Add transcripts/ to .gitignore (we'll pick the best ones as examples
     later and put them in a separate folder).

4. Entry points: make the CLI runnable with `python -m emporio` and with a
   console script named `emporio` (pyproject). Reinstall the package if
   needed so the command works.

5. tests/test_cli.py with a FAKE agent (no network): command handling
   (/nova resets, /debug toggles, /sair exits, unknown command shows help),
   the --today option is applied, and the transcript file is written with
   the expected format (including tool calls). Run pytest; all tests pass.

6. Save this exact prompt to docs/prompts/05-cli.md with a short header.

Code style: type hints, short docstrings, small functions, no over-engineering.

Git rules: small logical commits (e.g. cli core, commands and debug mode,
transcripts, entry points, tests, prompt). Short English Conventional Commit
messages. Do NOT push.

When done, summarize files, commits and test results, and tell me the exact
commands to start the chat (normal, debug mode, and with --today).
