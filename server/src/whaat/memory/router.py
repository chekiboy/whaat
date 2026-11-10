from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from whaat.distilled.schemas import DistilledAnalysis
from whaat.distilled.store import load_analysis, load_graph
from whaat.git import GitCommitError
from whaat.identities.registry import Principal
from whaat.memory import (
    brain,
    curation_brief,
    fidelity,
    lint,
    migration,
    migration_plans,
    recall,
    rings,
    session_start,
    validity,
)
from whaat.memory.exceptions import InvalidMemoryPathError, MemoryNotFoundError
from whaat.memory.labels import Language
from whaat.memory.schemas import (
    CurationBriefCall,
    CurationRefuteCall,
    FidelityCall,
    FrameCall,
    Framed,
    GuardCall,
    Guarded,
    IdentityMemory,
    LevelCall,
    LintCall,
    MemoryGraph,
    MemoryRoots,
    MemorySave,
    MigrationCall,
    MigrationDecisions,
    MigrationImported,
    MigrationListed,
    MigrationPlanCall,
    MigrationPlanSummary,
    MigrationPlanView,
    MigrationSent,
    MigrationStart,
    PersonalMoved,
    ReadCall,
    ReadsCall,
    RecallDump,
    RecallDumped,
    RecallIndex,
    RecallIndexed,
    RecallOpen,
    RecallOpened,
    RecordCall,
    RevertCall,
    Reverted,
    SavedMemory,
    StartCall,
    Started,
    SubagentCore,
    Text,
)
from whaat.memory.service import MEMORY_DIR, MemoryService
from whaat.security import PrincipalDep, require_identity
from whaat.terminal.agent import AgentTokenMissingError
from whaat.terminal.projects import FolderError, folder
from whaat.terminal.schemas import TerminalSession
from whaat.terminal.service import Terminals
from whaat.terminal.tmux import SessionNotFoundError, TmuxMissingError, TypingError

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


def get_memory_service(request: Request) -> MemoryService:
    service: MemoryService = request.app.state.memory_service
    return service


MemoryServiceDep = Annotated[MemoryService, Depends(get_memory_service)]
IdentityDep = Annotated[str, Depends(require_identity)]


@router.post("/memories", response_model=SavedMemory, status_code=status.HTTP_201_CREATED)
def save_memory(memory: MemorySave, service: MemoryServiceDep, identity: IdentityDep) -> SavedMemory:
    """Write the memory and its index line exactly as given, drop the index lines it supersedes, commit those paths."""
    try:
        return service.save(identity, memory)
    except InvalidMemoryPathError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err


@router.delete("/memories/{path:path}", response_model=SavedMemory)
def delete_memory(path: str, service: MemoryServiceDep, identity: IdentityDep) -> SavedMemory:
    """Remove a memory that was simply wrong and its index line, in one commit."""
    try:
        return service.delete(identity, path)
    except InvalidMemoryPathError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    except MemoryNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err


@router.get("/where", response_model=MemoryRoots)
def memory_where(service: MemoryServiceDep, identity: IdentityDep) -> MemoryRoots:
    """The calling identity's memory root and personal dir, as absolute paths."""
    return service.where(identity)


@router.get("/browse", response_model=list[IdentityMemory])
def browse_memories(request: Request, service: MemoryServiceDep, principal: PrincipalDep) -> list[IdentityMemory]:
    """Every identity's memory for the admin, an identity's own for its token; for reading in the UI."""
    folders = request.app.state.registry.folders()
    identities = sorted(folders) if principal.admin else [principal.identity]
    return service.browse([identity for identity in identities if identity])


def _refused(err: recall.RecallError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err))


@router.post("/recall/index", response_model=RecallIndexed)
def recall_index(call: RecallIndex, service: MemoryServiceDep, identity: IdentityDep) -> dict[str, object]:
    """memory-recall index: the triggers that apply, one memory-recall.log line with the task."""
    try:
        return recall.index(service.roots(identity), call.session, call.task, call.cwd, call.repo, call.key)
    except recall.RecallError as err:
        raise _refused(err) from err


@router.post("/recall/open", response_model=RecallOpened)
def recall_open(call: RecallOpen, service: MemoryServiceDep, identity: IdentityDep) -> dict[str, object]:
    """memory-recall open: one memory with its index line, logged with why and for what purpose."""
    try:
        return recall.open_memory(service.roots(identity), call.session, call.file, call.because, call.purpose)
    except recall.RecallError as err:
        raise _refused(err) from err


