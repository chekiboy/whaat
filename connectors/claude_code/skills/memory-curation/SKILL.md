---
name: memory-curation
description: Use when the shared memory store needs reviewing or cleaning up — the user asking to tidy, deduplicate or prune memories, a recalled memory that proved wrong or stale, two memories found saying the same thing, or an index grown so long that triggers stop being read. Not for saving a single new learning (memory). Writes the report through whaat, into this identity's private folder.
model: opus
effort: high
argument-hint: "[report | apply-rows report=<report_id> | revert-applied-rows report=<report_id> rows=<n,…>] [confirmed=report-page]"
---

# Memory curation

Keeps the shared store small and right: one fact in one file at the right level, nothing stale, and
an index line that fires exactly when the file is needed. Format, levels, budgets, index shape and the
commit rule are the memory skill's; read its SKILL.md (`${CLAUDE_SKILL_DIR}/../memory/SKILL.md`)
in full before judging anything. This skill never restates them.

The first argument names the operation, like a method; the rest are its named arguments:

- `report` (default) writes the report and changes nothing.
- `apply-rows report=<report_id>` applies the rows the user approved on the report page.
- `revert-applied-rows report=<report_id> rows=<n,…>` undoes applied rows.
- `confirmed=report-page` on either: the user confirmed it on the report page.

A free-text request ("apply rows 3, 5") maps to the same operation. `W` below is
`${CLAUDE_SKILL_DIR}/../../scripts/whaat`.

## report

1. Lint: `${CLAUDE_SKILL_DIR}/../../scripts/whaat memory lint`. Its findings are mechanical
   facts; its duplicate and stale lists are only candidates, by word overlap and by backticked paths
   missing from the repo's origin default ref (generated files such as `vendor/` or `.nuxt/` appear there and are fine).
   Its Validity section lists `uncertain` and `stale` files: each `stale` one is a `verify` row (still true,
   and still needed?); when the check holds, the apply step sets `confirmed: <today>`. Superseded files are
   history, never `delete` rows. Its Recall outcomes section names memories whose trigger keeps opening them
   for the wrong task (a `retrigger` row) and memories that misled a session (check they were fixed).
