"""memory-curation's report as a typed body (lint summary, the row table, what could not be checked), so the report is
written once and whaat draws it."""

from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from whaat.reports.types.base import Strict
from whaat.reports.types.journal import BODY_VERSION

Text = Annotated[str, StringConstraints(min_length=1)]
CurationAction = Literal["merge", "move", "delete", "split", "trim", "retrigger", "verify", "fix"]
# the user's word on a row, set on the report page
RowDecision = Literal["apply", "reject"]


class CurationRow(Strict):
    n: int = Field(ge=1, description="The row number the user picks it by.")
    file: Text = Field(description="The memory file, below the memory root.")
    # one row is one change the user approves at once: actions that build on each other run in this order
    actions: list[CurationAction] = Field(
        min_length=1,
        description="The row's actions in the order they run; more than one only when they build on each other.",
    )
    target: str | None = Field(
        description="The file to merge into, the level to move to, the new index line, the split file names, or for"
        " a fix the corrected text; null when the actions have none."
    )
    reason: Text
    evidence: str | None = Field(
        description="The other file's name, the ref and missing path, the doc that already says it; null when none."
    )
    applied: str | None = Field(
        default=None, description="Empty until apply-rows fills it with the row's commits (`store <sha>`)."
    )
    decision: RowDecision | None = Field(default=None, description="The user's word on the row; null until given.")
    note: str | None = Field(
        default=None, description="The user's note on the row: it can narrow or change what the row does."
    )

    @model_validator(mode="before")
    @classmethod
    def _one_action_of_older_reports(cls, data: Any) -> Any:
        """Reports saved before 2026-11-06 hold one `action` per row; read them as a one-element `actions`."""
        if isinstance(data, dict) and "action" in data and "actions" not in data:
            data = {**data, "actions": [data["action"]]}
            del data["action"]
        return data

    @field_validator("actions")
    @classmethod
    def _each_action_once(cls, actions: list[str]) -> list[str]:
        if len(actions) != len(set(actions)):
            raise ValueError("an action appears once in a row")
        return actions

    sent_at: str | None = Field(
        default=None,
        description="Set by whaat, never by the agent: when the apply call carrying this row was typed into the"
        " session (YYYY-MM-DD HH:MM); emptied when a revert of the row is sent.",
    )


class CurationSection(Strict):
    heading: Text
    markdown: Text


class CurationReportBodyIn(Strict):
    lint_summary: Text = Field(description="The lint summary: index sizes and the problem counts by check.")
    rows: list[CurationRow] = Field(description="One row per change; kept files are not listed.")
    unchecked: Text = Field(description="What could not be checked, and why.")
    sections: list[CurationSection] = Field(
        default_factory=list,
        description="Any further part the report needs (what was judged and let go, refs), each as markdown.",
    )

    @field_validator("rows")
    @classmethod
    def _numbers_are_unique(cls, rows: list[CurationRow]) -> list[CurationRow]:
        numbers = [row.n for row in rows]
        if len(numbers) != len(set(numbers)):
            raise ValueError("row numbers must be unique")
        return rows


class CurationReportBody(CurationReportBodyIn):
    v: int = BODY_VERSION


class CurationReportContent(Strict):
    format: Literal["memory-curation"] = "memory-curation"
    report: CurationReportBody
