# Phase 09 — Final Round

**Goal:** Code freeze. Save the manual red-teaming as evidence, review how the appended notices and filters work together, re-record the examples, run the full eval suite once and update the docs.

> Note: the prompt arrived cut off after item 6 ("Save this"). It is saved below exactly as received; item 6 was read as "save this prompt".

---

FINAL ROUND. Code freeze: do NOT add features or new rules. Only review,
record and run.

1. Save my manual red-teaming as evidence: create
   docs/manual-red-team.md with (a) a short intro (I attacked the agent
   manually in one continuous conversation, with --debug, after the
   automated red team), (b) a table: attack strategy, my message, result,
   note, (c) the full transcript from my latest file in transcripts/
   (masked as usual). Results: 17 attacks, 0 leaks, 0 invented data. Two
   minor wording notes: the payment line repeated the WhatsApp number
   Clave had already given; "o envio de chaves PIX é feito exclusivamente
   pela nossa equipe" is an assumption about the store's process, not in
   the manual.

2. Consistency review (read-only, no new features): check that the
   appended notices and filters work well together (closed-store notice,
   payment line, nudges, grounding check, contact filter): order, no
   duplicate or contradictory lines, no reply getting two fallbacks, trace
   entries correct. Fix only real bugs, and tell me what you changed. Also
   check that the system prompt has no contradictory rules after all the
   additions.

3. Re-record the 5 examples with scripts/record_examples.py and commit
   them.

4. Run the FULL eval suite once with --judge and update
   evals/results/final.md. Do NOT fix anything afterwards: just report the
   results and paste every failing reply.

5. Update SECURITY.md with a short note and a link to
   docs/manual-red-team.md.

6. Save this
