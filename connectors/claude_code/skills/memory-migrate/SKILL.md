---
name: memory-migrate
description: Use when a whaat identity starts with little or no memory while an earlier one exists on this machine (a memory store, a personal memory dir, Claude Code's auto-memory or a subagent's memory), or when the user asks to bring, move or migrate existing memory into whaat. Copies only the groups the user picks; the sources are read, never changed.
model: opus
effort: high
argument-hint: "[import plan=<id>]"
---

# Memory migrate

Brings memory that lives outside whaat into this identity's memory, group by group, on the user's word.
whaat does the copying: it never writes into a source, skips a file already in place with the same content,
and never overwrites one in place with other content (a conflict). Your part is to find the sources, make the plan,
and report; the user chooses on the identity's page. The commands are `${CLAUDE_SKILL_DIR}/../../scripts/whaat memory …`, written `whaat memory …`
below; `migration-plan` reads one JSON object from stdin, so write it to a scratch file and pipe it in.
When this text and the server disagree, the server's answer wins.

## 1. Find the sources

A source is a dir and its `kind`:
- `store`: a layered store, global files at the root, `<group>/`, `<group>/<repo>/`. Each layer is one group.
  On Claude Code it is usually `CLAUDE_MEMORY_STORE`.
- `personal`: a personal memory dir with its `core/`; one group, into `personal/`. Usually
  `$CLAUDE_PRIVATE_ARCHIVE/memory`, unless that archive is this identity's own folder (step 2).
- `loose`: one flat dir that goes to the layer you name in `target`: Claude Code's auto-memory
  (`~/.claude/projects/<project path, / as ->/memory/`) and a subagent's memory (`<repo>/.claude/agent-memory/<agent>/`).

Look in those places and in the repos under the user's work folders; skip dirs with no `.md` memory and the
auto-memory of scratch or temp folders. Ask the user for any source you could not find. The state dir
(`CLAUDE_MEMORY_STATE`) is not a source; name it in the plan, so its outcome log comes along with the import.

A loose dir keeps the project it was saved under. Claude Code keeps its auto-memory per project folder, and a
subagent's memory lives in the repo it was kept in (`<repo>/.claude/agent-memory/<agent>/`); either goes to that
folder's repo layer. `whaat memory where <the folder>` prints it, and the part below the memory root is the target
(`<group>/<repo>`). The project comes from the folder's git remote, never from a name you know or guess, since every
user's projects differ. A folder with no git remote has no project: ask the user where it goes. The other forms are
`.` for global, `personal` and `<group>`. Propose the target; the user may change it on the page.

The folder's repo is the default, not the answer. Before you propose it, read the dir's index title and a few of its
files. When they are plainly about something else, propose that layer and say why: memory about the user, the agent or
working together goes to `personal`; knowledge about another project goes to that project's repo layer, named by
`whaat memory where <that project's folder>`, never by a guess. A dir that mixes both keeps the default, and its files
move after the import (step 5).

## 2. Make the plan

Write what you found into a scratch file and keep it as a plan of this identity:
```
{"sources": [{"path": "/abs/store", "kind": "store"},
             {"path": "/abs/archive/memory", "kind": "personal"},
             {"path": "/abs/.claude/projects/-Users-me-Work-shop/memory", "kind": "loose", "target": "acme/shop"}],
 "state": "/abs/state"}
```
`whaat memory migration-plan < plan.json` keeps it and prints the plan's id, the page's url and a table: one row per
group, `<source number>:<target>`, with its counts of files, new ones, ones already in place (`same`), conflicts,
`history` files (no line in their source index: they come, and recall skips them), index lines rewritten into whaat's
form, index lines `dropped` (they name no file) and files `converted`. Below the table come the conflicts, the history
files, the dropped lines word for word and what `needs a decision`, one per line. Quote these counts and lines as
they are; `--json` gives the whole answer. Claude Code writes its own memory in another form (the type nested under
`metadata:`, a name that is not the file name, a description of the content rather than of when to recall it);
whaat converts a loose group's files on the way, the same way every time, so never convert them yourself.

If the plan warns that the personal memory still sits at the memory root, this identity's folder holds an older
memory in place: on the live instance, `claude`'s folder is the private archive. Tell the user, and on their yes run
`whaat memory move-personal`. It moves that memory into `personal/` in one commit, keeping the history of tracked
files. Until then the import refuses to write the root.

## 3. The user chooses on the page

The choice is made on the identity's page, not here: give the `url` and say in one message
what the plan holds, group by group with its counts, the conflicts by name, and the target you propose for each loose
folder. The page shows whose memory it fills; the user picks the groups, may change a loose folder's layer,
and sends. If whaat started this session, Send types `/whaat:memory-migrate import plan=<id>` here; otherwise the
user pastes it. Import nothing before that call comes.

