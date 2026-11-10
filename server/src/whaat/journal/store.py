import os
from datetime import date
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel

JOURNAL_DIR = "journal"
SESSION_REPORTS_DIR = "session-reports"
CURATION_DIR = "memory-curation"
DIR_MODE = 0o700
FILE_MODE = 0o600

Document = TypeVar("Document", bound=BaseModel)


def month_dir(base: Path, day: date) -> Path:
    return base / f"{day.year:04d}" / f"{day.month:02d}"


class JournalStore(Protocol):
    def entry_path(self, folder: Path, entry_date: date, session: str) -> Path: ...

    def session_reports(self, folder: Path, session: str) -> list[Path]: ...

    def session_report_path(self, folder: Path, report_date: date, session: str, slug: str) -> Path: ...

    def curation_report_path(self, folder: Path, report_date: date) -> Path: ...

    def read(self, path: Path, model: type[Document]) -> Document | None: ...

    def write(self, folder: Path, path: Path, document: BaseModel) -> bool: ...


class FileJournalStore:
    def entry_path(self, folder: Path, entry_date: date, session: str) -> Path:
        return month_dir(folder / JOURNAL_DIR, entry_date) / f"{entry_date.isoformat()}_{session}.json"

    def session_reports(self, folder: Path, session: str) -> list[Path]:
        return sorted((folder / SESSION_REPORTS_DIR).rglob(f"*_session-report_{session}_*.json"))

    def session_report_path(self, folder: Path, report_date: date, session: str, slug: str) -> Path:
        name = f"{report_date.isoformat()}_session-report_{session}_{slug}.json"
        return month_dir(folder / SESSION_REPORTS_DIR, report_date) / name

    def curation_report_path(self, folder: Path, report_date: date) -> Path:
        return month_dir(folder / CURATION_DIR, report_date) / f"{report_date.isoformat()}_memory-curation.json"

    def read(self, path: Path, model: type[Document]) -> Document | None:
        """None when the file does not exist; a pydantic ValidationError when it is not a valid document."""
        if not path.exists():
            return None
        return model.model_validate_json(path.read_text(encoding="utf-8"))

    def write(self, folder: Path, path: Path, document: BaseModel) -> bool:
        """Replace the whole document atomically; the directories below the private folder are created private."""
        existed = path.exists()
        _make_private_dirs(folder, path.parent)
        partial = path.with_name(f".{path.name}.partial")
        descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(document.model_dump_json(indent=2) + "\n")
        partial.replace(path)
        return existed


def _make_private_dirs(folder: Path, directory: Path) -> None:
    for part in reversed([directory, *directory.parents]):
        if part.is_relative_to(folder) and part != folder and not part.exists():
            part.mkdir(mode=DIR_MODE)
