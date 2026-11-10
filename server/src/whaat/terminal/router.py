"""The terminal module: tmux sessions per persona, and a WebSocket that puts one of them into the browser's terminal.

This runs commands on the user's machine, so every call needs the admin token (an identity's token is an agent's), and
the WebSocket also checks that the page opening it is whaat's own: a browser lets any page open a WebSocket to
127.0.0.1, so binding to localhost alone would not stop another site in the same browser."""

import asyncio
import contextlib
import fcntl
import json
import os
import pty
import signal
import struct
import subprocess
import termios
from dataclasses import asdict
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status

from whaat.identities.registry import IdentityRegistry, Principal
from whaat.preferences.store import PreferencesStore
from whaat.security import require_admin
from whaat.terminal.agent import AgentTokenMissingError
from whaat.terminal.native import NativeOpenError, installed
from whaat.terminal.projects import FolderError, folder, subfolders
from whaat.terminal.schemas import (
    Folder,
    Folders,
    NewTerminal,
    OpenNative,
    Project,
    Projects,
    RenameTerminal,
    TerminalApps,
    TerminalSession,
    TerminalSessions,
    TerminalTheme,
    TerminalThemes,
)
from whaat.terminal.service import Terminals
from whaat.terminal.themes import machine_themes
from whaat.terminal.tmux import Session, SessionNotFoundError, Tmux, TmuxMissingError

router = APIRouter(prefix="/api/v1/terminal", tags=["terminal"])
AdminDep = Annotated[Principal, Depends(require_admin)]
PROTOCOL = "whaat"
CLOSE_REFUSED = 4401
CLOSE_GONE = 4404


def _session(session: Session, state: tuple[bool, bool, bool] = (False, False, False)) -> TerminalSession:
    busy, asking, done = state
    return TerminalSession(**asdict(session), idle=session.idle, asking=asking, busy=busy, done=done)


def _terminals(request: Request) -> Terminals:
    terminals: Terminals = request.app.state.terminals
    return terminals


TerminalsDep = Annotated[Terminals, Depends(_terminals)]


def _known_persona(request: Request, persona: str) -> None:
    registry: IdentityRegistry = request.app.state.registry
    if persona not in registry.folders():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no identity {persona!r}")


@router.get("/sessions")
def list_terminals(_: AdminDep, terminals: TerminalsDep, persona: str | None = None) -> TerminalSessions:
    """The running terminal sessions, of one persona or of all."""
    try:
        sessions = terminals.sessions(persona)
    except TmuxMissingError as err:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(err)) from err
    tmux = terminals.tmux
    listed = [_session(s, terminals.state(s.name) if not s.gone else (False, False, False)) for s in sessions]
    return TerminalSessions(command=tmux.command, cwd=str(tmux.cwd), sessions=listed)


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def open_terminal(body: NewTerminal, request: Request, _: AdminDep, terminals: TerminalsDep) -> TerminalSession:
    """Start a new session for a persona: the start command in the user's login shell, in its own tmux session."""
    _known_persona(request, body.persona)
    try:
        cwd = folder(body.cwd) if body.cwd else None
    except FolderError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    try:
        session = terminals.create(body.persona, cwd)
    except TmuxMissingError as err:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(err)) from err
    except AgentTokenMissingError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    if cwd:
        _projects(request).project_used(cwd)
    return _session(session)


def _projects(request: Request) -> PreferencesStore:
    store: PreferencesStore = request.app.state.preferences
    return store


@router.get("/apps")
def list_terminal_apps(_: AdminDep) -> TerminalApps:
    """The terminal apps of this machine a session can open in, besides the browser."""
    return TerminalApps(installed=list(installed()))


