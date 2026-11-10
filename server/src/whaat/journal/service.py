import threading
from collections.abc import Callable, Mapping
from datetime import date, datetime
from pathlib import Path

from pydantic import ValidationError

from whaat.git import GitCommitError, GitCommitter
from whaat.identities.registry import ADMIN, Principal
from whaat.journal.exceptions import (
    CurationReportNotFoundError,
    InvalidStoredDocumentError,
    UnknownIdentityError,
    UnknownRowsError,
)
from whaat.journal.schemas import (
    CurationApplied,
    CurationDecision,
    CurationReport,
    CurationReportDocument,
    JournalDocument,
    JournalEntry,
    SavedCurationReport,
    SavedJournalEntry,
    SavedSessionReport,
    SessionReport,
    SessionReportDocument,
)
from whaat.journal.store import CURATION_DIR, Document, JournalStore
from whaat.reports.schemas import Envelope
from whaat.reports.store import ReportFile, Root
from whaat.reports.types.journal import JournalBlock, JournalBody
from whaat.reports.types.memory_curation import CurationReportBody
from whaat.reports.types.session_report import SessionReportBody

ENTRY_COMMIT_MESSAGE = "journal: session {session} entry"
REPORT_COMMIT_MESSAGE = "journal: session {session} report"
CURATION_COMMIT_MESSAGE = "memory-curation: report {day}"
CURATION_WRITER = "whaat:memory-curation"
DECISIONS_COMMIT_MESSAGE = "memory-curation: decisions on {name}"
APPLIED_COMMIT_MESSAGE = "memory-curation: applied rows of {name}"
SENT_COMMIT_MESSAGE = "memory-curation: rows sent to the session, {name}"
WRITER = "whaat:journal"
NOT_A_REPOSITORY_WARNING = "the private folder of {identity} is not a git repository; it is not committed"
SEVERAL_REPORTS_WARNING = "session {session} has several reports; {name} was overwritten"


