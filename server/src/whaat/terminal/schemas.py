from pydantic import BaseModel, Field


class TerminalSession(BaseModel):
    """One terminal: a tmux session of whaat's own tmux server, running the start command in the user's login shell."""

    name: str
    persona: str
    number: int
    created: int = Field(description="When tmux started it, in Unix seconds.")
    attached: int = Field(description="How many windows show it now.")
    cwd: str
    command: str
    label: str = Field(default="", description="A name the user gave it; empty if none.")
    program: str = Field(default="", description="The program in the foreground of its pane, as tmux names it.")
    idle: bool = Field(default=False, description="The start command has exited and only the shell waits.")
    asking: bool = Field(
        default=False, description="Claude Code waits in it for an answer to a dialog (trust, permission, a question)."
    )
    busy: bool = Field(default=False, description="Claude Code is working on a turn in it.")
    done: bool = Field(default=False, description="A whaat skill's last turn in it ended in `[whaat] done`.")
    tmux_id: str = Field(default="", description="tmux's own id of the session ($N), as recorded when it started.")
    gone: bool = Field(
        default=False,
        description="whaat recorded it, but tmux no longer runs it (tmux stopped, the machine restarted).",
    )


class TerminalSessions(BaseModel):
    command: str = Field(description="The start command a new session runs.")
    cwd: str = Field(description="The folder a new session starts in.")
    sessions: list[TerminalSession]


class RenameTerminal(BaseModel):
    label: str = Field(max_length=200, description="The new name; empty takes the name off.")


class TerminalFont(BaseModel):
    family: str = Field(description="A CSS font family; the app's SF Mono is ui-monospace.")
    size: float


class TerminalCursor(BaseModel):
    style: str = Field(description="block, underline or bar")
    blink: bool


class TerminalTheme(BaseModel):
    """A theme read from this machine's terminal apps, its colours as xterm names them."""

    id: str = Field(description='The source and the profile, e.g. "terminal-app:Clear Dark".')
    name: str
    source: str = Field(description="The app it comes from: Terminal or iTerm2.")
    default: bool = Field(default=False, description="The profile the app itself opens with.")
    colors: dict[str, str]
    font: TerminalFont
    cursor: TerminalCursor
    optionIsMeta: bool = Field(description="The Option key sends Meta (Esc+), as in the app's profile.")


class TerminalThemes(BaseModel):
    themes: list[TerminalTheme]


class TerminalApps(BaseModel):
    installed: list[str] = Field(description="The terminal apps of this machine a session can open in.")


class OpenNative(BaseModel):
    app: str | None = Field(default=None, description="terminal-app or iterm2; the saved preference when none.")


class NewTerminal(BaseModel):
    persona: str
    cwd: str | None = Field(default=None, description="The project folder to start in; the configured folder if none.")


class Folder(BaseModel):
    name: str
    repo: bool = Field(description="Whether it holds a .git, a hint that it is a project.")


class Folders(BaseModel):
    path: str
    parent: str | None
    folders: list[Folder]


class Project(BaseModel):
    path: str
    used: int = Field(description="When a session last started in it, in Unix seconds.")
    exists: bool


class Projects(BaseModel):
    projects: list[Project]
