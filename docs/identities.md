# Identities

An identity is one agent's own past: its memory, its journal and its reports, kept in a folder of its own. You need this page when you set up a new agent, connect a project to one, or run several agents side by side.

## One folder, one token

Each identity has:
- **a folder**, which is a git repository. Every save in it is a commit, so you can see and undo what changed. Inside it are the memory, the journal, the session reports and a `state/` folder for logs and scores, which git leaves out.
- **a token**, printed once when the identity is created. Whoever holds it reads and writes as that identity, and only that identity.

The app uses a separate **admin token**. It sees every identity, so the app can show them all, but it is nobody: it cannot write anyone's memory or journal.

An identity is not a model. The same identity can run on another model tomorrow and keep its memory.

## Connecting an agent

`whaat connect <name>`, run in a project folder, makes the Claude Code sessions started there work as `<name>`:
- it creates the identity if it does not exist yet;
- it puts the identity's token into the project's local Claude Code settings, never on screen;
- it adds Whaat's plugin to your Claude Code settings;
- it adds Whaat's recall rule to that config's `CLAUDE.md`, because a plugin cannot bring one;
- it starts the server if it is not running.

With `--global`, the token goes into your Claude Code settings instead, and the agent works as this identity in every project.

To try Whaat beside your usual Claude Code setup, connect a separate Claude Code config folder. The main README shows how, under "Try it next to your current setup".

## Several identities, several instances

You can keep as many identities as you like: one per agent, or one per kind of work. The Settings page lists them with their folders and counts.

Separately, Whaat itself can run as several **instances**, each with its own port, data folder and admin token. A trial instance (`WHAAT_INSTANCE=dev`) never writes into your real data unless `WHAAT_IDENTITIES` points it at those folders, and the command line refuses to talk to an instance other than the one it was pointed at.

## Commands

| Command | What it does |
|---|---|
| `whaat connect <name> [--global]` | Connects Claude Code in this folder (or everywhere) as `<name>` |
| `whaat identity add <name>` | Creates an identity and prints its token once; needs the admin token |

In the app: **Settings › Identities** lists the identities, creates new ones, gives one a new token (the old one stops working at once) and sets which one the app opens with. An identity can also get its own Claude Code config folder there, which the [terminal](terminal.md) uses.
