"""Memory curation from the UI: a button starts the curation run in a terminal session of the chosen identity, and the
report page sends the user's word back into that session: apply-rows with the rows chosen, revert-applied-rows for an
applied row, and Done, which ends the session and types /exit once it printed its closing line. The decisions, notes and
sent stamps live in the report's JSON, not in side files. Without a running session the page shows the call instead."""

import threading
import time
from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from whaat.curation import view as curation_view
from whaat.curation.schemas import (
    CurationStarted,
    DecisionsSent,
    Discarded,
    DoneCall,
    RevertRow,
    RunState,
    SendDecisions,
    StartCuration,
)
from whaat.identities.registry import IdentityRegistry, Principal
from whaat.journal.exceptions import CurationReportNotFoundError, InvalidStoredDocumentError, UnknownRowsError
from whaat.journal.schemas import CurationReportDocument
from whaat.journal.service import JournalService
from whaat.journal.store import CURATION_DIR
from whaat.memory.service import MEMORY_DIR
from whaat.memory.validity import commit_dates
from whaat.reports.store import PRIVATE_ROOT_PREFIX
from whaat.security import require_admin, require_identity
from whaat.terminal.agent import AgentTokenMissingError
from whaat.terminal.projects import FolderError, folder
from whaat.terminal.schemas import TerminalSession
from whaat.terminal.service import Terminals
from whaat.terminal.tmux import Session, SessionNotFoundError, TmuxMissingError, TypingError

router = APIRouter(prefix="/api/v1/curation", tags=["curation"])
AdminDep = Annotated[Principal, Depends(require_admin)]
IdentityDep = Annotated[str, Depends(require_identity)]
LABEL = "memory-curation"
REPORT_CALL = "/whaat:memory-curation report"
# confirmed=report-page: the rows were chosen on the page, which lists the risky ones before sending;
# report page did; without it delete, merge and move rows would wait for a yes in the session
APPLY_CALL = "/whaat:memory-curation apply-rows report={report_id} confirmed=report-page"
REVERT_CALL = "/whaat:memory-curation revert-applied-rows report={report_id} rows={n} confirmed=report-page"
DONE_CALL = "/whaat:session-end steps=none confirmed=report-page"
SESSION_END_DONE = "SESSION-END: nothing open"
WATCH_SECONDS = 3
SCROLLBACK = 300


def _terminals(request: Request) -> Terminals:
    terminals: Terminals = request.app.state.terminals
    return terminals


def _journal(request: Request) -> JournalService:
    journal: JournalService = request.app.state.journal_service
    return journal


TerminalsDep = Annotated[Terminals, Depends(_terminals)]
JournalDep = Annotated[JournalService, Depends(_journal)]


def _view(session: Session) -> TerminalSession:
    return TerminalSession(**asdict(session), idle=session.idle)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _running(terminals: Terminals, identity: str) -> Session | None:
    """The identity's curation session whose claude still runs (not gone, not back at the shell)."""
    sessions = terminals.sessions(identity)
    alive = (s for s in reversed(sessions) if s.label == LABEL and not s.gone)
    return next((s for s in alive if terminals.runs_program(s.name)), None)


def _document(journal: JournalService, report_id: str) -> tuple[str, CurationReportDocument]:
    try:
        return journal.curation_document(report_id)
    except CurationReportNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except InvalidStoredDocumentError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err


def _type(terminals: Terminals, session: Session | None, command: str) -> str | None:
    """Type the call into the session: no busy check (Claude Code queues what is typed), only
    the prompt guard; the reason it was not typed, or None."""
    if session is None:
        return "no curation session runs for this identity"
    try:
        terminals.type_into(session.name, command)
    except (TypingError, SessionNotFoundError) as err:
        return str(err)
    return None


@router.post("/start", response_model=CurationStarted)
def start_curation(body: StartCuration, request: Request, _: AdminDep, terminals: TerminalsDep) -> CurationStarted:
    """Start memory-curation's report in a terminal session of the identity, with its own agent config; a curation
    session already running for it is returned instead of a second one."""
    registry: IdentityRegistry = request.app.state.registry
    if body.identity not in registry.folders():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no identity {body.identity!r}")
    if terminals.launch(body.identity) is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{body.identity} has no agent config: set its Claude config folder in Settings first",
        )
    if running := _running(terminals, body.identity):
        return CurationStarted(session=_view(running), started=False)
    try:
        cwd = folder(body.cwd) if body.cwd else None
    except FolderError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    try:
        session = terminals.create(body.identity, cwd, prompt=REPORT_CALL, label=LABEL)
    except TmuxMissingError as err:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(err)) from err
    except AgentTokenMissingError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    return CurationStarted(session=_view(session), started=True)


@router.get("/view", response_model=curation_view.CurationView)
def curation_page(report_id: str, request: Request, _: AdminDep, journal: JournalDep) -> curation_view.CurationView:
    """What the report page draws beside the report: the memory map and each row's diagram data, from the identity's
    memory as it is now."""
    identity, document = _document(journal, report_id)
    registry: IdentityRegistry = request.app.state.registry
    return curation_view.view(str(registry.folder_of(identity) / MEMORY_DIR), document.body.rows)


