from typing import Literal

from pydantic import Field

from whaat.reports.types.base import Strict
from whaat.reports.types.journal import BODY_VERSION, NOT_RECORDED, Text


class Outcome(Strict):
    status: Literal["done", "partly_done", "stuck"]
    line: Text = Field(description="The outcome in one line.")
    summary: Text = Field(description="Two or three sentences: what exists now that did not before.")


class DecisionOption(Strict):
    text: Text = Field(description="The option, with what it gives and what it costs.")
    chosen: bool
    note: str | None = Field(default=None, description="For an option not chosen: why it lost.")


class Decision(Strict):
    id: Text = Field(description="DU-1, DU-2 … for the user's decisions; DC-1 … for mine.")
    by: Literal["user", "claude"] = Field(
        description="The user's: they stated it or picked it from options I offered. Mine: I chose without asking"
        " and they let it stand. An assumption of mine they corrected is drift, not a decision."
    )
    title: Text
    options: list[DecisionOption] = Field(
        description="The options that were really on the table; one taken without weighing any alternative says so."
    )
    why: Text = Field(
        description="The user's reason in their words (none given says so, never one I make up), or for mine the"
        " facts it rested on and why I did not ask."
    )


class Drift(Strict):
    id: Text = Field(description="DF-1, DF-2 …")
    title: Text = Field(description="From what to what.")
    cause: Text = Field(description="The user changed the goal, I misread it, the code showed something else…")


class OpenQuestion(Strict):
    id: Text = Field(description="Q1, Q2 …")
    text: Text


class SessionReportBodyIn(Strict):
    topic: Text = Field(description="The session in one line.")
    outcome: Outcome | None = Field(description="How the session ended." + NOT_RECORDED)
    repo: str | None = Field(description="The repo the session worked in; null outside a repository.")
    branch: str | None
    transcript: str | None = Field(description="Path of the session's transcript.")
    task: Text | None = Field(
        description="What the user asked, in their words where it helps, and why they needed it." + NOT_RECORDED
    )
    steps: list[Text] | None = Field(description="What we did, chronologically, one line per step." + NOT_RECORDED)
    decisions: list[Decision] | None = Field(description="The decisions, the user's and mine." + NOT_RECORDED)
    drift: list[Drift] | None = Field(description="Where we drifted and why." + NOT_RECORDED)
    open_questions: list[OpenQuestion] | None = Field(description="Questions and todos left open." + NOT_RECORDED)


class SessionReportBody(SessionReportBodyIn):
    v: int = BODY_VERSION


class SessionReportContent(Strict):
    format: Literal["session-report"] = "session-report"
    report: SessionReportBody