@router.post("/recall/dump", response_model=RecallDumped)
def recall_dump(call: RecallDump, service: MemoryServiceDep, identity: IdentityDep) -> dict[str, object]:
    """memory-recall dump: every memory of one dir, for a pass that is not a recall."""
    try:
        return recall.dump(service.roots(identity), call.session, call.dir, call.because, call.purpose)
    except recall.RecallError as err:
        raise _refused(err) from err


@router.post("/recall/frame", response_model=Framed)
def recall_frame(call: FrameCall, service: MemoryServiceDep, identity: IdentityDep) -> Framed:
    """memory-frame: the opened memories as a hook note, each once per agent, logged as inject."""
    opened = [(line.file, line.path) for line in call.opened]
    roots = service.roots(identity)
    context = recall.frame(
        roots, call.session, call.agent, opened, call.force, describe=lambda rel: validity.quality(roots, rel)
    )
    return Framed(context=context)


@router.post("/recall/guard", response_model=Guarded)
def recall_guard(call: GuardCall, service: MemoryServiceDep, identity: IdentityDep) -> Guarded:
    """recall-guard: which of these paths is a memory read outside recall, so the hook can decline it."""
    return Guarded(file=recall.guard(service.roots(identity), call.session, call.paths, call.must_exist))


@router.post("/recall/start", response_model=Started)
def recall_start(call: StartCall, service: MemoryServiceDep, identity: IdentityDep) -> dict[str, object]:
    """memory-where --context: one SessionStart hook's part of an index or of the personal core, the loads logged."""
    return session_start.session_start(
        service.roots(identity), call.level, call.part, call.parts, call.session, call.source, call.key, call.cli
    )


@router.get("/recall/subagent-core", response_model=SubagentCore)
def recall_subagent_core(service: MemoryServiceDep, identity: IdentityDep) -> SubagentCore:
    """The global index, the `reach: every-agent` core files and the memory map, for the SubagentStart hook to give
    a subagent as context."""
    return SubagentCore(text=session_start.subagent_core(service.roots(identity)))


@router.post("/outcome/read", response_model=Text)
def outcome_read(call: ReadCall, service: MemoryServiceDep, identity: IdentityDep) -> Text:
    """memory-outcome --hook: log a Read of a memory and name a history, uncertain or stale one."""
    return Text(text=validity.read_note(service.roots(identity), call.session, call.path))


@router.post("/outcome/reads", response_model=Text)
def outcome_reads(call: ReadsCall, service: MemoryServiceDep, identity: IdentityDep) -> Text:
    """memory-outcome reads: what a session read, opened or dumped, with the purpose and why of each open."""
    return Text(text=validity.reads(service.roots(identity), call.session))


@router.post("/outcome/record", response_model=Text)
def outcome_record(call: RecordCall, service: MemoryServiceDep, identity: IdentityDep) -> Text:
    """memory-outcome record: held, misled or irrelevant per memory; held rescores at once."""
    try:
        return Text(text=validity.record(service.roots(identity), call.session, call.outcome, call.paths))
    except validity.OutcomeError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err


@router.post("/validity/refresh", response_model=Text)
def validity_refresh(service: MemoryServiceDep, identity: IdentityDep) -> Text:
    """memory-validity refresh: score every memory and write memory-validity.json."""
    return Text(text=validity.refresh_summary(service.roots(identity)))


@router.post("/validity/level", response_model=Text)
def validity_level(call: LevelCall, service: MemoryServiceDep, identity: IdentityDep) -> Text:
    """memory-validity level: score and level of these memories, rescoring a stale file first."""
    return Text(text=validity.levels(service.roots(identity), call.paths))


@router.post("/revert", response_model=Reverted)
def revert_memory(call: RevertCall, service: MemoryServiceDep, identity: IdentityDep) -> Reverted:
    """memory-curation's revert-applied-rows: undo commits of this identity's memory, newest first, in one run that a
    conflict aborts whole; a commit outside the memory dir or not in its history is refused."""
    try:
        return Reverted(commits=service.revert(identity, call.commits))
    except GitCommitError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err


