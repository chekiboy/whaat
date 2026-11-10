---
name: session-end
description: Use when the user ends the working session — says "végeztünk", "we're done", "that's it for today" — or a decision page sends `/whaat:session-end steps=none confirmed=report-page`. Runs whaat's session-end steps in order, each through its own skill, then closes only when nothing is left open.
argument-hint: "[steps=all|none] [confirmed=report-page]"
---

# Session end

One place that ends a session, so the wrap-up does not depend on a line being remembered.

## steps

- `all` (default): these steps, in this order, each through its own skill. Say in the reply which steps ran and
  which were skipped, with the reason.
  1. **Memory:** `/whaat:memory task-end`, the session's learnings.
  2. **Skill proposals:** `/whaat:skill-proposals session-end`.
  3. **Journal:** `/whaat:journal write-session-entry`, the journal entry and the session report.
- `none`: a scheduled run's decision page sends this from its "Done" button (`confirmed=report-page`). That run
  is not a working session: no journal entry, no skill proposals.

## Then, on either path

1. Wait until every background task or subagent this session started has finished.
2. If something is still open (a question not yet asked, a command or decision handed to the user as still
   waiting on them, a step that failed), ask it now, one choice per question, and stop. Reread the reply for
   such items before the closing line. Once it is settled, end the same way.
3. Otherwise end the reply with this line alone: `SESSION-END: nothing open`. In a normal session the line only
   marks the end.
