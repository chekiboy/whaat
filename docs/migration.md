# Migration

Migration brings memory you already have into a Whaat identity, so the agent does not start from zero. It only reads the sources: your old memory keeps working, and stays your fallback.

Run it once, right after you create an identity, if you have an earlier memory on this machine.

## What it can bring in

- **A layered memory store:** global files at the root, then folders per group and per repo. Each layer comes in as one group.
- **A personal memory folder** with its core. It goes into the personal layer.
- **Loose folders:** Claude Code's own auto-memory (one per project folder) and a subagent's memory. Each goes to the layer you choose, by default the repo of the folder it was kept in.

Claude Code writes its memory in a slightly different form. Whaat converts those files on the way, the same way every time, and lists what it changed.

## How a run goes

1. **The agent finds the sources** and proposes a target layer for each loose folder. It reads a few files first: a folder that is plainly about the user, or about another project, gets that layer instead.
2. **Whaat makes a plan** and shows it on the identity's page: one row per group, with how many files are new, already in place, or in conflict.
3. **You choose** on that page which groups come in, and may change a loose folder's layer. Then you send.
4. **Whaat imports** the chosen groups, one commit per group. The files keep their original dates, so their scores count from when they were really written, not from today.
5. **The agent reports and tidies up:** it fixes links that point at old file names, and asks you about the rest.

## What is never overwritten

- A file already in place with the same content is skipped.
- A file in place with different content is a **conflict**: both versions stay as they are, and you decide.
- An index line that names no file is dropped from the import and listed word for word, so you can save the ones worth keeping.

## After the import

The agent's report lists, group by group, what came over and what did not, and handles:
- links between memories: it adds the clear ones itself and asks about the doubtful ones;
- personal memories whose gist belongs in a core file (only on your yes, since the core loads into every session);
- reference memories for things the import cannot carry, such as a journal or a to-do list kept next to the old memory.

It also names what in your setup still points at the old memory, such as old memory skills or settings, and changes none of it. You decide.

A memory that landed in the wrong layer can be moved afterwards. A loose folder's group that nothing changed since can be reverted and imported again with a new target.

## Commands

The run is the `/whaat:memory-migrate` skill. In the app, open the identity from **Settings › Identities** and start the migration there; it runs in a [terminal](terminal.md) session, and the page sends your choice back into it. Starting it from the app needs the identity's Claude Code config folder, set on the same page.

| Command | What it does |
|---|---|
| `whaat memory migration-groups` | Shows what the sources would bring in, group by group; reads only |
| `whaat memory migration-plan` | Keeps the sources as a plan for you to choose from on the page |
| `whaat memory import plan=<id>` | Imports the groups you chose, one commit each |
| `whaat memory move-personal` | Moves personal memory that still sits at the memory root into the personal layer, in one commit |
