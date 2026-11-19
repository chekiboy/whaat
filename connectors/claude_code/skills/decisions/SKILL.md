---
name: decisions
description: Use when a run stops to wait for the user's decisions — a phase gate, review findings to accept or skip, options at a design gate, memory candidates — or the user asks to decide on a page. Puts the questions on a whaat decisions page, waits in the background for the answer and reads it back; nothing is decided in chat.
argument-hint: "[ask | read --report <id>]"
---

# Decisions

The user decides on a whaat page, not in the chat: each question with what it needs to be decided well, its options
and the one I recommend. I wait for the answer in the background and go on from what they chose. The page belongs to
this session: whaat lists it with the session's report and journal.

## ask (default)

1. Write the page as JSON into the scratchpad:

   ```json
   {
     "title": "ABC-101 · phase 3 gate",
     "asked_by": "implement-task · phase 3",
     "summary": "What the user should know first, as markdown: the verdict, a table, what was measured.",
     "rows": [
       {
         "n": 1,
         "title": "Drop the redundant check",
         "explain": "What changes, why, what it costs; enough to decide without opening anything else.",
         "options": [
           {"value": "apply", "label": "Apply it", "recommended": true, "why": "KISS"},
           {"value": "skip", "label": "Skip it"}
         ]
       }
     ]
   }
   ```

   One question is one row: its alternatives are options of that row, never further rows. Each row has at least two
   options, with distinct `value`s (lowercase, digits, `-`). Mark at most one option `recommended`; a row where I have
   no recommendation marks none. `why` is a word or two, never a sentence. Give "do nothing" as an option wherever it
   is a real choice. The page has no free answer field beyond each row's note, so a question with an open answer is
   not a row: ask it in chat.
   Write the title, the summary and the rows in the language of the work's documents; whaat translates only its own
   interface around them.

2. Save it as this session's page; the same `--slug` again replaces the page, until it is answered:

   ```bash
   ${CLAUDE_SKILL_DIR}/../../scripts/whaat decisions save --session <session8> --slug <slug> [--ticket ABC-101] [--tag <tag>] < <scratchpad>/decisions.json
   ```

   It prints the page's `report_id` and a `page:` line with its address. Give the user the address in one line. An
   answered page is refused (409): save a new slug instead.

3. Wait for the answer as a background command, so the session is woken when the user sends it:

   ```bash
   ${CLAUDE_SKILL_DIR}/../../scripts/whaat decisions wait --report <report_id>
   ```

   Run it with `run_in_background`. It asks the server every few seconds and survives a server restart. While it
   runs I do not act on any of the questions; work that none of them touches may go on. If the user answers in chat
   instead, their chat answer counts: stop the wait and say that the page stays unanswered.

4. When the wait ends, its output is the answer, and I continue from it:

   ```text
   decisions 2026-11-19_0a1b2c3d_phase-3-gate (session 0a1b2c3d): sent 2026-11-19 11:42
   1. apply
   2. skip (not the recommended) — only together with row 3
   3. —
   ```

   `n. <value>` is the chosen option. `(not the recommended)` marks a choice against my recommendation: read its
   note before acting. The note after `—` can narrow or change what the choice means, and it wins over my reading of
   the option. `n. —` is a row the user left open: it is not a yes; ask about it again, or leave it, and say which.

## read --report <id>

Prints the same answer once, without waiting. While the page is not answered it says so and exits 2: then nothing
was decided yet.

## Rules

- Never write the page file yourself and never edit it after the answer: whaat stores it in the identity's private
  folder and stamps the answer.
- The answer is the user's decision: it is never overridden by a later finding of mine; new evidence goes back to
  them as a new question.
