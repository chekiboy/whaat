from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Language = Literal["en", "hu"]
BUILT_IN_THEMES = ("whaat", "solarized-dark", "dracula", "light")
# a built-in theme, or one read from this machine ("terminal-app:<profile>", "iterm2:<profile>")
Theme = Annotated[
    str, StringConstraints(pattern=r"^(whaat|solarized-dark|dracula|light|(terminal-app|iterm2):.{1,120})$")
]


Opener = Literal["browser", "terminal-app", "iterm2"]


class SavedProject(BaseModel):
    path: str
    used: int = Field(description="When a session last started in it, in Unix seconds.")


class TerminalPreferences(BaseModel):
    command: str = Field(description="The command a new session runs: the saved one, or the default.")
    default_command: str = Field(description="The command when none is saved (WHAAT_TERMINAL_COMMAND, else claude).")
    theme: Theme = "whaat"
    opener: Opener = Field(default="browser", description="Where a session opens: here, or a terminal app.")
    projects: list[SavedProject] = Field(default_factory=list)


# "last", or an identity's id (the same pattern as whaat.config.IDENTITY_ID)
OpenWith = Annotated[str, StringConstraints(pattern=r"^(last|[A-Za-z][A-Za-z0-9-]{0,31})$")]
IdentityId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9-]{0,31}$")]


class IdentityPreferences(BaseModel):
    open_with: OpenWith = Field(
        default="last", description='The identity the app opens with: "last", the one used last, or a fixed one.'
    )
    last: str | None = Field(default=None, description="The identity chosen last in the app; null before the first.")
    agents: dict[str, str] = Field(
        default_factory=dict,
        description="An identity's own Claude Code config dir: a terminal session of that identity starts claude"
        " with it, whaat's plugin and the identity's token.",
    )


class Preferences(BaseModel):
    """What the UI remembers, in one file per instance."""

    language: Language = "en"
    identity: IdentityPreferences = Field(default_factory=IdentityPreferences)
    terminal: TerminalPreferences


class TerminalPatch(BaseModel):
    command: str | None = Field(default=None, description="An empty string goes back to the default.")
    theme: Theme | None = None
    opener: Opener | None = None


class IdentityPatch(BaseModel):
    open_with: OpenWith | None = None
    last: IdentityId | None = None
    agents: dict[IdentityId, str] | None = Field(default=None, description="An empty path takes an agent config off.")


class PreferencesPatch(BaseModel):
    language: Language | None = None
    identity: IdentityPatch | None = None
    terminal: TerminalPatch | None = None