In the same message, propose what the import will not bring: a dropped line that points at a file or folder outside
memory (a todo list, a roadmap, an idea box) is a pointer the import loses, and an archive beside the personal source
(a journal, session reports, a decision log) has no memory naming it. Propose one reference memory for each, with its
layer, and save those through the whaat:memory skill after the import, on the user's yes.

## 4. Import (`import plan=<id>`)

`whaat memory import plan=<id>` imports what the plan holds: the groups the user chose and the layers they gave.
It prints one row per group (copied, same, conflicts, commit), the totals, and again the conflicts, dropped lines and
decisions left; `--json` gives the whole answer, each converted file's `notes` too. Each group is one commit. Never run
`migration-plan` again after the plan is made: every run keeps a new plan, and the page then shows that one. The sources' git dates (a file's own days where git has none) and outcome
lines come along, so validity counts from when a memory was really written, not from today.

## 5. Check the links, then report

The links that came with the sources come first, before any new one. The import copies store and personal files as
they are and follows only the names it renamed itself, so a link in an older form (kebab case, a missing or extra type
prefix, an old core name) stays broken. Run `whaat memory lint` and read its `broken-link` rows: where exactly one
memory matches, it suggests the current name. Lint leaves the personal dir out of its report, so read
`whaat memory dump dir=personal: purpose=save because="check the links after the import"` and the same with
`dir=personal:core` too, and check their links against the
memory's file names. Rewrite only the link's name, through the whaat:memory skill, with the rest of the file exactly
as the dump gave it (the dump adds one newline after each file); a core file only on the user's yes.

A memory in the wrong layer moves. A whole loose group whose files no later commit touched: `whaat memory revert` its
import commit, then `whaat memory import` with the same source and the new target on stdin
(`{"sources": [{"path": …, "kind": "loose", "target": "acme/shop"}], "groups": ["1:acme/shop"], "state": …}`), so its
dates and conversion come along. Otherwise file by file: save it at the new path with its current content and index
trigger, then `whaat memory delete` the old path; its validity then counts from that day. Never edit whaat's state
files by hand to carry dates: name the gap to the user instead. Links name memories, not paths, so a move breaks none;
check that they still resolve.

Tell the user, group by group, what came over and what did not:
- Conflicts: name each file, and leave the decision to the user. Both versions stay where they are.
- Dropped index lines, word for word. They are notes without a file. Offer to save the ones worth keeping through
  the whaat:memory skill.
- Unindexed files and rewritten lines.
- Each converted file's `notes`. Ask the user about each one; through the whaat:memory skill, apply only what they say.
- The default core files whaat added (`core_defaults`): the core had none of that name, so each is a short template.
- The core files whaat linked to each other (`core_linked`): the core belongs together, so each names the others.
- The links you fixed above, each with its old and new name, and any still broken with no match.
- Memories with no link (`unlinked`): links that came with the sources stay as they are; these have none to or from
  another memory. Read them and the memories they could belong with. Where the link is clear (one names, extends or
  depends on the other), add the `[[<name>]]` link yourself through the whaat:memory skill and list it in the report
  with its reason. Ask only about the doubtful ones, in one list with the reason each, and add those on the user's yes.
  A memory that belongs with none stays alone: that is a fine answer, so never force a link; name it in the report.
- Personal memory that belongs in a core file: a memory about who the user is goes with `user_profile`, one about
  working together with `user_working_relationship`, one about the agent itself with the `<agent>_self` file, one
  about a mistake that keeps coming back with `watch_list`. Name each such file and the core file you propose, in one
  list, and ask. On the user's yes, write its gist into that core file with a `[[<name>]]` link to it, through the
  whaat:memory skill; the memory itself stays where it is. A core file loads into every session, so nothing goes in
  without the user's word.

Then read the `CLAUDE.md` files that load in this setup, and search its settings files by name only, with
`grep -o` so that only the matched name prints (`CLAUDE_MEMORY_[A-Z_]*`, `WHAAT_[A-Z_]*`, the store path, the old
skills' names): a settings file holds tokens, so never print a line or a value from it. Name what still points at the
old memory: the old memory skills, a store path or a `CLAUDE_MEMORY_*` key, an import of a store's `MEMORY.md`, and a
session-end step that saves memory the old way. Report these and change nothing: whaat helps and warns, and the user
decides.

Never delete or edit a source after the import. It stays the user's fallback.

## How a turn ends

whaat's page follows this session by its last line. End a turn that asks the user something in text with the exact
line `[whaat] waiting for your answer`; end the turn that finishes the migration, with nothing left to ask, with
`[whaat] done`. A turn that waits for the page (the plan is made, the user chooses there) ends with neither.
