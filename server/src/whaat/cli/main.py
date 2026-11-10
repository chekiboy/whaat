import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Annotated, Any

import typer
import uvicorn

from whaat.config import Settings, load_settings
from whaat.git import GitCommitter
from whaat.identities.registry import IdentityRegistry
from whaat.main import create_app
from whaat.memory import migration_summary
from whaat.platform.browser import open_app_window, open_url
from whaat.platform.instance_lock import InstanceRunningError, bind_listener
from whaat.platform.process import spawn_detached
from whaat.platform.repo_key import repo_key
from whaat.reports.store import report_key
from whaat.security import load_or_create_token
from whaat.terminal import agent

SERVER_LOG_NAME = "server.log"
ENSURE_TIMEOUT_SECONDS = 15.0
WHERE_PATHS = {"store": "memory", "state": "state", "personal": "personal"}

app = typer.Typer(help="Whaat?! Not just an agent. An agent with a past.", no_args_is_help=True)
journal_app = typer.Typer(
    help="The journal: one file per session in an identity's private folder.", no_args_is_help=True
)
app.add_typer(journal_app, name="journal")
identity_app = typer.Typer(help="Identities: each with its own folder and token.", no_args_is_help=True)
app.add_typer(identity_app, name="identity")
memory_app = typer.Typer(help="The calling identity's memory, layer by layer.", no_args_is_help=True)
app.add_typer(memory_app, name="memory")


def _health_url(settings: Settings) -> str:
    return f"http://{settings.host}:{settings.port}/api/v1/health"


def _probe(settings: Settings) -> dict[str, object] | None:
    """What answers on the configured address: its health, or None when nothing (or something not whaat) does."""
    try:
        with urllib.request.urlopen(_health_url(settings), timeout=1) as response:
            health = json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return health if isinstance(health, dict) and health.get("app") == "whaat" else None


class ForeignInstanceError(Exception):
    def __init__(self, settings: Settings, found: object) -> None:
        super().__init__(
            f"the whaat on {settings.host}:{settings.port} is the {found or 'unnamed'} instance,"
            f" not {settings.instance}; refusing to use it."
            " Give this instance its own port (WHAAT_PORT) or stop the other one."
        )


def running_instance(settings: Settings, health: dict[str, object] | None) -> bool:
    """True when our instance answers, False when nothing does; another instance is an error, never a fallback."""
    if health is None:
        return False
    if health.get("instance") != settings.instance:
        raise ForeignInstanceError(settings, health.get("instance"))
    return True


@app.command()
def serve() -> None:
    """Run the server in the foreground."""
    settings = load_settings()
    try:
        sock = bind_listener(settings.host, settings.port)
    except InstanceRunningError as err:
        typer.echo(str(err), err=True)
        raise typer.Exit(1) from err
    token = load_or_create_token(settings.state_dir)
    server = uvicorn.Server(uvicorn.Config(create_app(settings, token), log_level="info"))
    typer.echo(f"whaat {settings.instance} listens on {settings.public_url} ({settings.host}:{settings.port})")
    server.run(sockets=[sock])


def _ensure_running(settings: Settings) -> str:
    try:
        return _start_unless_running(settings)
    except ForeignInstanceError as err:
        typer.echo(str(err), err=True)
        raise typer.Exit(1) from err


def _start_unless_running(settings: Settings) -> str:
    where = f"{settings.instance} on {settings.public_url}"
    if running_instance(settings, _probe(settings)):
        return f"whaat {where} already runs"
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    log_path = settings.state_dir / SERVER_LOG_NAME
    with log_path.open("ab") as log:
        spawn_detached([sys.executable, "-m", "whaat", "serve"], log)
    deadline = time.monotonic() + ENSURE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if running_instance(settings, _probe(settings)):
            return f"whaat {where} started"
        time.sleep(0.2)
    typer.echo(f"whaat did not answer within {ENSURE_TIMEOUT_SECONDS:.0f}s; see {log_path}", err=True)
    raise typer.Exit(1)


@app.command()
def ensure() -> None:
    """Start the server in the background unless it already runs."""
    typer.echo(_ensure_running(load_settings()))


