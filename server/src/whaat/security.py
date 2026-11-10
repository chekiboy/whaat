import secrets
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from whaat.identities.registry import IdentityRegistry, Principal

TOKEN_FILE_NAME = "token"

bearer = HTTPBearer(auto_error=False)


def token_file(state_dir: Path) -> Path:
    return state_dir / TOKEN_FILE_NAME


def load_or_create_token(state_dir: Path) -> str:
    path = token_file(state_dir)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    state_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    path.chmod(0o600)
    return token


def require_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    """The token names the caller: the admin, or the identity it was given to."""
    registry: IdentityRegistry = request.app.state.registry
    principal = registry.principal_for(credentials.credentials) if credentials else None
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing or wrong token")
    return principal


PrincipalDep = Annotated[Principal, Depends(require_principal)]


def require_admin(principal: PrincipalDep) -> Principal:
    if not principal.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="this needs the admin token")
    return principal


def require_identity(principal: PrincipalDep) -> str:
    """An identity's own token; the admin token names no identity, so it cannot write in anyone's name."""
    if principal.identity is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="the admin token names no identity; use the identity's token"
        )
    return principal.identity
