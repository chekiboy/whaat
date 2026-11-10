from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from whaat.reports.types.base import AtomDatetime
from whaat.reports.types.journal import JournalContent
from whaat.reports.types.memory_curation import CurationReportContent
from whaat.reports.types.session_report import SessionReportContent

ReportState = Literal["done", "applied"]
EnvelopeSource = Literal["meta", "embedded", "derived"]


class Envelope(BaseModel):
    v: int = 1
    kind: str
    title: str
    created_date: date | None = None
    created_at: AtomDatetime | None = None
    session: str | None = None
    repo: str | None = None
    ticket: str | None = None
    writer: str | None = None
    identity: str | None = None
    tags: list[str] = Field(default_factory=list)


class ReportSummary(BaseModel):
    id: str
    key: str = Field(description="An opaque handle for the report, so a URL does not show its path.")
    root: str
    path: str
    envelope: Envelope
    envelope_source: EnvelopeSource
    private: bool
    state: ReportState
    warnings: list[str]


class ReportSection(BaseModel):
    heading: str
    level: int
    markdown: str


class ReportBody(BaseModel):
    format: Literal["markdown"] = "markdown"
    title: str
    pins: list[str]
    sections: list[ReportSection]


ReportContent = Annotated[
    ReportBody | JournalContent | SessionReportContent | CurationReportContent, Field(discriminator="format")
]


class ReportDetail(ReportSummary):
    body: ReportContent