def claude_settings_file(global_: bool, cwd: Path, environ: Mapping[str, str]) -> Path:
    """The project's own local settings, or with --global the settings of the Claude config dir in use."""
    if global_:
        return Path(environ.get("CLAUDE_CONFIG_DIR") or "~/.claude").expanduser() / "settings.json"
    return cwd / ".claude" / "settings.local.json"


def _connect_token(settings: Settings, identity: str) -> str:
    """The identity's kept token; a new identity is made first, so its token never shows."""
    admin = load_or_create_token(settings.state_dir)
    registry = IdentityRegistry(settings, admin, GitCommitter())
    if identity not in registry.folders():
        return str(_post_json(settings, "/api/v1/identities", {"id": identity}, admin)["token"])
    token = registry.stored_token(identity)
    if not token:
        typer.echo(
            f"whaat keeps no token for {identity}: give it a new token in Settings, Identities"
            " (the old one stops working), then connect again.",
            err=True,
        )
        raise typer.Exit(1)
    return token


def _warn_unless_ignored(settings_file: Path) -> None:
    folder = settings_file.parent.parent
    found = subprocess.run(
        ["git", "check-ignore", "-q", str(settings_file)], cwd=folder, capture_output=True, check=False
    )
    if found.returncode == 1:
        typer.echo(
            f"{settings_file.relative_to(folder)} is not ignored by git and now holds a token: add it to .gitignore.",
            err=True,
        )


@app.command()
def connect(
    identity: Annotated[str, typer.Argument(help="The identity the agent works as; made when it does not exist.")],
    global_: Annotated[
        bool, typer.Option("--global", help="Work as this identity in every project, not only in this folder.")
    ] = False,
) -> None:
    """Connect Claude Code to whaat: sessions started in this folder work as this identity, its token in the
    project's local settings only. whaat's plugin goes into the user's Claude settings, since Claude Code does
    not load plugin folders from a project's settings. Starts the server when it does not run."""
    identity_file = claude_settings_file(global_, Path.cwd(), os.environ)
    plugin_file = claude_settings_file(True, Path.cwd(), os.environ)
    try:
        agent.check_writable(identity_file)
        agent.check_writable(plugin_file)
    except agent.SettingsUnreadableError as err:
        typer.echo(str(err), err=True)
        raise typer.Exit(1) from err
    settings = load_settings()
    typer.echo(_ensure_running(settings), err=True)
    agent.write_agent_env(identity_file, agent.agent_env(_connect_token(settings, identity), settings))
    agent.add_connector(plugin_file)
    if not global_:
        _warn_unless_ignored(identity_file)
    typer.echo(f"connected: sessions reading {identity_file} work as {identity} on whaat {settings.instance}")
    typer.echo(f"whaat's plugin loads from {plugin_file}")


def report_url(settings: Settings, report_id: str) -> str:
    return f"{settings.public_url}/ui/reports/{report_key(report_id)}"


@app.command("open")
def open_report(report_id: Annotated[str, typer.Argument(help="The report's id, as the API gives it.")]) -> None:
    """Open a report in the UI, starting the server first if needed."""
    settings = load_settings()
    typer.echo(_ensure_running(settings), err=True)
    url = report_url(settings, report_id)
    open_url(url, settings.browser)
    typer.echo(url)