@router.post("/migration/groups", response_model=MigrationListed)
def migration_groups(call: MigrationCall, service: MemoryServiceDep, identity: IdentityDep) -> MigrationListed:
    """The groups these sources would bring into this identity's memory, each with its files, which are new, already
    in place or in conflict, and how its index lines come over; reads only, writes nothing."""
    try:
        root = service.folder_of(identity) / MEMORY_DIR
        return migration.listing(root, call, service.identity_folders())
    except migration.MigrationSourceError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err


@router.post("/migration/import", response_model=MigrationImported)
def migration_import(call: MigrationCall, service: MemoryServiceDep, identity: IdentityDep) -> MigrationImported:
    """Copy the named groups into this identity's memory, one commit each: a file already in place is skipped, one in
    conflict is left as it is; the sources' git dates and outcome lines come along; the sources are only read."""
    try:
        with service.lock:
            imported = migration.import_groups(
                service.folder_of(identity), service.committer, call, service.identity_folders()
            )
        validity.refresh(service.roots(identity))
        return imported
    except migration.MigrationSourceError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    except migration.MigrationLayoutError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err


@router.post("/migration/move-personal", response_model=PersonalMoved)
def migration_move_personal(service: MemoryServiceDep, identity: IdentityDep) -> PersonalMoved:
    """The personal memory that still sits at the memory root moves into personal/ with its index, tracked files
    with their history, in one commit; personal/ gets its never-shared mark."""
    try:
        with service.lock:
            return migration.move_personal(service.folder_of(identity), service.committer)
    except migration.MigrationLayoutError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err


MIGRATE_LABEL = "memory-migrate"
MIGRATE_CALL = "/whaat:memory-migrate"
IMPORT_CALL = "/whaat:memory-migrate import plan={plan_id}"


def _plan_identity(request: Request, principal: Principal, identity: str | None) -> str:
    """The admin names the identity; an identity's token always reads its own folder, whatever it names."""
    name = identity if principal.admin else principal.identity
    if name is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="name the identity")
    if name not in request.app.state.registry.folders():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no identity {name!r}")
    return name


def _plan_view(request: Request, service: MemoryService, identity: str, plan_id: str) -> MigrationPlanView:
    folder = service.folder_of(identity)
    try:
        plan = migration_plans.load(folder, plan_id)
        listed = migration.listing(folder / MEMORY_DIR, migration_plans.call_of(plan), service.identity_folders())
    except migration_plans.PlanNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no plan {plan_id!r}") from err
    except migration.MigrationSourceError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    settings = request.app.state.settings
    return MigrationPlanView(
        plan=plan,
        folder=str(folder),
        instance=settings.instance,
        layers_now=migration_plans.layers_now(folder),
        listing=listed,
        url=f"{settings.public_url}/ui/settings/identities/{identity}/migrate?plan={plan.id}",
    )


@router.post("/migration/plans", response_model=MigrationPlanView, status_code=status.HTTP_201_CREATED)
def migration_plan_create(
    request: Request, call: MigrationPlanCall, service: MemoryServiceDep, identity: IdentityDep
) -> MigrationPlanView:
    """Keep what the skill found, with a loose dir's proposed target, as a plan of this identity, for the user to
    choose from on the identity's page; nothing is imported yet."""
    try:
        migration.groups_of(MigrationCall(sources=call.sources), service.identity_folders())
    except migration.MigrationSourceError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    plan = migration_plans.create(identity, service.folder_of(identity), call)
    return _plan_view(request, service, identity, plan.id)


@router.get("/migration/plans", response_model=list[MigrationPlanSummary])
def migration_plan_list(
    request: Request, principal: PrincipalDep, service: MemoryServiceDep, identity: str | None = None
) -> list[MigrationPlanSummary]:
    """The identity's migration plans, newest first."""
    name = _plan_identity(request, principal, identity)
    return migration_plans.summaries(service.folder_of(name))


@router.get("/migration/plans/{plan_id}", response_model=MigrationPlanView)
def migration_plan_get(
    plan_id: str, request: Request, principal: PrincipalDep, service: MemoryServiceDep, identity: str | None = None
) -> MigrationPlanView:
    """The plan with its groups as they stand against the identity's memory now, and who the memory goes to."""
    return _plan_view(request, service, _plan_identity(request, principal, identity), plan_id)


