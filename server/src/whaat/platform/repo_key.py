import subprocess
from pathlib import Path

MAX_LOCAL_HOPS = 3


def _git(folder: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def remote_path(url: str | None, base: Path, depth: int = 0) -> str | None:
    """The origin's path; a local-path origin is followed to its own origin, so a clone resolves like its source."""
    if not url or depth > MAX_LOCAL_HOPS:
        return None
    url = url.removeprefix("file://")
    if url.startswith(("/", "~", ".")):
        local = (base / Path(url).expanduser()).resolve()
        return remote_path(_git(local, "remote", "get-url", "origin"), local, depth + 1) if local.is_dir() else None
    if "://" in url:
        rest = url.split("://", 1)[1]
        path = rest.split("/", 1)[1] if "/" in rest else ""
    elif ":" in url:
        path = url.split(":", 1)[1]
    else:
        return None
    return path.strip("/").removesuffix(".git")


def repo_key(start: Path) -> tuple[str, str] | None:
    """(project, repo) of the repo holding start, from its origin remote; None outside git."""
    top = _git(start, "rev-parse", "--show-toplevel")
    if not top:
        return None
    segments = [
        s for s in (remote_path(_git(Path(top), "remote", "get-url", "origin"), Path(top)) or "").split("/") if s
    ]
    return (segments[0], segments[-1]) if len(segments) >= 2 else ("local", Path(top).name)
