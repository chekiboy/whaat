"""Browsing the server's folders for the project a terminal session starts in; the folders used are saved in the
preferences (whaat.preferences)."""

from pathlib import Path

MAX_FOLDERS = 500


class FolderError(ValueError):
    pass


def folder(path: str) -> Path:
    """An existing folder, given as an absolute path (or one under ~)."""
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise FolderError(f"{path!r} is not an absolute path")
    resolved = candidate.resolve()
    if not resolved.is_dir():
        raise FolderError(f"{path!r} is not a folder")
    return resolved


def subfolders(parent: Path, hidden: bool = False) -> list[tuple[str, bool]]:
    """The folders right under `parent`, by name, each with whether it is a git repo."""
    found = []
    try:
        entries = sorted(parent.iterdir(), key=lambda p: p.name.lower())
    except PermissionError as err:
        raise FolderError(f"{parent} cannot be read") from err
    for entry in entries:
        if not hidden and entry.name.startswith("."):
            continue
        try:
            if entry.is_dir():
                found.append((entry.name, (entry / ".git").exists()))
        except OSError:
            continue
        if len(found) >= MAX_FOLDERS:
            break
    return found
