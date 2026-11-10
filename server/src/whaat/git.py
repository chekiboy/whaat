import subprocess
import threading
from pathlib import Path

_folder_locks: dict[Path, threading.Lock] = {}
_folder_locks_guard = threading.Lock()


def folder_lock(folder: Path) -> threading.Lock:
    """One lock per repository folder, shared by every committer in the process: the memory and the journal commit into
    the same identity folder, and two git commands at once there fail on its index.lock."""
    key = folder.resolve()
    with _folder_locks_guard:
        return _folder_locks.setdefault(key, threading.Lock())


class GitCommitError(RuntimeError):
    pass


class GitCommitter:
    def is_repository(self, folder: Path) -> bool:
        return (folder / ".git").exists()

    def init(self, folder: Path) -> None:
        with folder_lock(folder):
            self._git(folder, "init", "--quiet")

    def commit(self, folder: Path, paths: list[Path], message: str) -> str:
        """Commit only these paths, so whatever else is staged or changed in the folder stays as it is."""
        relative = [path.relative_to(folder).as_posix() for path in paths]
        with folder_lock(folder):
            self._git(folder, "add", "--", *relative)
            self._git(folder, "commit", "--quiet", "-m", message, "--", *relative)
            return self._git(folder, "rev-parse", "HEAD").strip()

    def move(self, folder: Path, moves: list[tuple[Path, Path]], message: str) -> str:
        """Move files in one commit: a tracked file with `git mv`, so its history follows it; an untracked one is
        renamed and added. Nothing else in the folder is staged."""
        with folder_lock(folder):
            sources = [src.relative_to(folder).as_posix() for src, _ in moves]
            tracked = set(self._git(folder, "ls-files", "-z", "--", *sources).split("\0")) - {""}
            paths: list[str] = []
            for (src, dst), rel in zip(moves, sources, strict=True):
                target = dst.relative_to(folder).as_posix()
                if rel in tracked:
                    self._git(folder, "mv", "--", rel, target)
                    paths += [rel, target]
                else:
                    src.rename(dst)
                    paths.append(target)
            self._git(folder, "add", "--", *[dst.relative_to(folder).as_posix() for _, dst in moves])
            self._git(folder, "commit", "--quiet", "-m", message, "--", *paths)
            return self._git(folder, "rev-parse", "HEAD").strip()

    def revert(self, folder: Path, shas: list[str], inside: str) -> list[str]:
        """Revert these commits newest first, one revert commit each, in a single run: a conflict aborts the whole run
        and leaves the folder as it was. Refuses a commit HEAD does not contain, or one that touched a path outside
        `inside`. Returns the new commits, oldest first."""
        with folder_lock(folder):
            resolved = []
            for sha in shas:
                full = self._git(folder, "rev-parse", "--verify", f"{sha}^{{commit}}").strip()
                if subprocess.run(
                    ["git", "-C", str(folder), "merge-base", "--is-ancestor", full, "HEAD"], capture_output=True
                ).returncode:
                    raise GitCommitError(f"{sha} is not in this folder's history")
                touched = self._git(folder, "show", "--name-only", "--format=", full).split()
                outside = [path for path in touched if not path.startswith(inside + "/")]
                if outside:
                    raise GitCommitError(f"{sha} touched {', '.join(outside)}, outside {inside}/; not reverted")
                resolved.append(full)
            newest_first = self._git(folder, "rev-list", "--no-walk=sorted", *resolved).split()
            before = self._git(folder, "rev-parse", "HEAD").strip()
            run = subprocess.run(
                ["git", "-C", str(folder), "revert", "--no-edit", *newest_first], capture_output=True, text=True
            )
            if run.returncode:
                subprocess.run(["git", "-C", str(folder), "revert", "--abort"], capture_output=True, check=False)
                reason = (run.stderr or run.stdout).strip().splitlines()
                raise GitCommitError(f"git revert failed and was aborted, nothing changed: {' '.join(reason[-2:])}")
            return self._git(folder, "rev-list", "--reverse", f"{before}..HEAD").split()

    @staticmethod
    def _git(folder: Path, *args: str) -> str:
        result = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise GitCommitError(f"git {args[0]} failed: {(result.stderr or result.stdout).strip()}")
        return result.stdout