2. Judge each dir (the dirs of the lint's Index sizes) by its brief, never by words of your own:
   `${CLAUDE_SKILL_DIR}/../../scripts/whaat memory curation-brief dir=<dir>` (`dir=.` for the global one) prints
   the dir's fixed brief: what every action requires and how it is checked (`judge-brief.md` beside this file), how
   to read the dir with the recall dump (a curation read is no recall), and the dir's candidates from the lint, each
   of which gets a row or a `keep`.
   - A dir with more than ~40 files goes to one read-only subagent. Its prompt is that output as it is: nothing
     added, removed or reworded (no focus list, no premise of yours). Judge every other dir yourself by the same
     brief.
   - Refute each dir's rows from another aspect: `${CLAUDE_SKILL_DIR}/../../scripts/whaat memory curation-refute-brief dir=<dir> <
     <the judge's answer as a JSON file>` prints the refuter's fixed text (`refute-brief.md`) with those rows. A dir
     whose judge was a subagent gets one read-only refuter subagent with that output as its whole prompt; the
     small dirs you refute yourself by the same text. Take each verdict as it is: `holds` keeps the row,
     `changed` replaces it (its reason keeps the judge's original), `dropped` sends it to `Judged and let go`
     with the refuter's why.
   - Then merge across dirs: a merge or move that spans two dirs is yours to add, by the brief's requirements, and
     you refute it yourself by the same text. A row you do not take goes to `Judged and let go` with the reason; a
     row you change keeps the judge's original in its reason. Every `kept` entry goes to a `Kept candidates`
     section (file, check, reason).
   Before writing rows, read what the user discarded in earlier reports: `W journal discarded`. A proposal with the same file and the same `actions` that the user
   discarded is not made again, unless that entry says `changed_since: true` (the file changed after that report);
   then make it again only if it still holds, and say in its reason that it was discarded on <report_date>.
3. Write the report as JSON to `memory-curation.json` in the scratchpad with the Write tool:
   ```
   {"lint_summary": "<index sizes and the problem counts by check>",
    "rows": [{"n": 1, "file": "<path>", "actions": ["<action>", …], "target": <…|null>, "reason": "<…>",
              "evidence": <…|null>, "applied": null}],
    "unchecked": "<what you could not check, and why>",
    "sections": [{"heading": "<any further part>", "markdown": "<its text>"}]}
   ```
   `sections` holds what else the report needs to say (what was judged and let go, refs), each as markdown; leave it
   empty when there is nothing.
   One row per change: actions that build on each other, on one file or one needing another's result (a `retrigger`
   of the file a `merge` keeps, a `trim` before its new index line), are one row with `actions` in the order they
   run, so the user approves and applies them together; otherwise one action per row. `applied` stays null until
   apply fills it. Target: the file to merge into, the level to move
   to, the new index line, or the split file names. Evidence: the other file's name, the ref and missing path, the
   doc that already says it. Mechanical lint problems (name, type, link, abs-path) get rows too, action `fix`. A
   `fix` row's target is the corrected text; without one the row is `verify`.
   Save it, then open it for review:
   ```
   ${CLAUDE_SKILL_DIR}/../../scripts/whaat journal save-curation < <scratchpad>/memory-curation.json
   ${CLAUDE_SKILL_DIR}/../../scripts/whaat open <report_id>
   ```
   If whaat refuses it, fix what its message names in the file and save again.

In report mode never write, move, delete or commit anything in the store, and don't save memories
about this run: the store is shared and nobody reviewed the report yet. After the report, stop and
wait for the user.

## apply-rows

Input: `report=` (a report the user has read). Read it with `W show <report_id>` (the report as JSON). The rows to
apply are those whose `decision` is `apply`; a `reject` row and a row without a decision are left alone. Ask which
rows if none says `apply`. A row's `note` is the user's word on that row: it can narrow or change what the row does;
when it conflicts with the row or is unclear, ask before applying that row. With `confirmed=report-page` the rows
were confirmed on the page, risky ones listed by action, and that counts as the yes; otherwise rows holding
`delete`, `merge` or `move` only with their explicit yes.

- Re-check a `delete` or `verify` row of a repo memory on a fresh clone (`/git-checkout-pure`) before
  acting, with git as `(cd <clone> && git …)`; a report is a week old.
- A row's `actions` run in the listed order as one change; stop the row at the first that fails.
- Make each change through the memory skill's Save rules: format, budget, index line in the right
  dir's `MEMORY.md`; save with `W memory save`, remove with `W memory delete <path>`.
- Before committing a `trim`, `merge` or `split`, check what the text still does; lint proves format
  and budget, never that:
  - walk the diff: each removed sentence lives on somewhere you can name (the skill, the code on the
    origin ref, the other memory) or was narrative. A trap or decision with no new home goes back in;
    if that breaks the budget, split instead;
  - remove a code fact only after the origin ref shows it is gone, never check it afterwards;
  - read the index line against the new body: it still opens the file when needed, and only then;
  - the body keeps the memory skill's shape (rule in 1–3 sentences, **Why**, **How to apply**).
  The evidence for this check is that per-sentence account, not a green lint. Make it from the fidelity table:
  `W memory fidelity file=<the memory as it was> new=<every
  memory its text now lives in> rev=<the commit before your change>` lists every old sentence and whether the new
  text keeps it word for word; each one it does not gets a line of account (reworded where, moved where, cut as
  narrative), and a changed meaning is fixed with another save before the row's Applied cell is written. The
  account goes into that cell after the commits.
- After a merge, move, split or rename, update every `[[link]]` to the old name (`grep -rl '\[\[<old>\]\]'
  <memory dir>`, the dir from `W memory where --path store`) and both indexes.
- Each save or delete commits by itself. Never push the memory: what reaches a remote is the user's call, after
  they have read it.
- Write each applied row's commits into its Applied cell (`store <sha> <sha>`) with
  `W journal save-applied --report <report_id> < <scratchpad>/applied.json`, the file holding
  `[{"n": <row>, "applied": "store <sha> …"}]`, and leave the row in the report. Never save the report again with
  `save-curation` here: it replaces the whole report and the user's decisions with it.
- Re-run `W memory lint` at the end; a new problem it reports is yours to fix.

## revert-applied-rows

Input: `report=` and `rows=`, each row with commits in its Applied cell (`confirmed=report-page`
counts as the yes). Per row: `W memory revert <sha> …` with that row's commits; whaat undoes them newest first in
one run, and a conflict aborts it whole and changes nothing. Re-run `W memory lint`, check that every
`[[link]]` and index line the revert restored resolves, and empty the Applied cell (`"applied": null` through
`W journal save-applied`), so the row is open again. Never push.

Never touch the auto-memory dirs (`~/.claude/projects/*/memory/`) or `<store>/.claude/agent-memory/`
(subagents' own memory, empty dirs included).
