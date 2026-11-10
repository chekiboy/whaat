"""The terminal's sessions live in tmux, on a tmux server of whaat's own (one per instance), so a closed window leaves
its session running and it can be opened again, and the user's own tmux is never touched."""

import os
import re
import shlex
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from whaat.config import IDENTITY_ID, Settings

FALLBACK_PATHS = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin")
DROPPED_ENV = ("CLAUDE_", "WHAAT_", "TMUX")
MAX_LABEL = 60
SHELLS = {"zsh", "bash", "sh", "fish", "dash", "ksh", "tcsh", "csh", "login"}
# the persona part is an identity id as whaat.config.IDENTITY_ID allows it, capitals included (wHaat)
SESSION_NAME = re.compile(r"^whaat-(" + IDENTITY_ID.pattern.strip("^$") + r")-(\d+)$")
# Claude Code's screen while a turn runs ("● Concocting… (2s · ↓ 16 tokens)"; older: "esc to interrupt")
BUSY = re.compile(r"\S…\s*\((?:\d+m\s*)?\d+s\b|esc to interrupt")
# Claude Code waiting for an answer: a dialog's footer or its permission question; a countdown that goes on by itself
# ("Continuing automatically · Esc to cancel") waits for nobody
ASKING = re.compile(r"Enter to (?:confirm|select)|Do you want to proceed\?|Esc to cancel")
GOES_ON = re.compile(r"Continuing (?:automatically|shortly)")
# the line a whaat skill ends its turn with: it asked in text and waits, or it is done; the last one on screen counts
TURN_MARK = re.compile(r"\[whaat\] (waiting for your answer|done)\b")
SGR = re.compile(r"\x1b\[[0-9;]*m")
DIM = re.compile(r"\x1b\[2m.*?(?:\x1b\[(?:0|22)m|$)")
PROMPT_MARK = "❯"  # noqa: RUF001 - Claude Code's prompt mark
READBACK_SECONDS = 0.4


def waits_for_answer(screen: str) -> bool:
    """Whether a visible Claude Code screen waits for the user: a dialog (trust, permission, a question), or a skill's
    turn ending in `[whaat] waiting for your answer`."""
    if BUSY.search(screen) or GOES_ON.search(screen):
        return False
    return bool(ASKING.search(screen)) or last_mark(screen) == "waiting for your answer"


def last_mark(screen: str) -> str | None:
    marks = TURN_MARK.findall(screen)
    return marks[-1] if marks else None


def says_done(screen: str) -> bool:
    """Whether a skill's last turn on screen ended in `[whaat] done` and nothing runs since."""
    return not BUSY.search(screen) and last_mark(screen) == "done"


class TmuxMissingError(RuntimeError):
    pass


class TypingError(RuntimeError):
    """Nothing was sent: the session has no prompt, holds unsent text, or did not show the typed text."""


class SessionNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class Session:
    name: str
    persona: str
    number: int
    created: int
    attached: int
    cwd: str
    command: str
    label: str = ""
    program: str = ""
    tmux_id: str = ""
    gone: bool = False

    @property
    def idle(self) -> bool:
        """The start command has exited and only the shell waits (tmux shows the pane's foreground program)."""
        return self.program.lstrip("-") in SHELLS


def session_env() -> dict[str, str]:
    """The environment a session starts with: the server's, without its own keys or the agent's that started it (a
    `claude` inside must not inherit this server's token or a running session's ids), with a PATH that finds tmux
    and the user's tools even when the server was started by the app (launchd's PATH is minimal)."""
    env = {key: value for key, value in os.environ.items() if not key.startswith(DROPPED_ENV)}
    path = env.get("PATH", "").split(os.pathsep)
    env["PATH"] = os.pathsep.join([*path, *(p for p in FALLBACK_PATHS if p not in path)])
    env["TERM"] = "xterm-256color"
    env.setdefault("LANG", "en_US.UTF-8")
    env.setdefault("SHELL", "/bin/zsh")
    return env


