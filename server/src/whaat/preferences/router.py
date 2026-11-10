from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from whaat.identities.registry import Principal
from whaat.preferences.schemas import Preferences, PreferencesPatch
from whaat.preferences.store import PreferencesStore
from whaat.security import require_admin

router = APIRouter(prefix="/api/v1/preferences", tags=["preferences"])
AdminDep = Annotated[Principal, Depends(require_admin)]


def _store(request: Request) -> PreferencesStore:
    store: PreferencesStore = request.app.state.preferences
    return store


StoreDep = Annotated[PreferencesStore, Depends(_store)]


@router.get("")
def get_preferences(_: AdminDep, store: StoreDep) -> Preferences:
    """What the UI remembers: the language, the identity it opens with and the one used last, and the terminal's default
    command, theme and saved folders."""
    return Preferences.model_validate(store.load())


@router.patch("")
def update_preferences(body: PreferencesPatch, _: AdminDep, store: StoreDep) -> Preferences:
    """Change what is given and keep the rest; an empty command goes back to the default."""
    terminal = body.terminal
    identity = body.identity
    agents = {
        who: str(Path(folder).expanduser()) if folder else ""
        for who, folder in ((identity and identity.agents) or {}).items()
    }
    for who, folder in agents.items():
        if folder and not Path(folder).is_dir():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"no folder {folder!r} for {who}'s agent config",
            )
    store.update(
        language=body.language,
        open_with=identity.open_with if identity else None,
        last_identity=identity.last if identity else None,
        agents=agents or None,
        command=terminal.command if terminal else None,
        theme=terminal.theme if terminal else None,
        opener=terminal.opener if terminal else None,
    )
    return Preferences.model_validate(store.load())