class JournalService:
    def __init__(
        self,
        store: JournalStore,
        roots_for: Callable[[Principal], list[Root]],
        committer: GitCommitter,
        now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    ) -> None:
        self._store = store
        self._roots_for = roots_for
        self._committer = committer
        self._now = now
        self._lock = threading.Lock()

    def save_entry(self, entry: JournalEntry, identity: str) -> SavedJournalEntry:
        root = self._root_for(identity)
        warnings: list[str] = []
        now = self._now().replace(microsecond=0)
        entry_date = entry.entry_date or now.date()
        with self._lock:
            report = ReportFile(root, self._store.entry_path(root.path, entry_date, entry.session))
            previous = self._read(report, JournalDocument)
            block = JournalBlock(**entry.block.model_dump(), at=now)
            envelope = self._envelope(
                previous.envelope if previous else None,
                kind="journal",
                title=f"{entry_date.isoformat()} · session {entry.session}",
                created_date=entry_date,
                session=entry.session,
                repo=None,
                identity=identity,
                tags=entry.tags,
                now=now,
            )
            blocks = [*(previous.body.blocks if previous else []), block]
            self._store.write(
                root.path, report.path, JournalDocument(envelope=envelope, body=JournalBody(blocks=blocks))
            )
            commit = self._commit(root, report.path, ENTRY_COMMIT_MESSAGE.format(session=entry.session), warnings)
        return SavedJournalEntry(
            report_id=report.id, appended=previous is not None, commit=commit, envelope=envelope, warnings=warnings
        )

    def save_session_report(self, report_in: SessionReport, identity: str) -> SavedSessionReport:
        """One report per session: a later save replaces the file the first one named, whatever its date or slug."""
        root = self._root_for(identity)
        warnings: list[str] = []
        now = self._now().replace(microsecond=0)
        with self._lock:
            existing = self._store.session_reports(root.path, report_in.session)
            if len(existing) > 1:
                warnings.append(SEVERAL_REPORTS_WARNING.format(session=report_in.session, name=existing[0].name))
            path = (
                existing[0]
                if existing
                else self._store.session_report_path(
                    root.path, report_in.entry_date or now.date(), report_in.session, report_in.slug
                )
            )
            report = ReportFile(root, path)
            previous = self._read(report, SessionReportDocument)
            body = SessionReportBody(**report_in.report.model_dump())
            envelope = self._envelope(
                previous.envelope if previous else None,
                kind="session-report",
                title=body.topic,
                created_date=report_in.entry_date or now.date(),
                session=report_in.session,
                repo=body.repo,
                identity=identity,
                tags=report_in.tags,
                now=now,
            )
            self._store.write(root.path, report.path, SessionReportDocument(envelope=envelope, body=body))
            commit = self._commit(root, report.path, REPORT_COMMIT_MESSAGE.format(session=report_in.session), warnings)
        return SavedSessionReport(
            report_id=report.id, replaced=previous is not None, commit=commit, envelope=envelope, warnings=warnings
        )

    def save_curation_report(self, report_in: CurationReport, identity: str) -> SavedCurationReport:
        """One report per day: a later save that day replaces it, so apply-rows can write its Applied cells back."""
        root = self._root_for(identity)
        warnings: list[str] = []
        now = self._now().replace(microsecond=0)
        day = report_in.entry_date or now.date()
        with self._lock:
            report = ReportFile(root, self._store.curation_report_path(root.path, day))
            previous = self._read(report, CurationReportDocument)
            body = CurationReportBody(**report_in.report.model_dump())
            envelope = Envelope(
                kind="memory-curation",
                title=f"Memory curation — {day.isoformat()}",
                created_date=day,
                created_at=previous.envelope.created_at if previous and previous.envelope.created_at else now,
                writer=CURATION_WRITER,
                identity=identity,
            )
            self._store.write(root.path, report.path, CurationReportDocument(envelope=envelope, body=body))
            commit = self._commit(root, report.path, CURATION_COMMIT_MESSAGE.format(day=day.isoformat()), warnings)
        return SavedCurationReport(
            report_id=report.id, replaced=previous is not None, commit=commit, envelope=envelope, warnings=warnings
        )

    def save_curation_decisions(
        self, report_id: str, decisions: list[CurationDecision]
    ) -> tuple[str, str | None, list[str]]:
        """The user's word per row, written into the report itself; rows not named stay as they are.
        Returns the report's identity, the commit and any warnings."""
        updates = {d.n: {"decision": d.decision, "note": d.note} for d in decisions}
        return self._update_curation_rows(report_id, None, updates, DECISIONS_COMMIT_MESSAGE)

    def save_curation_applied(
        self, report_id: str, identity: str, applied: list[CurationApplied]
    ) -> tuple[str, str | None, list[str]]:
        """apply-rows' Applied cells (the row's commits; null empties it after a revert), on the identity's own report
        only; the decisions and everything else in the report stay as they are."""
        updates = {a.n: {"applied": a.applied} for a in applied}
        return self._update_curation_rows(report_id, identity, updates, APPLIED_COMMIT_MESSAGE)

    def curation_document(self, report_id: str) -> tuple[str, CurationReportDocument]:
        """The identity and the document of a curation report, for the page; CurationReportNotFoundError if none."""
        root, report = self._curation_report(report_id, None)
        document = self._read(report, CurationReportDocument)
        if document is None:
            raise CurationReportNotFoundError(report_id)
        return root.identity or "", document

    def mark_curation_sent(self, report_id: str, rows: list[int], at: str | None) -> None:
        """Stamp rows as sent to the session at `at`, or empty the stamp (a revert was sent)."""
        self._update_curation_rows(report_id, None, {n: {"sent_at": at} for n in rows}, SENT_COMMIT_MESSAGE)

    def _curation_report(self, report_id: str, identity: str | None) -> tuple[Root, ReportFile]:
        root_key, _, rel = report_id.partition(":")
        principal = ADMIN if identity is None else Principal(identity)
        root = next((r for r in self._roots_for(principal) if r.key == root_key and r.identity), None)
        if root is None or not rel.startswith(CURATION_DIR + "/") or ".." in Path(rel).parts:
            raise CurationReportNotFoundError(report_id)
        return root, ReportFile(root, root.path / rel)

    def _update_curation_rows(
        self, report_id: str, identity: str | None, updates: Mapping[int, Mapping[str, object]], message: str
    ) -> tuple[str, str | None, list[str]]:
        root, report = self._curation_report(report_id, identity)
        warnings: list[str] = []
        with self._lock:
            document = self._read(report, CurationReportDocument)
            if document is None:
                raise CurationReportNotFoundError(report_id)
            unknown = sorted(set(updates) - {row.n for row in document.body.rows})
            if unknown:
                raise UnknownRowsError(unknown)
            rows = [
                row.model_copy(update=dict(updates[row.n])) if row.n in updates else row for row in document.body.rows
            ]
            body = document.body.model_copy(update={"rows": rows})
            self._store.write(root.path, report.path, CurationReportDocument(envelope=document.envelope, body=body))
            commit = self._commit(root, report.path, message.format(name=report.path.name), warnings)
        return root.identity or "", commit, warnings

    def _root_for(self, identity: str) -> Root:
        root = next((root for root in self._roots_for(Principal(identity)) if root.identity == identity), None)
        if root is None:
            raise UnknownIdentityError(identity)
        return root

    def _read(self, report: ReportFile, model: type[Document]) -> Document | None:
        try:
            return self._store.read(report.path, model)
        except ValidationError as err:
            raise InvalidStoredDocumentError(report.id, f"{err.error_count()} errors") from err

    @staticmethod
    def _envelope(
        previous: Envelope | None,
        *,
        kind: str,
        title: str,
        created_date: date,
        session: str,
        repo: str | None,
        identity: str,
        tags: list[str],
        now: datetime,
    ) -> Envelope:
        """The first save fixes the date and the creation time; tags only ever grow."""
        return Envelope(
            kind=kind,
            title=title,
            created_date=previous.created_date if previous and previous.created_date else created_date,
            created_at=previous.created_at if previous and previous.created_at else now,
            session=session,
            repo=repo,
            writer=WRITER,
            identity=identity,
            tags=list(dict.fromkeys([*(previous.tags if previous else []), *tags])),
        )

    def _commit(self, root: Root, path: Path, message: str, warnings: list[str]) -> str | None:
        if not self._committer.is_repository(root.path):
            warnings.append(NOT_A_REPOSITORY_WARNING.format(identity=root.identity))
            return None
        try:
            return self._committer.commit(root.path, [path], message)
        except GitCommitError as err:
            warnings.append(f"saved but not committed: {err}")
            return None
