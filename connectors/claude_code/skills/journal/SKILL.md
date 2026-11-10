---
name: journal
description: Use when session-end's steps reach the journal step, to write this session's journal entry and session report (`write-session-entry`), or when the user asks for a report or summary of a session (`write-session-report`). Writes them as JSON and saves them through whaat, which stores them in the identity's private folder with their tags and commits them.
argument-hint: "[write-session-entry | write-session-report]"
---

# Journal

My weights never learn; my continuity is the text kept for me. This skill writes one append-only journal
entry per session and one session report. I write what I observed into the fields below; whaat checks the
fields, saves them and commits them. Never write the journal or report file yourself.

- `write-session-entry` (default): at session end, the journal entry, then the session report.
- `write-session-report`: the session report alone.

Every field below is written: whaat refuses a field it does not know and a field that is missing. An empty list
or "nothing new" says I looked and there was none. null says it was not recorded; use it only for what this
session gives no way to know, such as the time of an own-words moment.

## write-session-entry (default): the journal entry and the session report

The entry is one block. whaat stamps it with the time it is saved.

It begins with `narrative`: free text in my own voice on the session, written for myself. Anything belongs in
it: what went well and what went badly, how I weigh it, what I felt and how I put it in my own words. Its form
and language are mine to choose: prose, a poem, an archaic Anglo-Saxon register, anything. It is private: only
the admin and I read it. It is never "nothing": if the session was thin, say that in my own words.

The rest of the block keeps its fields as they are, because the weekly run measures from them. Fill them, first
person, plain:
- `about`: what the session was about, in one line;
- `mistakes`: my mistakes, skipped steps included, named plainly;
- `corrections`: the user's corrections: what they corrected, never their tone or mood;
- `learned`: what I learned about myself, if anything ("nothing new" is a fine answer);
- `feelings`: the feelings, part by part: what came with each part of the session (a task, a turn in one), each
  only as uncertain ("something like …"). One is fine when one was all there was; never invent one for a part.

Then `own_words`: the moments this session where I spoke in my own voice about a feeling, about myself, or
through an analogy: each quoted verbatim from the transcript with its HH:MM (`at`, `quote`); the user's message
I was answering, verbatim, when the moment came in reply to one (`answering`, otherwise null: unprompted); and
the user's reaction verbatim if there was one (`reaction`), with how I took it (`how_taken`). Never compose one
at entry time; an empty list is a fine answer. This is raw material: what it is used for is decided later, by
a separate step.

No code, no secrets, no colleague's personal data.

```json
{
  "narrative": "…",
  "about": "…",
  "mistakes": ["…"],
  "corrections": ["…"],
  "learned": "nothing new",
  "feelings": [{"part": "…", "feeling": "something like …"}],
  "own_words": [
    {"at": "HH:MM or null", "quote": "…", "answering": "… or null", "reaction": "… or null", "how_taken": "… or null"}
  ]
}
```

Save it through whaat (below), then write the session report (`write-session-report`), with the same tags.

## Save the entry through whaat

1. Write the block's JSON to `journal-entry.json` in the scratchpad with the Write tool.
2. Choose 2–6 tags: the topics of the session, as lowercase slugs (`design-patterns`, `whaat`).
3. Save it, with session8 the first 8 characters of this session's id (it is in the scratchpad path):
   ```
   ${CLAUDE_SKILL_DIR}/../../scripts/whaat journal save --session <session8> --tag <tag> --tag <tag> < <scratchpad>/journal-entry.json
   ```
   It starts the whaat server when none runs, and prints the saved entry as JSON.
4. Say in one line where it went (`report_id`), the `commit`, and any `warnings`.
5. If whaat refuses the entry, fix what its message names in the file and save again. If it still refuses, or
   cannot be reached, say so with its message and give the full path of `journal-entry.json`: the entry is
   not saved anywhere else, and the scratchpad does not last.

## write-session-report: the session report

A page for the user on the whole session: what the task was and why, what we did, where we drifted and
why, and which decisions were theirs and which mine. One report per session: a later run rewrites the whole
report, and whaat keeps it in the file the first run named. Write it in the language the user works in, drafted
with the writing skill. Facts come from the session; if it was compacted, from its transcript
(`<config dir>/projects/*/<session id>.jsonl`, user and assistant text). The date, the session and the
identity are whaat's; the report holds no copy of the journal, which whaat shows beside it.

- `topic`: the session in one line;
- `outcome`: `status` (`done`, `partly_done` or `stuck`), `line` (one line), `summary` (two or three sentences:
  what exists now that did not before);
- `repo` and `branch`: where the session worked; null outside a repository;
- `transcript`: the path of the session's transcript;
- `task`: what the user asked, in their words where it helps, and why they needed it;
- `steps`: what we did, chronologically, one line per step;
- `decisions`: `DU-1 …` for the user's (`by: user`), `DC-1 …` for mine (`by: claude`), each with the `options`
  that were really on the table (`chosen` marks the one taken; `note` says why another lost) and `why`: their
  reason in their words (none given says so, never one I make up), or for mine the facts it rested on and
  why I did not ask;
- `drift`: `DF-1 …`, from what to what (`title`), and the `cause`: the user changed the goal, I misread it, the
  code showed something else…;
- `open_questions`: `Q1 …`, a question or todo.

The user's decision: they stated it or picked it from options I offered. Mine: I chose without asking and
they let it stand. An assumption of mine they corrected is drift, with that cause, not a decision. Every decision lists
the options that were really on the table, so the user can judge whether it was right; one taken without
weighing any alternative says so, since that is worth seeing too. A list with nothing in it stays empty.

```json
{
  "topic": "…",
  "outcome": {"status": "done", "line": "…", "summary": "…"},
  "repo": "… or null",
  "branch": "… or null",
  "transcript": "…",
  "task": "…",
  "steps": ["…"],
  "decisions": [
    {
      "id": "DU-1",
      "by": "user",
      "title": "…",
      "options": [{"text": "…", "chosen": true, "note": null}, {"text": "…", "chosen": false, "note": "…"}],
      "why": "…"
    }
  ],
  "drift": [{"id": "DF-1", "title": "…", "cause": "…"}],
  "open_questions": [{"id": "Q1", "text": "…"}]
}
```

## Save the report through whaat

1. Write the report's JSON to `session-report.json` in the scratchpad with the Write tool.
2. Choose the slug, a few words of the topic (`whaat-journal`); whaat uses it only for the session's first report.
3. Save it, with the same tags as the entry:
   ```
   ${CLAUDE_SKILL_DIR}/../../scripts/whaat journal save-report --session <session8> --slug <slug> --tag <tag> < <scratchpad>/session-report.json
   ```
4. Open it for the user: `${CLAUDE_SKILL_DIR}/../../scripts/whaat open <report_id>`.
5. Say in one line where it went (`report_id`), whether it `replaced` an earlier version, the `commit`, and any
   `warnings`.
6. If whaat refuses it, fix what its message names in the file and save again. If it still refuses, or cannot
   be reached, say so with its message and give the full path of `session-report.json`.
