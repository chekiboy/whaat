# Terminal

**Experimental:** it may change or break, and it is not finished.

The terminal runs agent sessions inside the app. You pick an identity and a project folder, and Whaat starts the agent there. It works as that identity when the identity has its own Claude Code config folder (see below); otherwise the session runs the plain start command. Curation and migration use it too: their pages start the agent in a terminal session and type your decisions into it.

## How sessions work

- **Each session runs in tmux,** on a tmux server of Whaat's own, so your own tmux is never touched. Closing the window leaves the session running; you can open it again later, also after restarting the Whaat server.
- **A session starts in a project folder** you pick from a folder browser. Folders you used are saved and offered first.
- **It runs a start command,** `claude` unless you set another in the settings, as `cd <project> && <command>`.
- **An identity can have its own Claude Code config folder.** A session for that identity then runs with that config and Whaat's plugin, and Whaat writes the identity's token into the config's settings, never onto the command line.
- **You can open a session in a terminal app** of your Mac (Terminal or iTerm2) instead of the app window. Both show the same session. The first time, macOS asks you to let Whaat control the app.
- **Stopping a session** ends it and what runs in it. Closing its window does not.

A session that tmux no longer has, for example after a restart of the Mac, is listed as gone until you remove it.

## How the app follows a session

The app watches the last lines of a session to know when to move you between a decision page and the terminal:
- **Migration** ends a turn that asks you something in the terminal with `[whaat] waiting for your answer`, and the finished run with `[whaat] done`. A turn that waits for your choice on the page ends with neither.
- **Curation** is closed from the report page: **Done** asks the agent to end the session, waits for its closing line `SESSION-END: nothing open`, then exits the agent.

## Safety

The terminal runs commands on your machine, so it needs the admin token. It also checks that the page opening a session is Whaat's own, because any website in your browser could try to connect to a local port.

## Settings

Under **Settings › Terminal**: the default start command, whether sessions open in the app or in a terminal app, the colour theme (Whaat's own, or your Terminal and iTerm2 profiles), and the saved project folders.
