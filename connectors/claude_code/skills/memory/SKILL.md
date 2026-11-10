---
name: memory
description: Use before saving, updating or deleting a memory — when a learning, a user correction or a project/repo fact should outlive the session, at task end when extracting learnings (`task-end`), when the user says "remember"/"jegyezd meg", when something about the user or about working together should be kept, or when you need another repo's memory. Saves through whaat into this identity's own memory. Takes the place of the built-in auto-memory.
model: opus
effort: high
argument-hint: "[what to remember | task-end]"
---

# Memory

whaat keeps this identity's memory in the identity's own folder, a git repo, and shares none of it with
another identity yet. What is about the user, about you or about working together goes to the personal dir.
The harness auto-memory (`~/.claude/projects/*/memory/`) and subagents' own memory are not written; a hook answers
such a write with where it goes.
whaat knows who you are from your token (`WHAAT_TOKEN`). The commands are
`${CLAUDE_SKILL_DIR}/../../scripts/whaat memory …`, written `whaat memory …` below; each starts the server if
it is not running.

## Where

```
whaat memory where [path]          # global / project / repo dirs
whaat memory where --path store|state|personal
```

| Dir | Holds |
|---|---|
| `<memory>/` | cross-project practice: working-style feedback, tool and harness behaviour |
| `<memory>/<project>/` | true for every repo of one group (Jira fields, shared envs, domain) |
| `<memory>/<project>/<repo>/` | true for one codebase (conventions, gotchas, test setup, architecture) |
| `<personal>/` | the user, you, how you work together; `core/` is put into every session start; a core file with `reach: every-agent` reaches every agent |

`<project>/<repo>` is the origin remote path (`…/acme/web.git` → `acme/web`).
Route by what the fact is **about**, not by cwd: a review of repo B run from repo A saves into B —
run `whaat memory where <B's path>`. Facts about the user, you or your work together go to `<personal>/`, never
another dir.

## Read

Recall goes through the whaat:memory-recall skill: `index task=…` lists the global, project and repo triggers
for a path, `open file=… because=…` reads one memory and logs which trigger matched which task. Before a
task, open only the files whose trigger matches it; never bulk-read a dir. For another repo, `index path=<repo>`.
Reads that are not recalls name their purpose (`purpose=save|curate|review`; a whole dir: `dump`). A memory describes the past: check that a
named file, flag or command still exists before acting on it, the more so the older its `confirmed` date.
A file with no index line that another file `supersedes` is history: never act on it.

## Save

1. `grep -ril <term> <memory>` first. Update the existing file rather than add a near-duplicate. If the
   new fact contradicts an old one: when the old one was simply wrong, fix it, or delete it with
   `whaat memory delete <path>`; when it held until the user changed course, write the new file with
   `supersedes: <old name>` and remove the old one's index line (`unindex` below), but keep the file, so the
   change stays findable.
2. Skip: what code, git history, CLAUDE.md or docs already say; per-conversation state (review
   progress, branch state, teardown lists); anything one grep re-derives; secrets.
3. Write `<dir>/<name>.md`, `<name>` = `<type>_<kebab-or-snake-slug>`:
   ```
   ---
   name: <name>
   description: <when to recall it; aim for ≤120 chars>
   type: feedback | project | reference
   when: [<values below>]
   source: measured | user-decision | inference
   confirmed: <YYYY-MM-DD>
   supersedes: <older memory's name>
   ---
   <the rule or fact, 1–3 sentences>
   **Why:** <the reason or failure it prevents, 1 sentence>
   **How to apply:** <the concrete check, command or action>
   ```
   `feedback` = how to work, `project` = a fact about the codebase or domain, `reference` = a
   recipe or pointer. Body ≤ ~1200 characters (a recipe ≤ ~2500); over budget → split into
   separate files by trigger, never drop a non-obvious trap or decision to fit. Aim for lines under ~200. No narrative (who said what, when, how it unfolded). Keep exact
   commands, flags and paths in a recipe; elsewhere name the mechanism, not the class or line —
   those rot. Absolute dates, `~` not `/Users/<name>`. Link related files as `[[<name>]]`.
   The last four fields are optional; leave out what you can't fill. `when` names the moments the memory
   must be in front of you, only these values: `session-start`, `push`, `commit`, `review`, `writing`, `cloud`,
   `verification`, `delegation`, `decision`, `scope`, `shell`, in the inline form `[a, b]` (a hook may surface
   it then). `source` says what backs it; an inference never reaches `certain`. `confirmed` is the last day
   the fact was checked; set it when you re-verify an existing memory. memory-lint scores each memory from
   its source, minus 0.2 per 120 days since the latest of `confirmed`, its last `held` outcome (Task end)
   and its first commit. A memory nobody used successfully or checked for about a year turns `stale`
   and becomes a curation `verify` candidate.
4. Its index line is `- <name>.md — <same trigger>` in that dir's `MEMORY.md` (a core file: `- core/<name>.md — …`
   in `<personal>/MEMORY.md`). The index is a recall trigger list: it says when to open the file, not what the file says.
   `<personal>/core/` changes only when the user asked for it or said yes to it in this session; quote their
   words in your reply. Anything else about them or your work together is a new `<personal>/` file, which the
   weekly self-model-journal may propose folding into the core.
5. Write the file and the trigger through whaat, which writes the file as given, sets that index line, and
   commits only those paths: put `{"path": "<the file's path>", "content": "<the whole file>", "trigger":
   "<same trigger>", "unindex": ["<path of a memory this one supersedes>"]}` into a JSON file in the scratchpad
   with the Write tool, then `whaat memory save < <that file>`. Say the `commit` and any `warnings`.

## task-end: Task end

Before reporting a task done:

1. What non-obvious thing did this task teach — above all a correction or decision by the user? Save
   that at the right level. Textbook facts are not memories.
2. Whether the work should become a skill is `whaat:skill-proposals`' own step, not this one.
3. Judge the memories this session recalled. `whaat memory reads` lists every memory file this session and its
   subagents read or opened through recall, with the purpose and `because` of each open. Judge only the `recall`
   ones, opened because their trigger matched the task, not files read to save, curate or review memories.
   Record each with `whaat memory record <outcome> <path>...`:
   - `held`: the work relied on it and it proved right. Only this refreshes its validity; a read alone doesn't.
   - `misled`: it turned out wrong or stale. Fix or supersede it now, through Save.
   - `irrelevant`: its trigger opened it for a task it doesn't fit. Curation retriggers repeat offenders.
   Leave out a memory you can't judge. Personal memories (`personal:…`) are not recorded yet: leave them out.
