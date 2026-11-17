# Command line

`whaat` is one command with subcommands. Every command that talks to the server starts it first if it is not running, so you rarely start it by hand. Commands that read or write an identity's memory or journal need that identity's token in `WHAAT_TOKEN`; without it they stop before sending anything.

Run it from the server folder with `uv run whaat …`, from anywhere with `uv run --project <whaat>/server whaat …`, or through the plugin's wrapper script `connectors/claude_code/scripts/whaat`, which needs nothing installed. `whaat --help` and `whaat <command> --help` show the same list with every option.

## Running Whaat

| Command | What it does |
|---|---|
| `whaat serve` | Runs the server in the foreground |
| `whaat ensure` | Starts the server in the background, unless it already runs |
| `whaat app` | Opens the app in its own window, without tabs or an address bar |
| `whaat open <report id>` | Opens a report in the app |
| `whaat show <report id>` | Prints a report as JSON |
| `whaat openapi` | Prints the API contract |

## Identities and connecting

| Command | What it does |
|---|---|
| `whaat connect <name> [--global]` | Connects Claude Code in this folder (or everywhere) as `<name>`; creates the identity if needed |
| `whaat identity add <name>` | Creates an identity and prints its token once |
| `whaat mcp` | Serves the identity's memory and journal to an MCP client |

More: [Identities](identities.md), [MCP layer](mcp.md).

## Memory

| Command | What it does |
|---|---|
| `whaat memory where [path]` | Where the memory of a folder lives; `--path store\|state\|personal` prints one location |
| `whaat memory index task="…"` | The triggers that apply to the current repo |
| `whaat memory open file=… because="…"` | Reads one memory and logs why |
| `whaat memory dump dir=… purpose=… because="…"` | Reads a whole folder, to tidy, review or save |
| `whaat memory save` | Saves a memory (JSON on stdin) and commits it |
| `whaat memory delete <path>` | Removes a wrong memory and its index line |
| `whaat memory reads` | What this session opened |
| `whaat memory record <outcome> <paths>` | Records whether recalled memories held, misled or were irrelevant |
| `whaat memory validity refresh` | Scores every memory |
| `whaat memory validity level <paths>` | The score and level of the named memories |
| `whaat memory revert <commits>` | Undoes memory commits |

More: [Memory](memory.md).

## Curation

| Command | What it does |
|---|---|
| `whaat memory lint` | The mechanical check; reads only |
| `whaat memory curation-brief dir=<dir>` | The judging instructions for one folder |
| `whaat memory curation-refute-brief dir=<dir>` | The second-opinion instructions for a folder's proposals |
| `whaat memory fidelity file=… new=…` | Sentence-by-sentence check after a merge, split or trim |
| `whaat journal save-curation` | Saves a curation report |
| `whaat journal save-applied` | Writes the commits into the applied rows |
| `whaat journal discarded` | Proposals you rejected earlier |

More: [Curation](curation.md).

## Migration

| Command | What it does |
|---|---|
| `whaat memory migration-groups` | What the sources would bring in; reads only |
| `whaat memory migration-plan` | Keeps the sources as a plan to choose from on the page |
| `whaat memory import plan=<id>` | Imports the chosen groups |
| `whaat memory move-personal` | Moves personal memory at the root into the personal layer |

More: [Migration](migration.md).

## Journal

| Command | What it does |
|---|---|
| `whaat journal save` | Saves a journal entry (JSON on stdin) |
| `whaat journal save-report` | Saves a session report, replacing that session's earlier one |

More: [Journal and session end](journal.md).
