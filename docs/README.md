# Whaat, module by module

One page per module, each saying what the module is for, how it behaves and which commands belong to it. The pages explain; they do not document the code. For installing and starting Whaat, see the [main README](../README.md); for the server's settings, see [`server/README.md`](../server/README.md).

| Page | What it covers |
|---|---|
| [Identities](identities.md) | Who the agent is: an identity's folder, its token, and connecting an agent to it |
| [Memory](memory.md) | What the agent remembers: layers, saving, recall, and how far a memory can be trusted |
| [Curation](curation.md) | Keeping the memory tidy: a report of proposed changes that you decide on |
| [Migration](migration.md) | Bringing memory you already have into Whaat |
| [Journal and session end](journal.md) | What the agent writes down when a session ends |
| [Reports](reports.md) | Where journals, session reports and curation reports show up, and how to open them |
| [Claude Code plugin](claude-code-plugin.md) | The skills and hooks that connect Claude Code to Whaat |
| [MCP layer](mcp.md) | The same memory and journal for any MCP client |
| [Command line](cli.md) | Every `whaat` command in one list |
| [Terminal](terminal.md) | Agent sessions that run inside the app (experimental) |
| [The app](app.md) | The pages of the UI and its settings |

## Words used on every page

- **Identity:** one agent's own memory, journal and reports, kept in a folder of its own. An agent "works as" an identity.
- **Memory:** a short markdown file the agent wrote, with a trigger that says when to read it again.
- **Layer:** where a memory applies: everywhere, a group of repos, one repo, or the personal layer about the user.
- **Core:** the few personal memories that every session reads at its start.
- **Recall:** the agent reading the memories that fit its current task.
- **Token:** the key an agent or the app uses to talk to whaat. It decides which identity the caller is.
