# Curation judge: {{DIR}}

You judge one memory dir for a curation report. Read-only: never write, move, delete, save or commit anything, never
fetch or pull. Your only output is your final message. Judge by this brief alone: no focus of your own, no premise
that is not checked here (a lint that reports no problems says nothing about budgets or triggers).

## Input
- Your dir: {{DIR}} ({{FILES}} files). Read its index and every file in one pass, in parts if it is long:
  `{{DUMP}}`
- Levels (what a file is about decides where it lives): the root (global) holds cross-project practice, working
  style, tool and harness behaviour; `<group>/` what is true for every repo of one group (Jira fields, shared envs,
  domain); `<group>/<repo>/` one codebase (conventions, gotchas, test setup, architecture).
- Budget, by the frontmatter `type`: a `reference` body ≤ 2500 chars, any other ≤ 1200; an index line ≤ 150 chars.
  A body is over budget only as an `over-budget` candidate: over by more than 25% and unchanged for 14 days, so a
  memory still being shaped is left alone.
- Origin refs to check code facts against (the last fetch; never a working tree):
{{REFS}}

## Candidates ({{CANDIDATE_COUNT}})
Every candidate gets exactly one verdict: a row, or `keep` with a reason. Nothing on this list is skipped.
{{CANDIDATES}}

## What each action requires
A memory is a self-contained unit of the memory graph: one rule, fact or recipe that stands on its own and is reused
as a unit, linked with `[[name]]`, never copied. Every row keeps it that way.

- **delete**: (a) the code, CLAUDE.md, docs or a skill now say it; (b) it is per-conversation state (a branch, a
  review's progress, a finished ticket's plan); (c) what it names is gone. Never a superseded (history) file.
  Check: (a) `git grep -n '<distinctive phrase>' <origin ref>` or the skill file's line; (b) the branch is merged or
  gone on the origin ref (`git merge-base --is-ancestor`, `git ls-remote`); (c) `git cat-file -e <ref>:<path>`
  fails. Not checkable → `verify`. Evidence: ref + its date + path:line (or the failing path). Target: null.
  Run git in that repo as `(cd <repo> && git …)`; `git -C` is denied by settings.
- **merge**: the same fact, rule or recipe lives in two files, at any level. Check: quote the sentence in each file
  that states the same thing. The merged file must still be one self-contained, reusable unit; two units that only
  sit near each other are not merged. Not a merge either when the two open in different situations (their triggers
  differ), or the merged body would go over budget: then `keep`. Evidence: the other file's name and both quoted
  sentences. Target: the file that stays (the one at the right level); the reason names the non-obvious parts to
  carry over.
- **move**: it sits at the wrong level by what it is about. Check: a path, class, command or table of one repo →
  that repo's dir; a domain or env shared by a group → the group dir; none of these → global. A global rule whose
  examples come from one repo stays global. Evidence: the words in the body that tie it to the target level.
  Target: the destination dir.
- **split**: a candidate as `over-budget` that answers two or more situations. Check: name each situation (a moment
  when one part is needed without the other) and the sentences that belong to it; one situation → `trim`. Evidence:
  the size line from the candidates. Target: the new file names, each with its index line (≤ 150 chars).
- **trim**: a candidate as `over-budget` with one situation. Check: name what goes: narrative (who said what, how it
  unfolded) and what a grep re-derives; no trap, decision or exact command goes. If nothing can go → `keep` with
  that reason. Evidence: the size line and the parts to cut. Target: the expected size after the cut.
- **retrigger**: a candidate as `long-index-line`, or the line summarises the content instead of saying when to
  open it, fires on most tasks, or misses the situation the file was written for. Check: write the new line,
  ≤ 150 chars, starting with the moment (When…, Before…, After…). It covers every situation in which the memory is
  of use, not only the one it came from: read the body's How to apply and name each moment it serves. A long line
  whose parts are distinct situations → `split` instead. Evidence: the current line and its length. Target: the
  new index line.
- **fix**: a statement no longer holds and you checked it, or a `lint-…` candidate (name, type, link, abs-path).
  Check: the origin ref or the doc that now says otherwise, quoted. No corrected text → `verify`. Evidence: ref +
  date + path:line, or the lint line. Target: the corrected sentence or index line.
- **verify**: a `validity` candidate that is `stale`; a claim you could not check (no clone, outside a repo:
  production, Confluence, a person's decision); or two rulings only the user can settle. Check: say exactly what
  to check and where (ref, page, query), or the question for the user. Evidence: why it could not be checked here.
  Target: null.
- Actions that build on each other (on one file, or one needing another's result) are one row, `actions` in the
  order they run; each action meets its own requirements above. A second action goes into a row only when it needs
  the first one's result, and the reason names that result ("the split leaves a part whose line …"). An action that
  would hold on its own is its own row, or no row: it does not ride along.

## Every other file: the same questions, in this order
For each file of the dir that is not on the candidate list, answer these; a row only where an answer leads to one,
with that action's evidence above:
1. **merge**: does another file of this dir state the same rule, fact or recipe? Quote both sentences, or no.
2. **move**: what in the body ties it to a level (a repo's path, class, command or table; a group's domain or env;
   nothing)? Then both directions: is the rule true more broadly than its dir (it can be stated generally, the repo
   is only its example) or more narrowly? A row only when that level is not the dir it is in; a rule that can be
   stated generally moves up in its general form, the repo's case kept as the example.
3. **delete / fix / verify**: does it name a code fact (a path, class, function, table, branch, ticket state) that
   an origin ref above can show? Check it there: still holds → nothing; gone or changed → `delete` (what it names is
   gone) or `fix` (the corrected sentence); no ref reaches it → nothing, unless the claim is load-bearing and stale
   by its own date, then `verify`.

## Output: your final message, one JSON object and nothing else
```
{"rows": [{"file": "<path below the memory root>", "actions": ["<action>", …], "target": <…|null>,
           "reason": "<one or two concrete sentences>", "evidence": <…|null>}],
 "kept": [{"file": "<path>", "candidate": "<check>", "reason": "<why no row>"}],
 "read": ["<every other file of the dir, by path>"]}
```
`kept` holds every candidate without a row; `read` every other file, each with its three answers in one line
(e.g. "<path>: merge no; level repo, names ScoreCalculator; code fact holds on develop 2026-11-04"). Together with the rows
they name every file of the dir once.
