import json
import re
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from whaat.reports.exceptions import ReportNotFoundError
from whaat.reports.schemas import (
    Envelope,
    EnvelopeSource,
    ReportBody,
    ReportContent,
    ReportDetail,
    ReportSection,
    ReportState,
    ReportSummary,
)
from whaat.reports.store import ReportFile, ReportStore, report_key
from whaat.reports.types.journal import JournalBody, JournalContent
from whaat.reports.types.markdown import parse_markdown
from whaat.reports.types.memory_curation import CurationReportBody, CurationReportContent
from whaat.reports.types.session_report import SessionReportBody, SessionReportContent

PRIVATE_MARKER = ".private"
META_SUFFIX = ".meta.json"
SENT_SUFFIX = ".sent.jsonl"
MISSING_MARKER_WARNING = f"private by location: no {PRIVATE_MARKER} marker above this report"
MISMATCHED_IDENTITY_WARNING = "its envelope names {named}, but it lies in the private folder of {owner}"

WRITERS = {
    "review": "review-code",
    "development": "start-ticket-pure",
    "investigation": "investigate-pure",
    "memory-curation": "memory-curation",
    "session-report": "self-model-journal",
    "journal": "self-model-journal",
}
DATE_IN_NAME = re.compile(r"(\d{4})-?(\d{2})-?(\d{2})")
TICKET = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2,10}-\d+)(?![A-Za-z0-9])")
SESSION_IN_NAME = re.compile(r"(?:_session-report_([0-9a-f]{8})_|^\d{4}-\d{2}-\d{2}_([0-9a-f]{8})\.(?:md|json)$)")
INVALID_DOCUMENT_WARNING = "{name} is not a valid document ({reason}); its envelope is derived from its path"


def kind_of(report: ReportFile) -> str:
    top_dir = report.rel_path.split("/", 1)[0]
    if top_dir == "reviews":
        return "development" if report.path.name.endswith("-development.md") else "review"
    if top_dir == "investigations":
        return "investigation"
    if top_dir == "memory-curation":
        return "memory-curation"
    if top_dir == "session-reports":
        return "session-report"
    if top_dir == "journal":
        return "journal"
    return "markdown"


def created_date_of(report: ReportFile) -> date:
    match = DATE_IN_NAME.search(report.path.name)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    return date.fromtimestamp(report.path.stat().st_mtime)


def repo_of(report: ReportFile, kind: str, pins: list[str]) -> str | None:
    parts = report.rel_path.split("/")
    if kind in {"review", "development", "investigation"} and len(parts) >= 4:
        return f"{parts[1]}/{parts[2]}"
    for pin in pins:
        if pin.startswith("Repo:"):
            value = pin.removeprefix("Repo:").split()
            return value[0] if value else None
    return None


def derive_envelope(report: ReportFile, text: str) -> Envelope:
    body = parse_markdown(text)
    kind = kind_of(report)
    session = SESSION_IN_NAME.search(report.path.name)
    ticket = TICKET.search(report.rel_path)
    return Envelope(
        kind=kind,
        title=body.title or report.path.stem,
        created_date=created_date_of(report),
        session=next(filter(None, session.groups()), None) if session else None,
        repo=repo_of(report, kind, body.pins),
        ticket=ticket.group(1).upper() if ticket else None,
        writer=WRITERS.get(kind),
    )


def privacy_of(report: ReportFile) -> tuple[bool, list[str]]:
    directory: Path = report.path.parent
    while directory.is_relative_to(report.root.path):
        if (directory / PRIVATE_MARKER).exists():
            return True, []
        if directory == report.root.path:
            break
        directory = directory.parent
    if report.root.private:
        return True, [MISSING_MARKER_WARNING]
    return False, []


def state_of(report: ReportFile) -> ReportState:
    return "applied" if report.companion(SENT_SUFFIX).exists() else "done"


def _newest_first(summary: ReportSummary) -> tuple[date, str]:
    return summary.envelope.created_date or date.min, summary.id


