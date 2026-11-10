# whaat server

The Python JSON API and CLI. Use this page to run the server, work on it, and look up its settings.

## Commands

```
uv sync
uv run whaat serve      # run in the foreground
uv run whaat ensure     # start in the background unless it already runs
uv run whaat app        # start if needed and open the UI in an app window
uv run whaat connect <name>  # connect Claude Code in this folder as <name> (--global: every project)
uv run whaat openapi    # print the API contract
uv run whaat --help     # every command: identity, memory, journal, …
```

## Checks before a push

```
uv run ruff format && uv run ruff check
uv run mypy src
uv run pytest
uv run whaat openapi > ../openapi.json   # then `pnpm api` in ui/ when it changed
```

A route's docstring is part of the contract, so a changed docstring also means a new `openapi.json` and a new UI client.

## Access

Every API call except health needs `Authorization: Bearer <token>`.

- **The admin token** is the `token` file in the state folder. It sees every identity, adds identities (`whaat identity add <name>`, or `whaat connect <name>`) and is the token the UI uses. It names no identity, so it cannot write anyone's journal or memory.
- **An identity's token** is printed once when the identity is added. The CLI and the Claude Code plugin read it from `WHAAT_TOKEN`; it reads and writes only that identity's folder.

## Data

Each identity has its own folder, a git repository: `memory/` (the layers, with `personal/` and its `core/`), `journal/`, `session-reports/`, an optional `distilled/` (data for the analysis views) and `state/` (logs, scores and migration plans, outside git). A `.private` file marks what is never shared, even once sharing between identities comes. On an instance other than `live`, identities live under `<state folder>/identities/<name>` unless `WHAAT_IDENTITIES` names their folders.

## Settings

Each setting is read from the environment, else from the `env` block of the Claude Code settings file (`$CLAUDE_CONFIG_DIR/settings.json`, or `~/.claude/settings.json`).

| Setting | What it does | Default |
|---|---|---|
| `WHAAT_INSTANCE` | Names the instance; any name other than `live` gets its own port, state folder and host name | `live` |
| `WHAAT_PORT` | The port | `1111` for `live`, `1112` otherwise |
| `WHAAT_HOST` | The address the server binds and the CLI calls | `127.0.0.1` |
| `WHAAT_HOSTNAME` | The host name in the URLs a browser opens | `whaat.localhost`, `<instance>.whaat.localhost` |
| `WHAAT_STATE_DIR` | The state folder: admin token, identity tokens, preferences, terminal sessions, server log | `~/Library/Application Support/whaat[-<instance>]` |
| `WHAAT_DEFAULT_IDENTITY` | The identity a new install works with | `wHaat` |
| `WHAAT_IDENTITIES` | A JSON object of identity name → its folder | none |
| `WHAAT_TOKEN` | The calling identity's token, for the CLI and the plugin | none |
| `WHAAT_UI_DIR` | A built UI to serve instead of `ui/dist` (served as it is, never rebuilt) | `ui/dist` |
| `WHAAT_TERMINAL_COMMAND` | What a new terminal session runs | `claude` |
| `WHAAT_TERMINAL_CWD` | The folder a new terminal session starts in | the home folder |
| `MEMORY_REPO_ROOTS` | Colon-separated folders where the memory lint looks for local clones, to check the paths memories name | none |
| `WHAAT_LIVE_IDENTITIES` | A JSON object of identity name → its folder, read on the `live` instance only | none |
| `WHAAT_SHARED_REPORTS` | Shared folders whose reports the UI also lists: a JSON object of a short key → `{"path": folder, "dirs": [report folders below it]}` | none |
| `WHAAT_BROWSER` | The browser `whaat open` uses | the default browser |

Several instances can run side by side: each binds its own port, and the CLI refuses a server that names another instance, so a trial never writes into the live data.
