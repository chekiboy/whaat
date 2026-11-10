from pydantic import BaseModel, Field

from whaat.journal.schemas import CurationDecision
from whaat.reports.types.base import Strict
from whaat.terminal.schemas import TerminalSession


class StartCuration(Strict):
    identity: str = Field(description="Whose memory to curate; its own agent config runs the session.")
    cwd: str | None = Field(default=None, description="The folder to start in; the configured folder if none.")


class CurationStarted(BaseModel):
    session: TerminalSession
    started: bool = Field(description="False when a curation session of this identity was already running.")


class Discarded(BaseModel):
    file: str
    actions: list[str] = Field(
        description="The rejected row's actions, in order; a new row repeats it only with the same list."
    )
    target: str | None
    reason: str
    note: str | None = Field(description="The user's note on the discarded row.")
    report_id: str
    report_date: str
    changed_since: bool = Field(
        description="The memory file changed after that report's day: the proposal may be made again, saying so."
    )


class SendDecisions(Strict):
    report_id: str
    rows: list[CurationDecision]


class DecisionsSent(BaseModel):
    commit: str | None
    warnings: list[str]
    command: str = Field(description="The call that applies the decisions; typed into the session when it runs.")
    session: str | None = Field(description="The curation session it was typed into, or would have been.")
    typed: bool
    detail: str | None = Field(description="Why it was not typed: no running session, or the prompt readback.")
    at: str | None = Field(default=None, description="When it was typed (YYYY-MM-DD HH:MM); null when it was not.")


class RevertRow(Strict):
    report_id: str
    n: int = Field(ge=1)


class DoneCall(Strict):
    identity: str


class RunState(BaseModel):
    state: str = Field(description="open (Done not sent), waiting, asked or exited.")
