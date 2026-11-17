# The app

The app is where you look at an identity's past and decide what waits for you. It runs in a browser, or in a window of its own with `whaat app`, and is served by the Whaat server itself, so there is nothing else to run.

The app uses the same API as the agents, with the admin token; there is no separate way in. A few actions, such as the terminal, the settings and creating identities, need that admin token, so an agent working as an identity cannot do them.

## Pages

| Page | What you find there |
|---|---|
| **Home** | Who the identity is (its core), what happened on its last active days, and what needs you: memories to check (uncertain or stale) and memories getting old |
| **Memory** | Every memory, as a list by layer, as a 3D "brain" of memories and their links, or as rings with the core in the middle. Filter by layer, type and trust; click a memory for its text and connections. Curation starts here |
| **Reports** | Journals, session reports and curation reports, filtered by kind and by identity; see [Reports](reports.md) |
| **Terminal** | Agent sessions running in the app (experimental); see [Terminal](terminal.md) |
| **Settings** | Identities, the app's language, and the terminal's settings |
| **Bring memory in** | The migration page of one identity, where you choose what to import; see [Migration](migration.md) |
| **About** | What Whaat is and where it is heading |

The identity switcher changes which identity the pages show. A link that names an identity opens that one. `⌘K` opens a palette that searches the memory and the commands. The status bar shows the running version, and the app can restart or stop the server.

## Settings

- **Identities:** the list with each identity's folder, memory and report counts; creating a new one; giving one a new token (the old one stops working at once); which identity the app opens with (a fixed one, or the last used); and an optional Claude Code config folder per identity, for the [terminal](terminal.md).
- **General:** the app's language, English or Hungarian. Memories, journals and reports stay in the language they were written in.
- **Terminal:** the start command, where sessions open, the colour theme, and the saved project folders.

The settings are kept per Whaat instance, in its data folder.