class ReportService:
    def __init__(self, store: ReportStore) -> None:
        self._store = store

    def list_reports(
        self, kind: str | None = None, identity: str | None = None, tag: str | None = None, session: str | None = None
    ) -> list[ReportSummary]:
        summaries = [
            self._summary(report, report.path.read_text(encoding="utf-8")) for report in self._store.list_files()
        ]
        if kind is not None:
            summaries = [summary for summary in summaries if summary.envelope.kind == kind]
        if identity is not None:
            summaries = [summary for summary in summaries if summary.envelope.identity == identity]
        if tag is not None:
            summaries = [summary for summary in summaries if tag in summary.envelope.tags]
        if session is not None:
            summaries = [summary for summary in summaries if summary.envelope.session == session]
        return sorted(summaries, key=_newest_first, reverse=True)

    def get_report_by_key(self, key: str) -> ReportDetail:
        match = next((report for report in self._store.list_files() if report_key(report.id) == key), None)
        if match is None:
            raise ReportNotFoundError(key)
        return self.get_report(match.id)

    def get_report(self, report_id: str) -> ReportDetail:
        report = self._store.find(report_id)
        if report is None:
            raise ReportNotFoundError(report_id)
        text = report.path.read_text(encoding="utf-8")
        summary = self._summary(report, text)
        return ReportDetail(**summary.model_dump(), body=content_of(report, summary.envelope.kind, text))

    def _summary(self, report: ReportFile, text: str) -> ReportSummary:
        warnings: list[str] = []
        envelope, source = self._envelope(report, text, warnings)
        owner = report.root.identity
        if envelope.identity is None:
            envelope = envelope.model_copy(update={"identity": owner})
        elif owner is not None and envelope.identity != owner:
            warnings.append(MISMATCHED_IDENTITY_WARNING.format(named=envelope.identity, owner=owner))
            envelope = envelope.model_copy(update={"identity": owner})
        private, privacy_warnings = privacy_of(report)
        return ReportSummary(
            id=report.id,
            key=report_key(report.id),
            root=report.root.key,
            path=report.rel_path,
            envelope=envelope,
            envelope_source=source,
            private=private,
            state=state_of(report),
            warnings=warnings + privacy_warnings,
        )

    @staticmethod
    def _envelope(report: ReportFile, text: str, warnings: list[str]) -> tuple[Envelope, EnvelopeSource]:
        if report.path.suffix == ".json":
            try:
                return Envelope.model_validate(json.loads(text)["envelope"]), "embedded"
            except (ValueError, KeyError, TypeError, ValidationError) as err:
                warnings.append(INVALID_DOCUMENT_WARNING.format(name=report.path.name, reason=type(err).__name__))
                return derive_envelope(report, ""), "derived"
        meta = report.companion(META_SUFFIX)
        if meta.exists():
            try:
                return Envelope.model_validate_json(meta.read_text(encoding="utf-8")), "meta"
            except ValidationError as err:
                warnings.append(f"{meta.name} is invalid ({err.error_count()} errors); envelope derived instead")
        return derive_envelope(report, text), "derived"


def content_of(report: ReportFile, kind: str, text: str) -> ReportContent:
    """A JSON document gives its typed body; markdown, or a body that does not validate, is shown as sections."""
    if report.path.suffix != ".json":
        return parse_markdown(text)
    try:
        body = json.loads(text)["body"]
        if kind == "journal":
            return JournalContent(blocks=JournalBody.model_validate(body).blocks)
        if kind == "session-report":
            return SessionReportContent(report=SessionReportBody.model_validate(body))
        if kind == "memory-curation":
            return CurationReportContent(report=CurationReportBody.model_validate(body))
    except (ValueError, KeyError, TypeError, ValidationError):
        pass
    return ReportBody(title=report.path.stem, pins=[], sections=[ReportSection(heading="JSON", level=2, markdown=text)])
