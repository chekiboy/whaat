"""Opening a whaat session in a terminal app of the machine: the
app gets a new window that attaches to the same tmux session, so the session is the one the browser shows, only seen
from elsewhere. macOS only for now; the first time, macOS asks the user to let whaat control the app."""

import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Literal

App = Literal["terminal-app", "iterm2"]
APP_PATHS: dict[App, tuple[Path, ...]] = {
    "terminal-app": (Path("/System/Applications/Utilities/Terminal.app"), Path("/Applications/Utilities/Terminal.app")),
    "iterm2": (Path("/Applications/iTerm.app"), Path.home() / "Applications" / "iTerm.app"),
}
Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class NativeOpenError(RuntimeError):
    pass


def installed() -> list[App]:
    return [app for app, paths in APP_PATHS.items() if any(p.is_dir() for p in paths)]


def _applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def script_for(app: App, command: str) -> str:
    quoted = _applescript_string(command)
    if app == "terminal-app":
        return f'tell application "Terminal"\n  activate\n  do script {quoted}\nend tell'
    return f'tell application "iTerm"\n  activate\n  create window with default profile command {quoted}\nend tell'


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False, timeout=20)


def open_in(app: App, attach: list[str], run: Runner = _run) -> None:
    """Open the app with a window running the tmux attach command."""
    if app not in installed():
        raise NativeOpenError(f"{app} is not installed")
    done = run(["osascript", "-e", script_for(app, shlex.join(attach))])
    if done.returncode != 0:
        raise NativeOpenError(done.stderr.strip() or f"osascript failed for {app}")
