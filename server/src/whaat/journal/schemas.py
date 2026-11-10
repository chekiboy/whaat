from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from whaat.reports.schemas import Envelope
from whaat.reports.types.base import Strict
from whaat.reports.types.journal import JournalBlockIn, JournalBody
from whaat.reports.types.memory_curation import CurationReportBody, CurationReportBodyIn, RowDecision
from whaat.reports.types.session_report import SessionReportBody, SessionReportBodyIn

SESSION_PATTERN = r"^[0-9a-f]{8}$"
TAG_PATTERN = r"^[a-z][a-z0-9-]{0,31}$"
SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"

Session = Annotated[str, StringConstraints(pattern=SESSION_PATTERN)]
Tag = Annotated[str, StringConstraints(pattern=TAG_PATTERN)]


class JournalDocument(BaseModel):
    envelope: Envelope
    body: JournalBody


class SessionReportDocument(BaseModel):
    envelope: Envelope
    body: SessionReportBody


class CurationReportDocument(BaseModel):
    envelope: Envelope
    body: CurationReportBody


class JournalEntry(Strict):
    session: Session
    entry_date: date | None = None
    tags: list[Tag] = Field(default_factory=list)
    block: JournalBlockIn


class SessionReport(Strict):
    session: Session
    slug: Annotated[str, StringConstraints(pattern=SLUG_PATTERN)] = Field(
        description="A few words of the topic; used only when the session has no report yet."
    )
    entry_date: date | None = None
    tags: list[Tag] = Field(default_factory=list)
    report: SessionReportBodyIn


class CurationReport(Strict):
    entry_date: date | None = Field(default=None, description="The run's day; today when left out.")
    report: CurationReportBodyIn


class SavedJournalEntry(BaseModel):
    report_id: str
    appended: bool
    commit: str | None
    envelope: Envelope
    warnings: list[str]


class CurationDecision(Strict):
    n: int = Field(ge=1, description="The row's number.")
    decision: RowDecision | None = Field(description="apply, reject, or null to take a word back.")
    note: str | None = None


class CurationApplied(Strict):
    n: int = Field(ge=1, description="The row's number.")
    applied: str | None = Field(description="The row's commits (`store <sha> <sha>`); null empties the cell.")


class CurationAppliedCall(Strict):
    report_id: str
    rows: list[CurationApplied]


class CurationRowsSaved(BaseModel):
    commit: str | None
    warnings: list[str]


class SavedCurationReport(BaseModel):
    report_id: str
    replaced: bool
    commit: str | None
    envelope: Envelope
    warnings: list[str]


class SavedSessionReport(BaseModel):
    report_id: str
    replaced: bool
    commit: str | None
    envelope: Envelope
    warnings: list[str]
