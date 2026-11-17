# Curation

Curation keeps the memory small and right: one fact in one file, at the right layer, nothing out of date, and a trigger that opens the file exactly when it is needed. The agent proposes changes in a report; you decide each one; the agent applies what you approved, as commits you can undo.

Run it when the memory has grown, when a memory turned out wrong, or when two memories say the same thing. Ask the agent to tidy the memory, or press **Start curation** on the app's **Memory** page.

## How a run goes

1. **Mechanical check (lint).** Whaat runs fixed rules over the memory, without judging content and without changing anything. It checks the memory without changing it: file names and headers, broken links, indexes that do not match their folder, near-duplicates by word overlap, memories over the size limit, and scores that turned uncertain or stale. When the `MEMORY_REPO_ROOTS` setting says where your clones are, it also flags memories that name files no longer in their repo.
2. **Judging.** The agent goes through every folder and proposes changes. Whaat writes the instructions for this step (the **brief**), so every run judges by the same words. A large folder goes to a separate helper agent that gets the brief as it is.
3. **Second opinion.** Another pass tries to refute each proposal from a different angle. A proposal it disproves is dropped, with the reason kept in the report.
4. **The report.** The proposals are saved as a curation report and opened in the app. Nothing has changed in the memory yet.
5. **You decide.** On the report page, each row is a proposed change with its reason and evidence. You mark it apply or reject, and can add a note that narrows it.
6. **Apply.** The agent applies the approved rows, each as its own commits, and writes the commits into the row. It runs the lint again at the end.

A proposal you rejected earlier is not made again, unless the memory changed since.

## What a row can propose

- **merge** two memories that say the same thing;
- **move** a memory to the layer it belongs to;
- **split** one that covers two triggers, or **trim** one that grew too long;
- **retrigger:** rewrite a trigger that keeps opening the memory for the wrong task;
- **verify** a stale memory: is it still true, and still needed? If it holds, it is marked confirmed today;
- **delete** a memory whose content the code or docs now hold, that was only the state of one conversation, or whose subject is gone;
- **fix** a statement that no longer holds, or a mechanical problem the lint found.

## Nothing is lost by shortening

Before a merge, split or trim is committed, Whaat lists every sentence of the old text and whether the new text still holds it word for word (the **fidelity** check). The agent accounts for each one that changed: where it moved, how it was reworded, or why it was only narrative. A clean lint proves the format, never that the meaning survived.

## Undoing

Every applied row records its commits. Reverting a row undoes them, newest first, in one run. If anything conflicts, nothing is changed and you are told why.

## Commands

The run is the `/whaat:memory-curation` skill. In the app, the **Memory** page starts it in a [terminal](terminal.md) session, and the report page sends your decisions back into that session. Starting it from the app needs the identity's Claude Code config folder, set in **Settings › Identities**.

| Skill call | What it does |
|---|---|
| `/whaat:memory-curation report` | Writes the report; changes nothing |
| `/whaat:memory-curation apply-rows report=<id>` | Applies the rows marked apply |
| `/whaat:memory-curation revert-applied-rows report=<id> rows=<n,…>` | Undoes applied rows |

The commands it uses:

| Command | What it does |
|---|---|
| `whaat memory lint` | The mechanical check; reads only |
| `whaat memory curation-brief dir=<dir>` | The judging instructions for one folder |
| `whaat memory curation-refute-brief dir=<dir>` | The second-opinion instructions for that folder's proposals |
| `whaat memory fidelity file=… new=…` | Sentence-by-sentence check after a merge, split or trim |
| `whaat journal save-curation` | Saves the report |
| `whaat journal save-applied` | Writes the commits into the applied rows |
| `whaat journal discarded` | Lists proposals you rejected earlier, and whether the file changed since |
| `whaat memory revert <commits>` | Undoes a row's commits |
