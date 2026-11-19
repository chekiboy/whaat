# Claude Code plugin

The plugin connects Claude Code to whaat. Its skills tell the agent what to observe and write down; its hooks make sure the agent sees its memory at the right moments, without having to remember to look. `whaat connect` installs it (see [Identities](identities.md)).

The plugin is a thin layer: most skills and hooks call the Whaat server, which does the actual work. Without a token the hooks stay silent, except `memory-write-guard`, which still declines writes into Claude Code's own memory folders.

## Skills

The agent calls most of them on its own when the work fits. You can also call them yourself as `/whaat:<name>`.

| Skill | When it runs | What it does |
|---|---|---|
| `memory` | Something should outlast the session; at the end of a task | Saves, updates or deletes a memory; records how recalled memories went |
| `memory-recall` | Before every reply, and before a push, commit or cloud call | Lists the triggers that apply and opens the memories that fit |
| `memory-curation` | You ask to tidy the memory, or a memory proved wrong | Writes a curation report, then applies or reverts the rows you decided |
| `memory-migrate` | A new identity has an older memory on this machine | Brings that memory in, group by group, on your choice |
| `journal` | At session end, or when you ask for a session summary | Writes the journal entry and the session report |
| `decisions` | A run stops for your decisions | Puts the questions on a decisions page, waits until you send your answer and goes on from it |
| `session-end` | You end the session | Runs memory, skill proposals and journal, in that order |
| `skill-proposals` | A procedure was repeated during the work; at session end | Notes candidates, then proposes them as skills and asks |

Details: [Memory](memory.md), [Curation](curation.md), [Migration](migration.md), [Journal and session end](journal.md).

## Hooks

Hooks are small scripts Claude Code runs by itself at fixed moments, such as a session start or a file read. Whaat's hooks never stop the session: when they decline something, they answer with what to do instead.

| Hook | When | What it does |
|---|---|---|
| `session-start` | A session starts | Starts the server if needed; puts in the personal core, the memory index that recall gives (global, project, repo and personal triggers, in parts) and a map of the memory folders. The text comes in several parts, because Claude Code caps each hook's output |
| `session-start` (compact) | Before the context is compacted | Logs the compaction, so the core and the index are put in again after it; prints nothing |
| `subagent-start` | A helper agent starts | Gives it the global index, the memory map, and the core files marked for every agent |
| `memory-frame` | After a recall, and on each of your messages | Puts an opened memory into the context, once per agent, so the agent treats it as your rule rather than as tool output; reminds the agent to recall before replying |
| `recall-guard` | Before a file read | Declines a direct read of a memory file and names the recall command to use instead |
| `memory-write-guard` | Before a file write | Declines writes into Claude Code's own memory folders and says where the memory goes in Whaat |
| `memory-outcome` | After a file read | Logs a read of a memory, and warns when it is history, uncertain or stale |

## Why a recall rule in `CLAUDE.md` too

A plugin can bring skills and hooks, but not a standing instruction. `whaat connect` therefore adds a short rule to the config's `CLAUDE.md`: recall before every reply. The hooks remind the agent; the rule makes it a habit.
