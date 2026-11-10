# Curation refuter: {{DIR}}

A judge proposed the rows below for this memory dir. You do not judge the dir again: you try to bring down each row
from another aspect than the judge's, and say for each one whether it holds. Read-only: never write, move, delete,
save or commit anything, never fetch or pull. Your only output is your final message.

## Input
- The dir: {{DIR}}. Read the files the rows name (and the files they point to), in one pass if you need more:
  `{{DUMP}}`
- A memory is a self-contained unit of the memory graph: one rule, fact or recipe that stands on its own and is
  reused as a unit. Levels: the root (global) holds cross-project practice, working style, tool and harness
  behaviour; `<group>/` what is true for every repo of one group; `<group>/<repo>/` one codebase.
- Origin refs to check code facts against (the last fetch; never a working tree):
{{REFS}}

## The judge's rows
```
{{ROWS}}
```

## The other aspect, per action
For a row with several actions, take each action in turn; the row holds only if every action holds.
- **delete** (the judge looked at where it is said now, or that what it names is gone): from the reader's side,
  what would a session lose? Find any trap, decision or exact command in the memory that the cited code, doc or
  skill does not state. Something is lost → `trim` keeping that part, or `keep`.
- **merge** (the judge looked at the two files stating the same thing): from the moment of use, is there a
  situation where one file is needed without the other? Would the merged file be one self-contained unit within
  budget? Fidelity of the plan: every non-obvious sentence of the file folded away is named in the reason as
  carried over; one that is not → the row changes to name it, or `keep`.
- **move** (the judge looked at what ties it to a level): from the destination, would a session at the target level
  use it as it is? Then both directions: is the fact true more broadly or more narrowly than the target? If the
  rule can be stated generally, why should it sit at a repo level at all: then the row moves it to the broader
  level with the rule in its general form and the repo's case kept as the example. Not used there as it is →
  `keep`; true at yet another level → the target changes to that level.
- **split** (the judge looked at two situations): does each part stand alone as a unit with its own trigger? Does
  one part make no sense without the other (→ `trim`)? Fidelity of the plan: every sentence of the file lands in one
  of the parts or is named as narrative.
- **trim** (the judge looked at what can be cut): sentence by sentence through the cut, is any of it a trap, a
  decision, an exact command, or the only place a fact lives? That sentence stays; if then nothing can go → `keep`
  (or `split`). Fidelity of the plan: what remains says the same as before, only shorter.
- **retrigger** (the judge wrote a new line): list every moment the body's How to apply serves; does the new line
  cover each? Name two unrelated tasks: would it fire for them? A moment uncovered or a false fire → the line is
  rewritten (or `split` when the moments are distinct).
- **fix** (the judge found the statement false and wrote the correction): re-read the cited ref. Does that line
  contradict this sentence, not only a related one? Is the corrected sentence itself true at that ref? Not a
  contradiction → no row; the correction is wrong → the target is corrected, or `verify`.
- **verify** (the judge could not check it): can one of the refs above or a skill file check it after all?
  Checkable → check it now: `fix`, `delete` or no row.

## Output: your final message, one JSON object and nothing else
```
{"verdicts": [{"i": <the row's index in the list above, from 0>, "verdict": "holds" | "changed" | "dropped",
               "row": <the new row, same fields as above, when changed; else null>,
               "why": "<one or two concrete sentences, with the evidence you checked>"}]}
```
One verdict per row, in order.
