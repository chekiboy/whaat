---
name: skill-proposals
description: Use when work just replayed a procedure someone will run again — steps followed from a recipe memory, a script written for the task, a command chain that took several tries, a workaround for a gap in an existing skill — by calling this skill with args `note <skill name> — <the sign, in one sentence>`; and when session-end's steps reach the skill proposals (`session-end`) or the user asks whether something should become a skill, to propose and ask. Builds nothing without the user's yes.
argument-hint: "[note <skill name> — <the sign> | session-end]"
---

# Skill proposals

This step is not part of saving memories. It has two moments: during the work the call itself is the note
of a candidate, and at session end it asks about the candidates.

Did the work run a procedure someone will run again? Signs: steps replayed by hand from a recipe memory, a
script written for the task, a command chain that took several tries, a workaround for a gap in an existing
skill. A one-off, or a fact one memory line carries, is no skill.

## note: during the work

Called with `note <skill name> — <the sign>`, the call is the note: it shows as this skill's own tool call,
not as a message to the user, and the transcript keeps its args. Write nothing about it in the reply; ask
nothing, build nothing, and go on with the work. One call per candidate; a candidate already noted is not
noted again.

## session-end: at session end, or when the user asks

1. Collect this session's notes: the calls of this skill with `note` args. After a compaction they may be gone
   from the context: search the transcript (`<config dir>/projects/*/<session id>.jsonl`) for `Skill` tool calls
   whose `skill` is `whaat:skill-proposals` and whose `args` start with `note `. Then check the whole session
   against the question above for a candidate no note caught. Leave out a candidate the user already decided on
   in this session.
2. For each candidate left, propose, in the reply, a new skill or an addition to the skill that already covers
   that work:
   - its name and trigger, i.e. when it should fire;
   - its level: one repo's `.claude/skills/`, or `~/.claude/skills/` with its source in the framework repo's
     `.claude/templates/skills/` when it holds across projects;
   - what it bundles (script, steps) and which recipe memories it takes over; those shrink to the traps the
     skill does not cover.
3. Ask once whether to build each one, one choice per question. Build it only on the user's yes; a no drops it.
   Nothing to propose: say so in one line.
