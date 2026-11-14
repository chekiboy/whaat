# Changelog

What changed in each version of whaat. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0, a new minor version (0.2, 0.3) may change the API, the CLI or the file formats.

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
