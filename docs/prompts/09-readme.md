# Phase 09 — README

**Goal:** Write the final README in English (instructions, technical decisions, quality, security, limitations, AI usage) and add review notes to the example conversations. Code freeze: no code changes.

---

Phase 9 (final): write README.md in ENGLISH. Code freeze: don't change any
code. My tokens are limited today, so be efficient: read only what you need,
and COMMIT EACH PART AS SOON AS IT'S WRITTEN (if the session ends midway,
progress must be saved).

Read: SECURITY.md, docs/data-quality.md, docs/manual-red-team.md,
evals/results/ (baseline.md, after-fixes.md, red-team.md, final.md: use the
summary lines), examples/, pyproject.toml, the system prompt, and the
headers and "Follow-up" headings of docs/prompts/ (skim them for the story;
don't reread the code unless needed to verify a fact).

The challenge requires: (1) all instructions to run the project, (2)
justification of technical decisions (framework, LLM, retrieval
architecture, prompt strategy), (3) known limitations and what I'd do with
more time, (4) how AI coding assistants were used.

Writing style:
- Plain, natural English, like a careful engineer wrote it. Short
  sentences, common words. It must not read like AI-generated text.
- Avoid: "leverage", "seamless", "robust", "cutting-edge", "delve",
  "comprehensive", "empower", "streamline", "state-of-the-art",
  "game-changer". No exclamation marks, no marketing tone, few em dashes.
- Scannable: headings, short paragraphs, tables. Link to the detailed docs
  instead of repeating them.
- Honest: every number must come from the actual files (test count from
  running pytest, eval scores from final.md and red-team.md). If final.md
  has failures, report them honestly in Quality and Limitations.
- Portuguese terms (PIX, product names, Clave's replies) stay in Portuguese.

Structure:
1. Title, one-line description, "Highlights" (5-7 bullets: hand-built agent
   loop with function calling; business rules in code: prices, PIX,
   installments; output checks in code: every R$ value must come from a
   tool, and unofficial contact or payment details are blocked; data
   quality analysis; evals with baseline vs. after fixes plus automated and
   manual red-teaming; provider abstraction; built with AI under a
   test-gated, phase-by-phase workflow, every prompt in docs/prompts/).
   Then a short real excerpt from an example, with its tool calls.
   Right after the excerpt, add a short "Quick tour for reviewers" list:
   5-6 links with one line each, pointing to the most important files to
   look at first (the agent loop, the tools, the business rules, the eval
   results, SECURITY.md, docs/prompts/), so a reviewer with 2 minutes knows
   where to go.

2. Getting started: prerequisites (Python >= 3.11, free Gemini API key from
   Google AI Studio); steps for Windows PowerShell AND macOS/Linux (clone,
   venv, activate, pip install -e ., copy .env.example to .env, add key);
   run (`emporio`, `emporio --debug`, `emporio --today 2026-02-20`,
   `python -m emporio`); chat commands (/ajuda, /nova, /debug, /sair);
   tests (`pytest`, offline and free); evals (exact command + free-tier
   quota warning).

3. Architecture: a Mermaid diagram (CLI -> Agent loop -> LLMClient/Gemini;
   Agent -> tools -> business rules / data / policies; reply checks:
   grounding, contact filter, notices); how one message flows (numbered,
   real example); short project tree.

4. Technical decisions (decision, alternatives, why), at least:
   - Hand-built function-calling loop vs. LangChain/ReAct libraries, SQL
     agent, pure RAG.
   - Policies via section lookup tool vs. RAG with embeddings (8-page PDF).
   - Model/provider: Gemini free tier so anyone can run it; the model story
     (gemini-2.5-flash unavailable -> gemini-3.8-flash 504s on free tier ->
     gemini-3.5-flash-lite), one-line change thanks to config + retries;
     generateContent vs. Interactions API (stateless, keeps the provider
     abstraction); temperature, thinking level, timeout.
   - Code computes, the LLM communicates: money math, PIX not stacking,
     installment rules, status as source of truth.
   - Defense in layers for what must never be wrong: prompt rules ->
     tools that return the right data -> checks on the final reply
     (grounding, contact filter) -> deterministic notices (closed store,
     official channels on payment messages) -> evals. Use the phishing-link
     story: Clave refused the fake link but invented an "official site",
     which in a scam context could send a customer to a fake one; that led
     to the prompt rule, the official-channels line and the no-site check.
   - Prompt strategy: versioned file, persona "Clave", grounding rules,
     short tone examples, injected context (date, Campo Grande time,
     open/closed), test keeping prompt and tools in sync.
   - Data treatment: table of main inconsistencies and decisions; link to
     docs/data-quality.md; contact info fixed at the source.
   - Interface and persistence: CLI, debug mode, --today, per-session
     transcripts.
   - Timezone America/Campo_Grande (UTC-4).

5. Quality: tests and evaluations
   - Tests were NOT required by the challenge: a deliberate choice, run at
     the end of every phase as a checkpoint.
   - Unit tests: real count, what they cover, fake LLM, fuzzing (it found a
     real crash with non-object tool arguments), tests that depended on the
     real clock were fixed.
   - Evals: deterministic checks, LLM-as-judge, global invariants. Table:
     baseline -> after fixes -> final, plus red team, with real numbers.
   - What human review found: the critical PIX bug the checks missed; the
     discontinued product shown as non-existent with a 26x more expensive
     alternative; vacuous passes; hype words outside the checked scenario;
     invented products in a recorded example (flagged by the coding
     assistant; I decided to enforce grounding in code); the invented
     "official site".
   - The judge's limits: it passed a fallback error, an "announce-then-stop"
     reply and an invented site, because it's the same model; those became
     deterministic checks.
   - Run-to-run variance: the same code scored 170/170 and then 166/170;
     the announce-then-stop failure led to a prompt rule plus a nudge.
   - Knowing when to stop: after the last security fixes I froze the code;
     remaining issues are wording variations, documented below.

6. Security: short summary (read-only tools, rules in code, brute-force
   lock, identical errors, PII masking, input limit, contact/payment filter,
   bandit clean), automated red-team result, manual red-teaming (17 attacks
   in one conversation, 0 leaks; link docs/manual-red-team.md), link to
   SECURITY.md.

7. Example conversations: table of the 5 files (scenario, what it shows),
   note they're in Portuguese and unedited, how to regenerate.
   Also: add a "Review notes" section at the end of each example file,
   clearly separated from the unedited conversation, listing any factual
   issue you find by comparing the replies with the data and the policy.
   Mark each section with <!-- review notes: to be confirmed by Gabriela -->.

8. Assumptions: data snapshot and --today; all orders treated as online;
   estimated_delivery as delivery proxy; status labels; contact info
   choice; installment rule reading; no partner stores; no website in the
   data; holidays not in the data.

9. Known limitations and next steps: model variance and single runs; judge
   = same model; small hallucinations (an "internal system" to a fake
   manager, assumptions about the store's process); self-introduction only
   checked in one scenario; nudge, payment line and no-site check are
   keyword heuristics; output checks cover R$ values and contact/payment
   details only, not names, specs or process details; 4-digit verification
   is weak; per-conversation lock; free-tier data usage; CLI only; no real
   handoff or ticketing; no holidays. "With more time": repeated eval runs
   with pass rates, a different judge model, CI, web/WhatsApp interface,
   real authentication, server-side rate limiting, lock file, tickets for
   complaints and returns.

10. How I used AI: insert EXACTLY the text between the markers. Only fix
   links. Don't rewrite it.

=== START OF MY TEXT ===
(The full text is in the README under "How I used AI in this project",
inserted exactly as provided.)
=== END OF MY TEXT ===

11. Language note: README, code, commits and technical docs in English;
   Clave, the system prompt and the examples in Portuguese because the
   customers are Brazilian.

12. Footer, exactly: "Built by Gabriela Rached" linking to
   https://github.com/Garached

Before finishing: check that every relative link points to an existing
file and every number matches the source files; run `emporio --help`.

Save this prompt to docs/prompts/09-readme.md with a short header.
Commit in small parts as you go (README sections, example review notes,
prompt). Short English Conventional Commit messages. Do NOT push.
When done, list the README sections and anything you couldn't verify.