@app.command("show")
def show_report(report_id: Annotated[str, typer.Argument(help="The report's id, as the API gives it.")]) -> None:
    """Print a report as JSON (its envelope and body), as WHAAT_TOKEN's identity sees it."""
    settings = load_settings()
    token = _identity_token(settings)
    typer.echo(_ensure_running(settings), err=True)
    request = urllib.request.Request(
        f"http://{settings.host}:{settings.port}/api/v1/reports/{urllib.parse.quote(report_id, safe=':/')}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            typer.echo(json.dumps(json.load(response), indent=2, ensure_ascii=False))
    except urllib.error.HTTPError as err:
        typer.echo(f"whaat refused it ({err.code}): {err.read().decode('utf-8', 'replace')}", err=True)
        raise typer.Exit(1) from err


APP_PROFILE_DIR = "app-window"


@app.command("app")
def open_app() -> None:
    """Open the UI in an app window (no tabs, no address bar), starting the server first if needed."""
    settings = load_settings()
    typer.echo(_ensure_running(settings), err=True)
    url = f"{settings.public_url}/ui/"
    if not open_app_window(url, settings.state_dir / APP_PROFILE_DIR):
        typer.echo("no Chrome, Chromium, Edge or Brave found: opening the default browser", err=True)
        open_url(url, settings.browser)
    typer.echo(url)


@app.command()
def openapi() -> None:
    """Print the API contract (openapi.json)."""
    settings = Settings(shared_roots={}, identities={}, state_dir=load_settings().state_dir)
    schema = create_app(settings, token="").openapi()
    typer.echo(json.dumps(schema, indent=2, sort_keys=True))


def _identity_token(settings: Settings) -> str:
    """The calling identity's own token; never the admin token, so nobody writes in another's name."""
    if not settings.agent_token:
        typer.echo(
            "WHAAT_TOKEN is not set: give this agent its identity's token (from `whaat identity add <id>`)"
            " in its env or its Claude config's settings.json env.",
            err=True,
        )
        raise typer.Exit(1)
    return settings.agent_token


def _post_to_whaat(settings: Settings, path: str, payload: dict[str, object], token: str) -> None:
    typer.echo(_ensure_running(settings), err=True)
    typer.echo(json.dumps(_post_json(settings, path, payload, token), indent=2, ensure_ascii=False))


def _post_json(settings: Settings, path: str, payload: dict[str, object], token: str) -> Any:
    request = urllib.request.Request(
        f"http://{settings.host}:{settings.port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        typer.echo(f"whaat refused it ({err.code}): {err.read().decode('utf-8', 'replace')}", err=True)
        raise typer.Exit(1) from err


def _stdin_json() -> object:
    try:
        return json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except ValueError as err:
        typer.echo(f"stdin is not JSON: {err}", err=True)
        raise typer.Exit(1) from err


def _iso_date(value: str | None) -> str | None:
    return date.fromisoformat(value).isoformat() if value else None


SessionOption = Annotated[str, typer.Option(help="The first 8 characters of the session id.")]
TagOption = Annotated[list[str] | None, typer.Option(help="A topic of the session; repeat it for more.")]
DateOption = Annotated[str | None, typer.Option("--date", help="YYYY-MM-DD of the file; today when left out.")]


@journal_app.command("save")
def save_journal_entry(session: SessionOption, tag: TagOption = None, entry_date: DateOption = None) -> None:
    """Save the journal block read from stdin as JSON, as WHAAT_TOKEN's identity; starts the server if needed."""
    settings = load_settings()
    token = _identity_token(settings)
    _post_to_whaat(
        settings,
        "/api/v1/journal/entries",
        {"session": session, "entry_date": _iso_date(entry_date), "tags": tag or [], "block": _stdin_json()},
        token,
    )


@journal_app.command("save-report")
def save_session_report(
    session: SessionOption,
    slug: Annotated[str, typer.Option(help="A few words of the topic; kept from the session's first report.")],
    tag: TagOption = None,
    entry_date: DateOption = None,
) -> None:
    """Save the session report read from stdin as JSON, replacing the session's report; starts the server if needed."""
    settings = load_settings()
    token = _identity_token(settings)
    _post_to_whaat(
        settings,
        "/api/v1/journal/session-reports",
        {
            "session": session,
            "slug": slug,
            "entry_date": _iso_date(entry_date),
            "tags": tag or [],
            "report": _stdin_json(),
        },
        token,
    )


@journal_app.command("save-curation")
def save_curation_report(entry_date: DateOption = None) -> None:
    """Save memory-curation's report from stdin as JSON, replacing that day's report; starts the server if needed."""
    settings = load_settings()
    token = _identity_token(settings)
    _post_to_whaat(
        settings,
        "/api/v1/journal/curation-reports",
        {"entry_date": _iso_date(entry_date), "report": _stdin_json()},
        token,
    )


@journal_app.command("save-applied")
def save_curation_applied(
    report: Annotated[str, typer.Option(help="The curation report's id, as the apply call names it.")],
) -> None:
    """Write apply-rows' Applied cells, read from stdin as [{"n": 1, "applied": "store <sha>"}]; null empties one."""
    settings = load_settings()
    token = _identity_token(settings)
    _post_to_whaat(
        settings, "/api/v1/journal/curation-reports/applied", {"report_id": report, "rows": _stdin_json()}, token
    )


@journal_app.command("discarded")
def discarded_proposals() -> None:
    """The proposals the user discarded in this identity's curation reports, and whether each file changed since."""
    settings = load_settings()
    token = _identity_token(settings)
    typer.echo(_ensure_running(settings), err=True)
    request = urllib.request.Request(
        f"http://{settings.host}:{settings.port}/api/v1/curation/discarded",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        typer.echo(json.dumps(json.load(response), indent=2, ensure_ascii=False))


@identity_app.command("add")
def add_identity(identity: Annotated[str, typer.Argument(help="The new identity's id.")]) -> None:
    """Give an identity its own folder and token, with the admin token; prints the token once."""
    settings = load_settings()
    _post_to_whaat(settings, "/api/v1/identities", {"id": identity}, load_or_create_token(settings.state_dir))


@memory_app.command("where")
def memory_where(
    path: Annotated[str | None, typer.Argument(help="A directory in the repo; the current one when left out.")] = None,
    which: Annotated[
        str | None, typer.Option("--path", help="store, state or personal: print that one location only.")
    ] = None,
) -> None:
    """Print the calling identity's global, project and repo memory dirs for a path."""
    if which is not None and which not in WHERE_PATHS:
        typer.echo("whaat memory where: --path takes store, state or personal", err=True)
        raise typer.Exit(1)
    settings = load_settings()
    token = _identity_token(settings)
    typer.echo(_ensure_running(settings), err=True)
    request = urllib.request.Request(
        f"http://{settings.host}:{settings.port}/api/v1/memory/where", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        roots = json.load(response)
    if which is not None:
        typer.echo(roots[WHERE_PATHS[which]])
        return
    store = Path(roots["memory"])
    key = repo_key(Path(path or ".").expanduser().resolve())
    typer.echo(f"global  {store}")
    if key:
        typer.echo(f"project {store / key[0]}")
        typer.echo(f"repo    {store / key[0] / key[1]}")
    else:
        typer.echo("project -  (not a git repo)")


@memory_app.command("save")
def save_memory() -> None:
    """Write the memory read from stdin as JSON (path, content, trigger, unindex) exactly as given, and commit it."""
    settings = load_settings()
    token = _identity_token(settings)
    _post_to_whaat(settings, "/api/v1/memory/memories", _object_from_stdin(), token)


@memory_app.command("delete")
def memory_delete(path: Annotated[str, typer.Argument(help="The memory's path below the memory root.")]) -> None:
    """Remove a memory that was simply wrong and its index line, in one commit."""
    settings = load_settings()
    token = _identity_token(settings)
    typer.echo(_ensure_running(settings), err=True)
    request = urllib.request.Request(
        f"http://{settings.host}:{settings.port}/api/v1/memory/memories/{urllib.parse.quote(path)}",
        headers={"Authorization": f"Bearer {token}"},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            typer.echo(json.dumps(json.load(response), indent=2, ensure_ascii=False))
    except urllib.error.HTTPError as err:
        typer.echo(f"whaat refused it ({err.code}): {err.read().decode('utf-8', 'replace')}", err=True)
        raise typer.Exit(1) from err


RECALL_USAGE = """The one way to read this identity's memories, as memory-recall:

    whaat memory index task="<what you are doing>" [path=<dir> | repo=<group or group/repo>]
    whaat memory open file=<path index printed> because="<which words of its trigger match the task>"
                      [purpose=recall|save|curate|review|load] [force=1]
    whaat memory dump dir=<memory-relative dir> purpose=curate|review|save because="<why>"
"""
NameValues = Annotated[list[str] | None, typer.Argument(help="name=value pairs, as memory-recall takes them.")]


def _name_values(argv: list[str] | None) -> dict[str, str]:
    out = {}
    for arg in argv or []:
        key, sep, value = arg.partition("=")
        if not sep:
            typer.echo(f"whaat memory: '{arg}' is not name=value\n\n{RECALL_USAGE}", err=True)
            raise typer.Exit(1)
        out[key] = value
    return out


def _recall(op: str, payload: dict[str, object]) -> dict[str, Any]:
    """POST one recall call with this session's id; a refusal prints memory-recall's message and exits 1."""
    return _memory_call(f"recall/{op}", {"session": _session(), **payload})


def _session() -> str:
    return os.environ.get("CLAUDE_CODE_SESSION_ID", "")[:8]


def _memory_call(path: str, payload: dict[str, object]) -> dict[str, Any]:
    """POST to /api/v1/memory/<path> with this identity's token; a refusal prints the script's message and exits 1."""
    settings = load_settings()
    token = _identity_token(settings)
    typer.echo(_ensure_running(settings), err=True)
    request = urllib.request.Request(
        f"http://{settings.host}:{settings.port}/api/v1/memory/{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result: dict[str, Any] = json.load(response)
            return result
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")
        try:
            detail = json.loads(body)["detail"]
        except (ValueError, KeyError, TypeError):
            detail = body
        typer.echo(detail if isinstance(detail, str) else f"whaat refused it ({err.code}): {body}", err=True)
        raise typer.Exit(1) from err


@memory_app.command("index", help=RECALL_USAGE)
def recall_index(args: NameValues = None) -> None:
    a = _name_values(args)
    cwd = a.get("path") or os.getcwd()
    key = None if a.get("repo") else repo_key(Path(cwd).expanduser().resolve())
    found = _recall(
        "index", {"task": a.get("task", ""), "cwd": cwd, "repo": a.get("repo"), "key": list(key) if key else None}
    )
    typer.echo(f"store {found['store']}")
    typer.echo('Open a memory only through: whaat memory open file=<path below> because="<trigger words that match>"\n')
    for section in found["sections"]:
        typer.echo(f"## {section['label']}: {section['prefix'] or '(store root)'}")
        if section["entries"] is None:
            typer.echo("(no index)\n")
            continue
        for entry in section["entries"]:
            typer.echo(f"- {entry['file']} — {entry['trigger']}")
        typer.echo()


@memory_app.command("open", help=RECALL_USAGE)
def recall_open(args: NameValues = None) -> None:
    a = _name_values(args)
    opened = _recall("open", {"file": a.get("file", ""), "because": a.get("because", ""), "purpose": a.get("purpose")})
    if opened["text"] is None:
        typer.echo(
            f"opened: {opened['file']} -> {opened['path']}\n(the text arrives as a hook note; if none follows, the"
            " memory-frame hook is not installed: install the whaat plugin with its hooks)"
        )
        return
    typer.echo(f"# {opened['file']}\nindex: {opened['trigger'] or '(no index line: history or unindexed)'}\n")
    typer.echo(opened["text"])


@memory_app.command("dump", help=RECALL_USAGE)
def recall_dump(args: NameValues = None) -> None:
    a = _name_values(args)
    dumped = _recall("dump", {"dir": a.get("dir", ""), "because": a.get("because", ""), "purpose": a.get("purpose")})
    for file in dumped["files"]:
        typer.echo(f"===== {file['file']}\n{file['text']}")


validity_app = typer.Typer(help="Scores of this identity's memories, as memory-validity.", no_args_is_help=True)
memory_app.add_typer(validity_app, name="validity")


def _print_text(result: dict[str, Any]) -> None:
    if result.get("text"):
        typer.echo(result["text"])


@memory_app.command("reads")
def outcome_reads(
    session: Annotated[
        str | None, typer.Argument(help="The session's first 8 characters; this one when left out.")
    ] = None,
) -> None:
    """What a session read or opened through recall, as memory-outcome reads (subagents share the session)."""
    session = session or _session()
    if not session:
        typer.echo("no session id: pass <session8>, or run inside Claude Code", err=True)
        raise typer.Exit(1)
    _print_text(_memory_call("outcome/reads", {"session": session}))


@memory_app.command("record")
def outcome_record(
    outcome: Annotated[str, typer.Argument(help="held | misled | irrelevant")],
    paths: Annotated[list[str], typer.Argument(help="Memory paths as `reads` prints them.")],
) -> None:
    """Record whether recalled memories held up, as memory-outcome record; held rescores at once."""
    _print_text(_memory_call("outcome/record", {"session": _session(), "outcome": outcome, "paths": paths}))


@validity_app.command("refresh")
def validity_refresh() -> None:
    """Score every memory and write memory-validity.json in the identity's state dir."""
    _print_text(_memory_call("validity/refresh", {}))


@validity_app.command("level")
def validity_level(paths: Annotated[list[str], typer.Argument(help="Memory paths, relative or absolute.")]) -> None:
    """Score and level of these memories, rescoring a file from an earlier day first."""
    _print_text(_memory_call("validity/level", {"paths": paths}))


@memory_app.command("revert")
def memory_revert(
    commits: Annotated[list[str], typer.Argument(help="The commits to undo, newest first or any order.")],
) -> None:
    """Undo commits of this identity's memory, as memory-curation's revert-applied-rows does; prints the new commits."""
    typer.echo(json.dumps(_memory_call("revert", {"commits": commits}), indent=2))


JsonFlag = Annotated[bool, typer.Option("--json", help="The whole answer as JSON instead of the summary.")]


@memory_app.command("migration-groups")
def memory_migration_groups(as_json: JsonFlag = False) -> None:
    """What the sources on stdin ({"sources": [{path, kind, target}]}) would bring into this identity, group by group;
    reads only."""
    answer = _memory_call("migration/groups", _object_from_stdin())
    summary = "\n".join(migration_summary.listing(answer["groups"], answer["warnings"]))
    typer.echo(json.dumps(answer, indent=2, ensure_ascii=False) if as_json else summary)


@memory_app.command("import")
def memory_import(args: NameValues = None, as_json: JsonFlag = False) -> None:
    """plan=<id>: import the groups the user chose on the page for that plan. Without plan=, the call on stdin
    ({"sources": […], "groups": [ids], "state": dir}). One commit per group; prints what came, what was skipped and
    what is in conflict."""
    plan = _name_values(args).get("plan")
    result = (
        _memory_call(f"migration/plans/{plan}/import", {})
        if plan
        else _memory_call("migration/import", _object_from_stdin())
    )
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False) if as_json else migration_summary.imported(result))


@memory_app.command("migration-plan")
def memory_migration_plan(as_json: JsonFlag = False) -> None:
    """Keep the sources on stdin ({"sources": [{path, kind, target}], "state": dir}) as a plan for the user to choose
    from on this identity's page; the session is this process's own, as recall's is. Prints the plan, the page's url
    and its groups with their counts."""
    view = _memory_call("migration/plans", {**_object_from_stdin(), "session": _session()})
    typer.echo(json.dumps(view, indent=2, ensure_ascii=False) if as_json else migration_summary.plan(view))


@memory_app.command("move-personal")
def memory_move_personal() -> None:
    """Move the personal memory that still sits at the memory root into personal/, in one commit."""
    typer.echo(json.dumps(_memory_call("migration/move-personal", {}), indent=2, ensure_ascii=False))


@memory_app.command("lint")
def memory_lint(
    dup_threshold: Annotated[float, typer.Option(help="Name+description word overlap that marks a duplicate.")] = 0.4,
) -> None:
    """Mechanical checks over this identity's memory, as memory-curation's memory-lint; read-only."""
    _print_text(_memory_call("lint", {"dup_threshold": dup_threshold}))


@memory_app.command("curation-brief")
def memory_curation_brief(args: NameValues = None) -> None:
    """memory-curation's judge brief for one dir (dir=<dir>, dir=. for the global one), to pass on as it is."""
    _print_text(_memory_call("curation-brief", {"dir": _name_values(args).get("dir", "")}))


@memory_app.command("curation-refute-brief")
def memory_curation_refute_brief(args: NameValues = None) -> None:
    """memory-curation's refuter brief for one dir (dir=<dir>), with the judge's JSON answer on stdin; pass it on as
    it is."""
    answer = _stdin_json()
    rows = answer.get("rows", []) if isinstance(answer, dict) else answer
    _print_text(_memory_call("curation-refute-brief", {"dir": _name_values(args).get("dir", ""), "rows": rows}))


@memory_app.command("fidelity")
def memory_fidelity(args: NameValues = None) -> None:
    """After a merge, split or trim: file=<memory> new=<memory,…> [rev=<commit>]; every old sentence and whether the
    new text keeps it word for word."""
    a = _name_values(args)
    body: dict[str, object] = {
        "file": a.get("file", ""),
        "rev": a.get("rev", "HEAD"),
        "new": [n for n in a.get("new", "").split(",") if n],
    }
    _print_text(_memory_call("fidelity", body))


def _object_from_stdin() -> dict[str, object]:
    value = _stdin_json()
    if not isinstance(value, dict):
        typer.echo("stdin must be one JSON object", err=True)
        raise typer.Exit(1)
    return value
