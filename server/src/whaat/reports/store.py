import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from whaat.config import Settings

PRIVATE_REPORT_DIRS = ("session-reports", "journal", "memory-curation")
PRIVATE_ROOT_PREFIX = "private-"
REPORT_SUFFIXES = (".md", ".json")
COMPANION_NAMES = (".meta.json", ".notes.json")


def is_report_file(path: Path) -> bool:
    return path.suffix in REPORT_SUFFIXES and not path.name.endswith(COMPANION_NAMES) and not path.name.startswith(".")


@dataclass(frozen=True)
class Root:
    key: str
    path: Path
    report_dirs: tuple[str, ...]
    identity: str | None = None

    @property
    def private(self) -> bool:
        return self.identity is not None


def roots_from(settings: Settings, identities: dict[str, Path] | None = None) -> list[Root]:
    shared = [
        Root(key, path.resolve(), settings.shared_report_dirs[key])
        for key, path in settings.shared_roots.items()
        if key in settings.shared_report_dirs
    ]
    private = [
        Root(f"{PRIVATE_ROOT_PREFIX}{identity}", path.resolve(), PRIVATE_REPORT_DIRS, identity)
        for identity, path in (settings.identities if identities is None else identities).items()
    ]
    return shared + private


@dataclass(frozen=True)
class ReportFile:
    root: Root
    path: Path

    @property
    def rel_path(self) -> str:
        return self.path.relative_to(self.root.path).as_posix()

    @property
    def id(self) -> str:
        return f"{self.root.key}:{self.rel_path}"

    def companion(self, suffix: str) -> Path:
        return self.path.with_suffix(suffix)


KEY_LENGTH = 16


def report_key(report_id: str) -> str:
    return hashlib.sha256(report_id.encode("utf-8")).hexdigest()[:KEY_LENGTH]


class ReportStore(Protocol):
    def list_files(self) -> list[ReportFile]: ...

    def find(self, report_id: str) -> ReportFile | None: ...


class FileReportStore:
    def __init__(self, roots: list[Root]) -> None:
        self._roots = {root.key: root for root in roots}

    def list_files(self) -> list[ReportFile]:
        return sorted(self._walk(), key=lambda report: report.id)

    def find(self, report_id: str) -> ReportFile | None:
        root_key, _, rel_path = report_id.partition(":")
        root = self._roots.get(root_key)
        if root is None or not rel_path:
            return None
        path = (root.path / rel_path).resolve()
        if not path.is_relative_to(root.path) or not is_report_file(path) or not path.is_file():
            return None
        report = ReportFile(root, path)
        return report if report.rel_path.split("/", 1)[0] in root.report_dirs else None

    def _walk(self) -> Iterator[ReportFile]:
        for root in self._roots.values():
            for dir_name in root.report_dirs:
                for path in (root.path / dir_name).rglob("*"):
                    if is_report_file(path) and path.is_file():
                        yield ReportFile(root, path)
