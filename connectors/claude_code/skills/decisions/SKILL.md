---
name: decisions
description: Use when a run stops to wait for the user's decisions — a phase gate, review findings to accept or skip, options at a design gate, memory candidates — or the user asks to decide on a page.
---

# Decisions

The user decides on a whaat page: each question with what it takes to decide it, its options and the one I recommend.
I wait for the answer in the background and go on from it.

1. Write the page as JSON into the scratchpad:

   ```json
   {
     "title": "ABC-101 · phase 3 gate",
     "asked_by": "implement-task · phase 3",
     "summary": "What to know first, as markdown: the verdict, a table, what was measured.",
     "rows": [
       {"n": 1, "title": "Drop the redundant check",
        "explain": "What changes, why, what it costs: enough to decide without opening anything else.",
        "options": [{"value": "apply", "label": "Apply it", "recommended": true, "why": "KISS"},
                    {"value": "skip", "label": "Skip it"}]}
     ]
   }
   ```

   One question is one row; its alternatives are its options, never further rows. At least two options per row,
   distinct `value`s (lowercase, digits, `-`), at most one `recommended`. Offer "do nothing" where it is a real choice.
   whaat adds a `discuss` option to every row itself: never offer one. A question with an open answer is not a row:
   ask it in chat. Write the content in the language of the work's documents; whaat translates only its own interface.

2. Save it as this session's page. `<session8>` is the first 8 characters of this session's id (it is in the
   scratchpad path). The same `--slug` on the same day replaces the page until it is answered; another day it makes a
   new page, and after the answer a new slug is needed:

   ```bash
   ${CLAUDE_SKILL_DIR}/../../scripts/whaat decisions save --session <session8> --slug <slug> [--ticket ABC-101] [--tag <tag>] < <scratchpad>/decisions.json
   ```

   Give the user the `page:` address it prints.

3. Wait with `run_in_background`, so the session wakes when the user sends:

   ```bash
   ${CLAUDE_SKILL_DIR}/../../scripts/whaat decisions wait --report <report_id>
   ```

   Until it ends I act on none of the questions. If the user answers in chat instead, the chat answer counts and the
   page stays unanswered: stop the wait.

4. The wait prints the answer, one line per row:

   ```text
   decisions 2026-11-19_0a1b2c3d_phase-3-gate (session 0a1b2c3d): sent 2026-11-19 11:42
   1. apply
   2. skip (not the recommended) — only together with row 3
   3. discuss — why not both?
   4. —
   ```

   - `n. <value>` is the chosen option. The note after `—` narrows or changes it and wins over my reading of the
     option. `(not the recommended)`: read the note before acting.
   - `n. discuss` means the user wants to talk it over: decide nothing on that row, raise it in chat, starting from
     the note.
   - `n. —` is left open, never a yes: ask again or leave it, and say which.

   Repeat the answer lines in my reply, so they outlast a context compaction. The answer is the user's decision;
   new evidence against it goes back as a new question.
