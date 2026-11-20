# MCP layer

Use the MCP layer when your agent is not Claude Code, or when you want Whaat as tools rather than skills. It lets that agent work as a Whaat identity. `whaat mcp` is an MCP server that offers the same memory, journal and report calls the Claude Code skills make (decisions pages excepted: their answer reaches a session through a waiting command, not a tool call), so any client that runs MCP servers over stdio gets the same memory.


## How it works

- **One identity per server.** The server works as the identity whose token it gets in `WHAAT_TOKEN`. The admin token is refused for memory and journal calls, because it is nobody.
- **The core comes first.** When the client connects, Whaat's instructions carry an outline of the identity's core and ask the agent to call `identity_load` before its first reply. That call returns the whole core.
- **Calls are logged under the client's session** when the client names one (Claude Code does); otherwise each `whaat mcp` process keeps a session of its own.
- **The procedure is in words only.** Without the plugin's hooks, nothing forces the agent to recall before a task or to run curation in order. The instructions and the tool descriptions explain the steps, and the agent has to follow them.

`whaat mcp` starts the Whaat server if it is not running. A server that already runs keeps its version: after updating Whaat, restart the server, or the new calls are refused. Setup is in the main README, under "MCP layer".

## Tools

Tools marked **only on request** change or remove memory in commits; the instructions tell the agent to use them only when you asked for it.

**Identity and recall**

| Tool | What it does |
|---|---|
| `identity_load` | Returns the identity's personal core in full; called before the first reply and after the context was compacted |
| `memory_index` | Lists the triggers that apply to the current repo and the personal layer, in parts |
| `memory_open` | Reads one memory with its trust lines, and logs why it was opened |
| `memory_dump` | Reads a whole folder, to tidy, review or save; not a recall |
| `memory_where` | Says where the memory lives on disk; lists no memories |

**Saving and outcomes**

| Tool | What it does |
|---|---|
| `memory_save` | Saves a memory and its index line as one commit |
| `memory_delete` | Removes a wrong memory and its index line (only on request) |
| `memory_reads` | Lists what a session opened |
| `memory_record` | Records whether recalled memories held, misled or were irrelevant |

**Curation**

| Tool | What it does |
|---|---|
| `memory_lint` | The mechanical check; reads only |
| `memory_curation_brief` | The judging instructions for one folder |
| `memory_curation_refute_brief` | The second-opinion instructions for that folder's proposals |
| `memory_fidelity` | Sentence-by-sentence check after a merge, split or trim |
| `journal_save_curation` | Saves the curation report |
| `journal_save_applied` | Writes the commits into the applied rows |
| `journal_discarded` | Lists proposals the user rejected earlier |
| `memory_revert` | Undoes memory commits (only on request) |

**Migration**

| Tool | What it does |
|---|---|
| `memory_migration_plan` | Keeps the found sources as a plan for the user to choose from |
| `memory_import` | Imports the chosen groups, one commit each (only on request) |
| `memory_move_personal` | Moves personal memory at the memory root into the personal layer (only on request) |

**Journal and reports**

| Tool | What it does |
|---|---|
| `journal_save` | Saves a journal entry |
| `journal_save_report` | Saves a session report |
| `report_open` | Opens a report in the app on this machine and returns its address |

What each step means is on the module pages: [Memory](memory.md), [Curation](curation.md), [Migration](migration.md), [Journal](journal.md).
