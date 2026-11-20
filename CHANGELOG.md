# Changelog

What changed in each version of whaat. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0, a new minor version (0.2, 0.3) may change the API, the CLI or the file formats.

## Unreleased

### Changed

- **Validity fades four times faster.** A memory's score now loses 0.2 per 30 days instead of per 120 days since its latest anchor (`confirmed`, the last `held` outcome, the first commit). A memory nobody confirms or uses successfully reaches `stale` within two to three months instead of about a year; a confirmation or a successful use restarts the clock as before.

## 0.3.1 (2026-11-17)

### Added

- **Paged recall index.** `memory index` (and `memory_index` over MCP) returns the index in parts, each under a client's output limit, with a digest of the whole index. Passing the digest back as `known=` answers an unchanged index in one line. The last part names the parts this session has not read yet, and an agent that has not read every part itself is asked to read it again.
- **Session start and compaction.** The SessionStart hook puts in the whole personal core and the index parts; a new PreCompact hook logs a compaction, so both are put in again after it.
- **Recall rule in `CLAUDE.md`.** `whaat connect` puts Whaat's recall rule at the top of the config's `CLAUDE.md`, between `<memory_handling>` tags; connecting again replaces only that block.
- **An opened memory ends with its own trust and its links:** the index lines and trust of the memories it links to, not their text.
- **Documentation.** `docs/` explains each module on its own page. The README opens with what Whaat is, then quick facts, security and privacy, our own measurements and an FAQ.
- **API.** `POST /api/v1/memory/recall/index` takes `known` and `part`, and answers with `digest`, `part`, `parts`, `missing`, `text` and `footer`.

### Changed

- **The recall skill says per trust level what to do:** follow a `certain` memory; follow a `likely` one and name where the code, the docs or another memory says otherwise; ask the user about an `uncertain` one that something contradicts; check a `stale` one against the code first; treat an inferred one as a hypothesis.
- **Recall before every reply.** The reminder asks for a recall on every user message, not only on a message that starts a task.
- **The journal, curation and migrate skills** name every branch of a conditional step.
- Bumped the project version to 0.3.1.

## 0.3.0 (2026-11-16)

### Added

- **MCP layer.** `whaat mcp` serves the calls the Claude Code skills make over MCP (stdio), as the identity whose token it gets in `WHAAT_TOKEN`. Its instructions carry an outline of the identity's personal core, and `identity_load` returns the whole core.
- **API.** `POST /api/v1/reports/{id}/open` opens a report in the UI. `GET /api/v1/memory/where` takes `key=<project>/<repo>` and names that project's and repo's folders. `recall/frame` takes `uncapped`, `recall/start` takes `outline`, and the two curation briefs take `dump` (`cli` or `mcp`).

### Changed

- **Saving a memory** returns what memory-lint finds in the saved file among its warnings; the save itself still goes through.
- **The outcome and read logs** record the time of each line, not only the day.
- **`memory record`** says that personal memories are not scored when it skips one.
- **The memory skill** asks to set `confirmed` after fixing what a memory says, since an edit alone does not reset its age.
- Bumped the project version to 0.3.0.

### Fixed

- An outcome recorded on the same day as a memory's last change, after it, now counts in "since its last change" and in memory-lint's misled and noisy lists.
- An Applied cell can no longer be written on a curation row the user did not decide as apply.

## 0.2.0 (2026-11-14)

### Changed

- **License.** This version is licensed under Business Source License 1.1 (BUSL-1.1), with no Additional Use Grant, a Change Date of 2030-11-14, and GPL-2.0-or-later as the Change License. Version 0.1.0 remains under Apache License 2.0.
- Bumped the project version to 0.2.0.

## 0.1.0 (2026-11-10)

The first version. It runs on macOS and connects to Claude Code.

### Added

- **Memory in layers.** Memories are markdown files with a trigger, kept at the level they are true for: everywhere, a group of repos, one repo, or the personal layer with its core. Each save and delete is a git commit.
- **Recall.** Hooks show the agent the core and the triggers that fit the repo it works in, and hand it a memory when it opens one. Each memory has a score that fades with age unless the memory is confirmed or proves right in use.
- **Curation.** A check and a report propose merges, moves, trims and fixes; you decide each on a page, and the agent applies them as commits you can undo.
- **Migration.** Brings in an existing memory store, a personal folder, Claude Code's auto-memory and a subagent's notes, and converts Claude Code's files to whaat's form. The sources are only read.
- **Journal and session reports.** The agent writes them at the end of a session; whaat keeps them in the identity's private folder.
- **Identities.** Each has its own folder, git history and token; the admin token, which the UI uses, sees all of them.
- **The app.** A home page per identity, the memory as a list, a brain and rings, the reports, the curation and migration pages and the settings, in English and Hungarian. The terminal that runs agent sessions in tmux is an experiment.
- **The Claude Code plugin.** Seven skills (`memory`, `memory-recall`, `memory-curation`, `memory-migrate`, `journal`, `session-end`, `skill-proposals`) and the hooks behind recall.
- **The CLI.** `whaat app`, `whaat ensure` and `whaat serve` run the server; `whaat connect <name>` connects Claude Code in a folder as an identity; the memory, journal and identity commands do what the skills call.
- **Instances.** Several whaat instances can run side by side, each with its own port, state folder and token.
