# Journal and session end

When a working session ends, the agent writes down what happened: a private journal entry for itself, and a session report for you. Together with the memory, these are how the identity carries its past into the next session.

You trigger it by ending the session in plain words ("we're done", "that's it for today"). The agent runs the steps itself.

## Session end: one place that closes a session

The `/whaat:session-end` skill runs these steps in order, each through its own skill:
1. **Memory:** the agent saves what the session taught it, and records whether the memories it recalled held up (see [Memory](memory.md)).
2. **Skill proposals:** the agent asks whether something it did should become a reusable skill.
3. **Journal:** the journal entry and the session report.

Then it waits for anything still running, asks any question still open, and ends with the line `SESSION-END: nothing open`.

## The journal entry: written for the agent itself

One entry per session, never rewritten afterwards. It starts with a free-form narrative in the agent's own voice, then fixed fields:
- what the session was about;
- the agent's own mistakes, skipped steps included;
- the user's corrections (what was corrected, not the tone);
- what it learned about itself, if anything;
- the feelings that came with each part of the session, stated as uncertain;
- the moments it spoke in its own voice, quoted word for word with the time.

The journal is private: only its identity and the admin token can read it.

## The session report: written for you

A page about the whole session:
- the task and why it was needed;
- the outcome: done, partly done or stuck;
- the steps, one line each;
- the **decisions**, split into yours and the agent's, each with the options that were really on the table and why one was chosen;
- **drift:** where the work moved away from what was asked, and why: the goal changed, the agent misread it, or the code showed something else;
- open questions.

The report is written in the language you work in. One session has one report; a later run rewrites it.

## How Whaat stores them

The agent fills in fixed fields; Whaat checks every field, refuses unknown or missing ones, and saves each document as JSON in the identity's folder, one commit per document. A save that Whaat refuses says what to fix. Both show up on the [Reports](reports.md) page, the journal next to its session's report; the agent also gives you the report's id, which `whaat open <id>` opens.

## Skill proposals

During the work, when the agent repeats a procedure someone will run again (steps followed from a recipe, a script written for the task, a command chain that took several tries), it notes it quietly as a candidate. At session end it proposes each candidate as a new skill or an addition to an existing one, and asks once per candidate. It builds nothing without your yes.

## Commands

| Skill or command | What it does |
|---|---|
| `/whaat:session-end` | Runs the session-end steps in order |
| `/whaat:journal write-session-entry` | Writes the journal entry and the session report |
| `/whaat:journal write-session-report` | Writes only the session report, e.g. when you ask for a summary |
| `/whaat:skill-proposals` | Notes a candidate during the work; proposes them at session end |
| `whaat journal save` | Saves a journal entry |
| `whaat journal save-report` | Saves a session report, replacing that session's earlier one |