class Tmux:
    def __init__(self, settings: Settings, command: Callable[[], str] | None = None) -> None:
        self.label = f"whaat-{settings.instance}"
        self._command = command or (lambda: settings.terminal_command)
        self.cwd = settings.terminal_cwd or Path.home()
        self.env = session_env()

    @property
    def command(self) -> str:
        """The start command a new session runs, read when it starts, so a changed preference takes effect at once."""
        return self._command()

    def binary(self) -> str:
        found = shutil.which("tmux", path=self.env["PATH"])
        if not found:
            raise TmuxMissingError("tmux is not installed; the terminal needs it (brew install tmux)")
        return found

    def argv(self, *args: str) -> list[str]:
        return [self.binary(), "-L", self.label, *args]

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(self.argv(*args), env=self.env, capture_output=True, text=True, check=False)

    def sessions(self, persona: str | None = None) -> list[Session]:
        listed = self._run(
            "list-sessions",
            "-F",
            "#{session_name}\t#{session_created}\t#{session_attached}\t#{pane_current_path}\t#{@whaat_command}\t#{@whaat_label}\t#{pane_current_command}\t#{session_id}",
        )
        if listed.returncode != 0:
            return []  # no server yet: no sessions
        found = []
        for line in listed.stdout.splitlines():
            name, created, attached, cwd, command, label, program, tmux_id = (line.split("\t") + [""] * 8)[:8]
            match = SESSION_NAME.match(name)
            if not match or (persona and match.group(1) != persona):
                continue
            found.append(
                Session(
                    name,
                    match.group(1),
                    int(match.group(2)),
                    int(created or 0),
                    int(attached or 0),
                    cwd,
                    command,
                    label,
                    program,
                    tmux_id,
                )
            )
        return sorted(found, key=lambda s: (s.persona, s.number))

    def create(
        self,
        persona: str,
        cwd: Path | None = None,
        number: int | None = None,
        command: str | None = None,
        env: dict[str, str] | None = None,
    ) -> Session:
        """A new session in `cwd` (the project), the start command run there, as `cd {cwd} && {command}` would; an
        identity's own agent brings its command and the keys its session gets on top of the server's."""
        number = number or max((s.number for s in self.sessions(persona)), default=0) + 1
        name = f"whaat-{persona}-{number}"
        shell = self.env["SHELL"]
        # the start command runs in the user's login shell, and the shell stays when it exits
        command = command or self.command
        extra = [flag for key, value in (env or {}).items() for flag in ("-e", f"{key}={value}")]
        script = f"{command}; exec {shlex.quote(shell)} -l"
        made = self._run(
            "new-session",
            "-d",
            "-s",
            name,
            "-c",
            str(cwd or self.cwd),
            "-x",
            "160",
            "-y",
            "48",
            *extra,
            "--",
            shell,
            "-lc",
            script,
        )
        if made.returncode != 0:
            raise RuntimeError(f"tmux could not start {name}: {made.stderr.strip()}")
        self._run("set-option", "-t", name, "@whaat_command", command)
        self._run("set-option", "-t", name, "status", "off")
        # Claude Code asks for focus events in tmux; this is whaat's own tmux server, so it is set here
        self._run("set-option", "-g", "focus-events", "on")
        for _ in range(20):
            for session in self.sessions(persona):
                if session.name == name:
                    return session
            time.sleep(0.05)
        raise RuntimeError(f"tmux started {name} but does not list it")

    def rename(self, name: str, label: str) -> Session:
        """Give a session a name of the user's own, kept on the tmux session; an empty one takes it off."""
        if not any(s.name == name for s in self.sessions()):
            raise SessionNotFoundError(name)
        clean = " ".join(label.split())[:MAX_LABEL]
        if clean:
            self._run("set-option", "-t", name, "@whaat_label", clean)
        else:
            self._run("set-option", "-u", "-t", name, "@whaat_label")
        return next(s for s in self.sessions() if s.name == name)

    def kill(self, name: str) -> None:
        if not any(s.name == name for s in self.sessions()):
            raise SessionNotFoundError(name)
        self._run("kill-session", "-t", name)

    def attach_argv(self, name: str) -> list[str]:
        if not any(s.name == name for s in self.sessions()):
            raise SessionNotFoundError(name)
        return self.argv("attach-session", "-t", name)

    def screen(self, name: str, escapes: bool = False, history: int = 0) -> str:
        """The pane's visible screen, plus that many lines of scrollback above it; with escapes, its colours too (a
        dim suggestion is told apart by them)."""
        back = ["-S", f"-{history}"] if history else []
        return self._run("capture-pane", *(["-e"] if escapes else []), "-p", *back, "-t", name).stdout

    def runs_program(self, name: str) -> bool:
        """Whether the session's start command still runs: its shell has a child process. tmux's pane_current_command
        names the shell even then (`shell -lc "cmd; exec shell -l"`, measured 2026-11-05), so it cannot tell."""
        pid = self._run("display-message", "-p", "-t", name, "#{pane_pid}").stdout.strip()
        if not pid.isdigit():
            return False
        return subprocess.run(["pgrep", "-P", pid], capture_output=True, check=False).returncode == 0

    def busy(self, name: str) -> bool:
        """Whether Claude Code works in the session; only the visible screen counts, scrollback keeps old frames."""
        return bool(BUSY.search(self.screen(name)))

    def asking(self, name: str) -> bool:
        return waits_for_answer(self.screen(name))

    def state(self, name: str) -> tuple[bool, bool, bool]:
        """(busy, asking, done) from one look at the visible screen."""
        screen = self.screen(name)
        return bool(BUSY.search(screen)), waits_for_answer(screen), says_done(screen)

    def type_into(self, name: str, text: str) -> None:
        """Type text into the claude prompt and submit it, or raise TypingError without submitting anything. A dim
        suggestion in the prompt is replaced by typing; real unsent text stops it."""
        before, dim = prompt_line(self.screen(name, escapes=True))
        if before is None:
            raise TypingError("no claude prompt found in the session")
        if before and not dim:
            raise TypingError(f"the session prompt holds unsent text ({before[:60]!r}); send or clear it first")
        self._run("send-keys", "-t", name, "-l", text)
        time.sleep(READBACK_SECONDS)
        now, dim = prompt_line(self.screen(name, escapes=True))
        if not same_text(now, text) or dim:
            self._run("send-keys", "-t", name, "C-u")
            raise TypingError(f"the prompt read back {now!r}, not the text; cleared it, nothing sent")
        self._run("send-keys", "-t", name, "Enter")


def prompt_line(screen: str) -> tuple[str | None, bool]:
    """(text, dim) of the claude prompt line: the text after the prompt mark, and whether it is only the dim suggestion
    Claude Code shows in an empty prompt. A long prompt wraps: its next lines run to a blank line or the box border."""
    raw = screen.splitlines()
    at = [i for i, line in enumerate(raw) if PROMPT_MARK in line]
    if not at:
        return None, False
    rest = []
    for line in raw[at[-1] + 1 :]:
        plain = SGR.sub("", line).replace("\xa0", " ").strip()
        if not plain or plain[0] in "─╰╭│":
            break
        rest.append(line)
    after = " ".join([raw[at[-1]].split(PROMPT_MARK, 1)[1], *rest])
    text = SGR.sub("", after).replace("\xa0", " ").strip()
    undimmed = SGR.sub("", DIM.sub("", after)).replace("\xa0", " ").strip()
    return text, bool(text) and not undimmed


def same_text(shown: str | None, typed: str) -> bool:
    """Whether the prompt shows the typed text; wrapping may add or drop spaces at the line breaks."""
    return shown is not None and re.sub(r"\s+", "", shown) == re.sub(r"\s+", "", typed)