@router.post("/migration/plans/{plan_id}/decisions", response_model=MigrationSent)
def migration_plan_decide(
    plan_id: str, body: MigrationDecisions, request: Request, principal: PrincipalDep, service: MemoryServiceDep
) -> MigrationSent:
    """Save the user's choice from the page into the plan, then type the import call into the identity's running
    migration session; without one, the answer carries the call to paste."""
    if not principal.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="this needs the admin token")
    identity = _plan_identity(request, principal, body.identity)
    folder = service.folder_of(identity)
    try:
        plan = migration_plans.load(folder, plan_id)
    except migration_plans.PlanNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no plan {plan_id!r}") from err
    if plan.imported_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"plan {plan_id} was imported already")
    try:
        decided = migration_plans.decide(folder, plan, body)
        known = {g.id for g in migration.groups_of(migration_plans.call_of(decided), service.identity_folders())}
    except (migration_plans.PlanDecisionError, migration.MigrationSourceError) as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    unknown = [gid for gid in body.groups if gid not in known]
    if unknown:
        migration_plans.save(folder, plan)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"no such group: {', '.join(unknown)}"
        )
    command = IMPORT_CALL.format(plan_id=plan_id)
    terminals: Terminals = request.app.state.terminals
    sessions = (s for s in reversed(terminals.sessions(identity)) if s.label == MIGRATE_LABEL and not s.gone)
    session = next((s for s in sessions if terminals.runs_program(s.name)), None)
    detail = None if session else "no migration session runs for this identity"
    if session:
        try:
            terminals.type_into(session.name, command)
        except (TypingError, SessionNotFoundError) as err:
            detail = str(err)
    if detail is None:
        migration_plans.mark_sent(folder, decided)
    return MigrationSent(
        command=command, session=session.name if session else None, typed=detail is None, detail=detail
    )


@router.post("/migration/plans/{plan_id}/import", response_model=MigrationImported)
def migration_plan_import(plan_id: str, service: MemoryServiceDep, identity: IdentityDep) -> MigrationImported:
    """Import the groups the user chose on the page, as the plan holds them, and keep the result in the plan."""
    folder = service.folder_of(identity)
    try:
        plan = migration_plans.load(folder, plan_id)
    except migration_plans.PlanNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no plan {plan_id!r}") from err
    if plan.groups is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="the user has not chosen on the page yet")
    if plan.imported_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"plan {plan_id} was imported already")
    try:
        with service.lock:
            result = migration.import_groups(
                folder, service.committer, migration_plans.call_of(plan), service.identity_folders()
            )
        migration_plans.record_import(folder, plan, result)
        validity.refresh(service.roots(identity))
        return result
    except migration.MigrationSourceError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    except migration.MigrationLayoutError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err


@router.post("/migration/start", response_model=TerminalSession)
def migration_start(body: MigrationStart, request: Request, principal: PrincipalDep) -> TerminalSession:
    """Start the migration skill in a terminal session of the identity, with its own agent config, in the folder
    given or else in that agent config's folder, never the home folder; one already running is returned instead."""
    if not principal.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="this needs the admin token")
    terminals: Terminals = request.app.state.terminals
    if body.identity not in request.app.state.registry.folders():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no identity {body.identity!r}")
    if terminals.launch(body.identity) is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{body.identity} has no agent config: set its Claude config folder in Settings first",
        )
    alive = (s for s in reversed(terminals.sessions(body.identity)) if s.label == MIGRATE_LABEL and not s.gone)
    if running := next((s for s in alive if terminals.runs_program(s.name)), None):
        return TerminalSession(**asdict(running), idle=running.idle)
    try:
        cwd = folder(body.cwd or request.app.state.preferences.agent_config(body.identity))
        session = terminals.create(body.identity, cwd, prompt=MIGRATE_CALL, label=MIGRATE_LABEL)
    except FolderError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    except TmuxMissingError as err:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(err)) from err
    except AgentTokenMissingError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    return TerminalSession(**asdict(session), idle=session.idle)


@router.post("/lint", response_model=Text)
def memory_lint(request: Request, call: LintCall, service: MemoryServiceDep, identity: IdentityDep) -> Text:
    """memory-curation's memory-lint: mechanical checks over this identity's memory, read-only, a markdown report."""
    repo_roots = list(request.app.state.settings.memory_repo_roots)
    return Text(text=lint.lint(service.roots(identity), repo_roots, call.dup_threshold))