@router.post("/sessions/{name}/open", status_code=status.HTTP_204_NO_CONTENT)
def open_natively(name: str, body: OpenNative, request: Request, _: AdminDep) -> None:
    """Open a running session in a terminal app of this machine, attached to the same tmux session."""
    tmux: Tmux = request.app.state.tmux
    app = body.app or request.app.state.preferences.load()["terminal"]["opener"]
    if app not in ("terminal-app", "iterm2"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{app!r} is not a terminal app")
    try:
        request.app.state.native_open(app, tmux.attach_argv(name))
    except SessionNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no session {name!r}") from err
    except NativeOpenError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err


@router.get("/themes")
def list_themes(_: AdminDep) -> TerminalThemes:
    """The terminal themes this machine has (macOS Terminal's and iTerm2's profiles), read when asked."""
    return TerminalThemes(themes=[TerminalTheme(**theme) for theme in machine_themes()])


@router.get("/folders")
def browse_folders(_: AdminDep, path: str = "~", hidden: bool = False) -> Folders:
    """The folders under a folder, for picking the project a session starts in."""
    try:
        here = folder(path)
        found = subfolders(here, hidden)
    except FolderError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    return Folders(
        path=str(here),
        parent=str(here.parent) if here.parent != here else None,
        folders=[Folder(name=name, repo=repo) for name, repo in found],
    )


@router.get("/projects")
def list_projects(request: Request, _: AdminDep) -> Projects:
    """The project folders sessions were started in, the one used last first."""
    return Projects(
        projects=[
            Project(path=str(p["path"]), used=int(str(p.get("used", 0))), exists=Path(str(p["path"])).is_dir())
            for p in _projects(request).projects()
        ]
    )


@router.delete("/projects", status_code=status.HTTP_204_NO_CONTENT)
def forget_project(request: Request, _: AdminDep, path: str) -> None:
    """Take a project off the saved list; the folder itself stays."""
    if not _projects(request).forget_project(path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no saved project {path!r}")


@router.patch("/sessions/{name}")
def rename_terminal(name: str, body: RenameTerminal, _: AdminDep, terminals: TerminalsDep) -> TerminalSession:
    """Name a session, so the list shows what runs in it."""
    try:
        return _session(terminals.rename(name, body.label))
    except SessionNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no session {name!r}") from err


@router.delete("/sessions/{name}", status_code=status.HTTP_204_NO_CONTENT)
def close_terminal(name: str, _: AdminDep, terminals: TerminalsDep) -> None:
    """Stop a session and what runs in it, and forget it; a gone one is only forgotten. Closing its window does not
    do this."""
    try:
        terminals.stop(name)
    except SessionNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no session {name!r}") from err


def _same_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host")
    return bool(origin and host and urlsplit(origin).netloc == host)


def _admin_token(websocket: WebSocket) -> bool:
    """The token comes as the second WebSocket subprotocol (a browser cannot set an Authorization header on one)."""
    offered = websocket.scope.get("subprotocols", [])
    if len(offered) != 2 or offered[0] != PROTOCOL:
        return False
    registry: IdentityRegistry = websocket.app.state.registry
    principal = registry.principal_for(offered[1])
    return principal is not None and principal.admin


def _resize(fd: int, cols: int, rows: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", max(rows, 2), max(cols, 2), 0, 0))


def _controlling_tty() -> None:
    os.setsid()
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


@router.websocket("/sessions/{name}/attach")
async def attach_terminal(websocket: WebSocket, name: str) -> None:
    """Binary frames carry the keys in and the screen out; a text frame `{"cols": n, "rows": n}` resizes. Closing the
    socket detaches: the session keeps running in tmux."""
    if not _same_origin(websocket) or not _admin_token(websocket):
        await websocket.close(code=CLOSE_REFUSED)
        return
    tmux: Tmux = websocket.app.state.tmux
    try:
        argv = tmux.attach_argv(name)
    except (SessionNotFoundError, TmuxMissingError):
        await websocket.close(code=CLOSE_GONE)
        return
    await websocket.accept(subprotocol=PROTOCOL)
    master, slave = pty.openpty()
    _resize(master, 120, 32)
    proc = subprocess.Popen(
        argv,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=tmux.env,
        preexec_fn=_controlling_tty,
        close_fds=True,
    )
    os.close(slave)
    loop = asyncio.get_running_loop()
    output: asyncio.Queue[bytes] = asyncio.Queue()

    def readable() -> None:
        try:
            data = os.read(master, 65536)
        except OSError:
            data = b""
        output.put_nowait(data)
        if not data:
            loop.remove_reader(master)

    loop.add_reader(master, readable)

    async def pump_out() -> None:
        while data := await output.get():
            await websocket.send_bytes(data)
        await websocket.close()

    async def pump_in() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes"):
                os.write(master, message["bytes"])
            elif message.get("text"):
                size = json.loads(message["text"])
                _resize(master, int(size["cols"]), int(size["rows"]))
                proc.send_signal(signal.SIGWINCH)

    sender = asyncio.create_task(pump_out())
    try:
        await pump_in()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        sender.cancel()
        loop.remove_reader(master)
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()  # only the attach client: the session stays in tmux
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=2)
        os.close(master)
