import subprocess
from functools import cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from whaat import __version__
from whaat.identities.registry import Principal
from whaat.security import require_admin

REPO_ROOT = Path(__file__).resolve().parents[4]

router = APIRouter(prefix="/api/v1/health", tags=["health"])


class Health(BaseModel):
    status: str
    app: str
    version: str
    commit: str | None = Field(
        description='The short hash of the code this server runs, "+dirty" when it has uncommitted changes;'
        " null outside a git checkout."
    )
    instance: str
    started: int = Field(description="When this server process started, in Unix seconds; a restart changes it.")


def _git(*args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


@cache
def code_commit() -> str | None:
    """Read once, when the server first answers, so it names the code the running process loaded."""
    commit = _git("rev-parse", "--short", "HEAD")
    if commit and _git("status", "--porcelain", "--untracked-files=no"):
        return f"{commit}+dirty"
    return commit


@router.get("", response_model=Health)
def get_health(request: Request) -> Health:
    return Health(
        status="ok",
        app="whaat",
        version=__version__,
        commit=code_commit(),
        instance=request.app.state.settings.instance,
        started=request.app.state.started,
    )


class Restart(BaseModel):
    ui_built: bool = Field(
        description="Whether `pnpm build` rebuilt the checkout's UI first; false for a `WHAAT_UI_DIR`."
    )


@router.post(
    "/restart",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Restart,
    responses={409: {"description": "The UI build failed; the server keeps running, and the detail ends its output."}},
)
def restart_server(request: Request, _: Annotated[Principal, Depends(require_admin)]) -> Restart:
    """Build the checkout's UI, then restart the server with the code on disk a moment after this answer; the UI waits
    for a new `started`. A failed build leaves the running server as it is."""
    build = request.app.state.build_ui()
    if build.error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=build.error)
    request.app.state.restart()
    return Restart(ui_built=build.built)


@router.post("/stop", status_code=status.HTTP_202_ACCEPTED)
def stop_server(request: Request, _: Annotated[Principal, Depends(require_admin)]) -> None:
    """Stop the server a moment after this answer, as Ctrl-C would; it starts again only from outside (the app or
    `whaat serve`). Terminal sessions keep running in tmux."""
    request.app.state.stop()