@router.post("/curation-brief", response_model=Text)
def memory_curation_brief(
    request: Request, call: CurationBriefCall, service: MemoryServiceDep, identity: IdentityDep
) -> Text:
    """memory-curation's judge brief for one dir: the skill's fixed text, how to read the dir and its candidates from
    the lint's checks; the run passes it to its judge as it is, adding nothing."""
    scan = lint.scan(service.roots(identity), list(request.app.state.settings.memory_repo_roots))
    rel = "" if call.dir.strip("/") in ("", ".") else call.dir.strip("/")
    if rel not in curation_brief.dirs(scan):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{call.dir!r} is not a memory dir")
    return Text(text=curation_brief.brief(scan, rel))


def _graph_identity(request: Request, principal: Principal, identity: str | None) -> str:
    name = identity if principal.admin else principal.identity
    if name is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="name the identity")
    if name not in request.app.state.registry.folders():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no identity {name!r}")
    return name


@router.get("/graph", response_model=MemoryGraph)
def memory_graph(
    request: Request, service: MemoryServiceDep, principal: PrincipalDep, identity: str | None = None
) -> MemoryGraph:
    """One identity's memories as nodes and edges: the admin names any identity, an identity's token reads its own."""
    return service.graph(_graph_identity(request, principal, identity))


@router.get("/brain", response_class=HTMLResponse)
def memory_brain(
    request: Request,
    service: MemoryServiceDep,
    principal: PrincipalDep,
    identity: str | None = None,
    embed: bool = False,
    lang: Language = "en",
) -> HTMLResponse:
    """The Emlékagy on this identity's memory graph: the whole page, or with embed only the drawing, for the memory page
    to frame and drive (its chips, search and card are the page's). When the identity keeps a distillate, it is drawn
    too, faint."""
    name = _graph_identity(request, principal, identity)
    folder = request.app.state.registry.folder_of(name)
    html = brain.cached(
        f"{name}:{embed}:{lang}",
        lambda: brain.render(service.graph(name), embed, load_graph(folder), lang),
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.get("/analysis", response_model=DistilledAnalysis)
def memory_analysis(request: Request, principal: PrincipalDep, identity: str | None = None) -> DistilledAnalysis:
    """The analysis of this identity's kept distillate, for the memory page's Elemzés to draw: the arc, the heatmap,
    the autonomy ladder and changed views, the hub sessions and my reading."""
    name = _graph_identity(request, principal, identity)
    found = load_analysis(request.app.state.registry.folder_of(name))
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{name!r} keeps no distillate")
    return found


@router.get("/rings", response_class=HTMLResponse)
def memory_rings(
    request: Request,
    service: MemoryServiceDep,
    principal: PrincipalDep,
    identity: str | None = None,
    embed: bool = False,
    lang: Language = "en",
) -> HTMLResponse:
    """The Memória-gyűrűk on this identity's memory: the whole page, or with embed only the drawing, for the memory page
    to frame and drive (its chips and card are the page's)."""
    name = _graph_identity(request, principal, identity)
    html = rings.cached(
        f"{name}:{embed}:{lang}", lambda: rings.render(name, service.browse([name])[0].layers, embed, lang)
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.post("/curation-refute-brief", response_model=Text)
def memory_curation_refute_brief(
    request: Request, call: CurationRefuteCall, service: MemoryServiceDep, identity: IdentityDep
) -> Text:
    """memory-curation's refuter brief for one dir: the skill's fixed text and that dir's judge rows, as they came."""
    scan = lint.scan(service.roots(identity), list(request.app.state.settings.memory_repo_roots))
    rel = "" if call.dir.strip("/") in ("", ".") else call.dir.strip("/")
    if rel not in curation_brief.dirs(scan):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{call.dir!r} is not a memory dir")
    return Text(text=curation_brief.refute_brief(scan, rel, call.rows))


@router.post("/fidelity", response_model=Text)
def memory_fidelity(call: FidelityCall, service: MemoryServiceDep, identity: IdentityDep) -> Text:
    """After a merge, split or trim: every sentence of the memory as it was, and whether the new text keeps it word
    for word; the rest is the agent's to account for before the commit."""
    try:
        return Text(text=fidelity.table(Path(service.roots(identity).store), call.file, call.rev, call.new))
    except FileNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
