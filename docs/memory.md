# Memory

The memory module is what the agent remembers between sessions. The agent decides what is worth keeping and writes it; Whaat checks it, saves it as a commit and puts it back in front of the agent when a task calls for it.

## A memory is a short note with a trigger

Each memory is a small markdown file: a rule or a fact in one to three sentences, why it matters, and how to apply it. Its most important part is the **trigger**, one line that says *when* the memory should be read, not what it says. For example: "Before pushing to the shared remote".

There are three kinds:
- **feedback:** how to work ("run the linter before every commit");
- **project:** a fact about a codebase or a domain ("this service keeps prices in cents");
- **reference:** a recipe or a pointer ("how to reset the local database").

## Layers: where a memory is true

A memory lives at the level it holds for:

| Layer | Holds | Example |
|---|---|---|
| Global | What is true everywhere | "Ask before deleting a branch" |
| Project | What is true for a group of repos | Shared environments, a team's ticket fields |
| Repo | What is true for one codebase | Its test setup, its traps |
| Personal | The user, the agent itself, and how they work together | "The user wants short answers" |

The personal layer has a **core**: a few files read at the start of every session, so the agent knows who it is and who it works with before its first reply.

Whaat finds a repo's layer from its git remote: `…/acme/shop.git` becomes `acme/shop`. A new project or repo needs no setup; its folder appears with its first memory.

Each folder has an index, `MEMORY.md`, with one line per memory: the file name and its trigger. The index is what the agent scans; it opens only the files whose trigger fits.

## Recall: reading the right memory at the right time

Recall happens in two steps:
1. **index:** the agent says what it is doing, and Whaat lists the triggers of every layer that applies to the current repo. A long index comes in parts.
2. **open:** for each trigger that fits, the agent opens that memory and says which words of the trigger matched which part of the task.

Every open is logged with its reason, so you can later see which trigger fired for which task. A memory the agent recorded as irrelevant twice or more shows up in [curation](curation.md) as a trigger to rewrite.

A third call, **dump**, reads a whole folder at once. It is meant for tidying or reviewing memory, not for recall, and is logged as such.

## Trust: how far a memory can be relied on

A recalled memory arrives with two lines that tell the agent how much to rely on it.

**Truthness** says what backs the memory, and how it went since its last change:
- its source: `measured`, `user-decision`, or `inference` (the agent's own conclusion);
- how many times it **held** (it was used and proved right), **misled** (it was wrong or out of date) or was **irrelevant** (it opened for a task it did not fit).

**Validity** is a score that fades with age. It starts from the source (1.0 for measured or user-decided, 0.75 for an inference, 0.9 when none is given) and loses 0.2 every 120 days. The clock restarts whenever the memory is confirmed or holds in use. The score gives a level:

| Level | Score | What the agent does |
|---|---|---|
| certain | 0.8 and above | Follows it |
| likely | 0.6 to 0.8 | Follows it; where the code, the docs or another memory says otherwise, it names the difference. The home page lists it as getting old |
| uncertain | 0.4 to 0.6 | Where something says otherwise, asks you before acting on it; where nothing does, follows it and names its age. The home page lists it to check |
| stale | below 0.4 | Checks it against the code first, then asks you or follows it as for uncertain; curation asks whether it still holds |

A memory backed only by an inference is treated as a hypothesis and checked first. Whatever the level, a step that is hard to undo waits for a check or a question to you.

A memory that was replaced by a newer one becomes **history**: it stays in the folder so the change can be traced, but the agent never acts on it. Personal memories are not scored.

At the end of a task the agent records, for each memory it recalled, whether it held, misled or was irrelevant. Only "held" refreshes a memory's score; reading it alone does not.

## Saving

The agent saves a memory when the work taught something that should outlast the session, above all a correction or a decision from the user. Before saving, it looks for an existing memory on the same subject and updates that instead of adding a near-copy.

Whaat writes the file and its index line together, as one commit. A memory that was simply wrong is fixed or deleted; one that held until the user changed course is replaced by a new one that names it, so the old one becomes history.

Direct writes elsewhere are redirected. If the agent tries to write into Claude Code's own memory folders, a hook tells it where the memory belongs in whaat.

## Commands

Through the plugin, the agent uses the `/whaat:memory` and `/whaat:memory-recall` skills; it rarely needs to be asked. The commands underneath:

| Command | What it does |
|---|---|
| `whaat memory where [path]` | Shows where the global, project and repo memory of a folder live |
| `whaat memory index task="…"` | Lists the triggers that apply to the current repo |
| `whaat memory open file=… because="…"` | Reads one memory and logs why |
| `whaat memory dump dir=… purpose=… because="…"` | Reads a whole folder, to tidy, review or save |
| `whaat memory save` | Saves a memory and its index line as one commit |
| `whaat memory delete <path>` | Removes a wrong memory and its index line |
| `whaat memory reads` | Lists what this session opened |
| `whaat memory record <held\|misled\|irrelevant> <paths>` | Records how the recalled memories went |
| `whaat memory validity refresh` | Scores every memory |
| `whaat memory validity level <paths>` | The score and level of the named memories |
| `whaat memory revert <commits>` | Undoes memory commits; a conflict cancels the whole run |

In the app, the **Memory** page shows every memory as a list, as a 3D "brain" of memories and their links, or as rings around the core, with filters by layer, type and trust.
