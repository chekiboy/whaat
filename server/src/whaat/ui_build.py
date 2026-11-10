"""Building the checkout's UI before a restart, so the new process does not serve an old `ui/dist` beside new endpoints.
A UI from `WHAAT_UI_DIR` is someone else's build and is served as it is."""

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from whaat.config import REPO_UI_DIR

BUILD_TIMEOUT_SECONDS = 300
# where pnpm usually is when the server's PATH lacks it: an app started from the Finder gets only
# /usr/bin:/bin:/usr/sbin:/sbin (Whaat (dev).app's ↻ answered 409 four times on 2026-11-09)
PNPM_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin", "~/Library/pnpm")
OUTPUT_TAIL_LINES = 20


@dataclass(frozen=True)
class UiBuild:
    built: bool
    error: str | None = None


Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """pnpm's own folder goes first on the PATH, so the `node` it starts with is found beside it."""
    path = os.pathsep.join([str(Path(command[0]).parent), os.environ.get("PATH", "")])
    return subprocess.run(
        command,
        cwd=cwd,
        env={**os.environ, "PATH": path},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=BUILD_TIMEOUT_SECONDS,
    )


def _tail(text: str) -> str:
    return "\n".join(text.strip().splitlines()[-OUTPUT_TAIL_LINES:])


def find_pnpm() -> str | None:
    """pnpm on the server's PATH, else in the folders it is usually installed in."""
    found = shutil.which("pnpm")
    if found:
        return found
    for folder in PNPM_DIRS:
        candidate = Path(folder).expanduser() / "pnpm"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def build_ui(ui_dir: Path | None, run: Runner = _run, pnpm: str | None = None) -> UiBuild:
    sources = REPO_UI_DIR.parent
    if ui_dir is None or ui_dir.resolve() != REPO_UI_DIR.resolve() or not (sources / "package.json").is_file():
        return UiBuild(built=False)
    pnpm = pnpm or find_pnpm()
    if pnpm is None:
        return UiBuild(built=False, error="pnpm is not on the server's PATH, so the UI could not be built")
    try:
        result = run([pnpm, "build"], sources)
    except subprocess.TimeoutExpired:
        return UiBuild(built=False, error=f"pnpm build ran longer than {BUILD_TIMEOUT_SECONDS} s")
    if result.returncode != 0:
        return UiBuild(built=False, error=_tail(result.stdout or ""))
    return UiBuild(built=True)