@router.post("/decisions", response_model=DecisionsSent)
def send_decisions(body: SendDecisions, _: AdminDep, terminals: TerminalsDep, journal: JournalDep) -> DecisionsSent:
    """Save the user's word per row into the report, then type the apply call into the identity's running curation
    session and stamp the applied rows as sent; a row already sent (and not reverted since) is refused. When no
    session runs, the answer carries the call to paste."""
    _owner, document = _document(journal, body.report_id)
    sent = {row.n for row in document.body.rows if row.sent_at}
    again = sorted(row.n for row in body.rows if row.decision == "apply" and row.n in sent)
    if again:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"already sent: rows {', '.join(map(str, again))}"
        )
    try:
        identity, commit, warnings = journal.save_curation_decisions(body.report_id, body.rows)
    except CurationReportNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except UnknownRowsError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    except InvalidStoredDocumentError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    command = APPLY_CALL.format(report_id=body.report_id)
    applying = [row.n for row in body.rows if row.decision == "apply"]
    session = _running(terminals, identity)
    if not applying:
        detail: str | None = "only discarded rows: nothing to apply, the decisions are saved"
    else:
        detail = _type(terminals, session, command)
    at = None
    if detail is None:
        at = _now()
        journal.mark_curation_sent(body.report_id, applying, at)
    return DecisionsSent(
        commit=commit,
        warnings=warnings,
        command=command,
        session=session.name if session else None,
        typed=detail is None,
        detail=detail,
        at=at,
    )


@router.post("/revert", response_model=DecisionsSent)
def send_revert(body: RevertRow, _: AdminDep, terminals: TerminalsDep, journal: JournalDep) -> DecisionsSent:
    """Type revert-applied-rows for one applied row into the curation session; the row counts as not sent again."""
    identity, document = _document(journal, body.report_id)
    row = next((r for r in document.body.rows if r.n == body.n), None)
    if row is None or not (row.applied or "").strip(" —"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rows must be applied rows of this report")
    command = REVERT_CALL.format(report_id=body.report_id, n=body.n)
    session = _running(terminals, identity)
    detail = _type(terminals, session, command)
    if detail is None:
        journal.mark_curation_sent(body.report_id, [body.n], None)
    return DecisionsSent(
        commit=None,
        warnings=[],
        command=command,
        session=session.name if session else None,
        typed=detail is None,
        detail=detail,
        at=_now() if detail is None else None,
    )


@router.post("/done", response_model=DecisionsSent)
def send_done(body: DoneCall, request: Request, _: AdminDep, terminals: TerminalsDep) -> DecisionsSent:
    """Done on the page: the session-end call with no steps; a watcher then waits for the closing line and types
    /exit. Its state is read from /run-state."""
    session = _running(terminals, body.identity)
    detail = _type(terminals, session, DONE_CALL)
    if detail is None and session is not None:
        runs: dict[str, str] = request.app.state.curation_runs
        runs[body.identity] = "waiting"
        threading.Thread(
            target=_watch_session_end, args=(terminals, session.name, runs, body.identity), daemon=True
        ).start()
    return DecisionsSent(
        commit=None,
        warnings=[],
        command=DONE_CALL,
        session=session.name if session else None,
        typed=detail is None,
        detail=detail,
        at=_now() if detail is None else None,
    )


@router.get("/run-state", response_model=RunState)
def run_state(identity: str, request: Request, _: AdminDep) -> RunState:
    """waiting, asked, exited after Done; open when Done was not sent."""
    runs: dict[str, str] = request.app.state.curation_runs
    return RunState(state=runs.get(identity, "open"))


def _watch_session_end(terminals: Terminals, name: str, runs: dict[str, str], identity: str) -> None:
    """After the session-end call: "waiting" while the session works, "asked" while it is idle without the closing
    line (it asked something), "exited" once /exit went through or the session is gone. Polls every 3 s."""
    skill = DONE_CALL.split()[0]
    while any(s.name == name and not s.gone for s in terminals.sessions(identity)):
        time.sleep(WATCH_SECONDS)
        text = terminals.screen(name, history=SCROLLBACK)
        after = text.rsplit(skill, 1)[-1] if skill in text else text
        prompt, dim = terminals.prompt(name)
        idle = not terminals.busy(name) and prompt is not None and (not prompt or dim)
        if idle and SESSION_END_DONE in after:
            try:
                terminals.type_into(name, "/exit")
            except (TypingError, SessionNotFoundError):
                continue
            runs[identity] = "exited"
            return
        runs[identity] = "asked" if idle and after.strip() else "waiting"
    runs[identity] = "exited"


@router.get("/discarded", response_model=list[Discarded])
def discarded_proposals(request: Request, identity: IdentityDep) -> list[Discarded]:
    """Every proposal the user discarded in this identity's curation reports, newest report first, with whether its
    memory file changed since: a discarded proposal is not made again unless the file changed."""
    registry: IdentityRegistry = request.app.state.registry
    home = registry.folder_of(identity)
    _, last_change = commit_dates(str(home / MEMORY_DIR))
    found: list[Discarded] = []
    for path in sorted((home / CURATION_DIR).rglob("*_memory-curation.json"), reverse=True):
        try:
            document = CurationReportDocument.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        day = (document.envelope.created_date or date.min).isoformat()
        report_id = f"{PRIVATE_ROOT_PREFIX}{identity}:{path.relative_to(home).as_posix()}"
        for row in document.body.rows:
            if row.decision != "reject":
                continue
            changed = last_change.get(row.file, "")
            found.append(
                Discarded(
                    file=row.file,
                    actions=list(row.actions),
                    target=row.target,
                    reason=row.reason,
                    note=row.note,
                    report_id=report_id,
                    report_date=day,
                    changed_since=bool(changed) and changed > day,
                )
            )
    return found
