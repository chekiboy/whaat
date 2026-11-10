from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from whaat.identities.registry import (
    IdentityExistsError,
    IdentityRegistry,
    InvalidIdentityError,
    Principal,
    UnknownTokenError,
)
from whaat.identities.schemas import CreatedIdentity, IdentitySummary, NewIdentity
from whaat.identities.service import IdentityService
from whaat.security import PrincipalDep, require_admin

router = APIRouter(prefix="/api/v1/identities", tags=["identities"])


def get_identity_service(request: Request) -> IdentityService:
    return IdentityService(request.app.state.settings, request.app.state.registry)


@router.get("", response_model=list[IdentitySummary])
def list_identities(
    service: Annotated[IdentityService, Depends(get_identity_service)], principal: PrincipalDep
) -> list[IdentitySummary]:
    """Every identity for the admin; an identity sees only itself."""
    return service.list_identities(principal)


@router.post("", response_model=CreatedIdentity, status_code=status.HTTP_201_CREATED)
def create_identity(
    new: NewIdentity, request: Request, _admin: Annotated[Principal, Depends(require_admin)]
) -> CreatedIdentity:
    """Give an identity its own folder and token; only the admin can. The answer is the only place the UI shows the
    token."""
    registry: IdentityRegistry = request.app.state.registry
    try:
        token, warnings = registry.add(new.id)
    except InvalidIdentityError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    except IdentityExistsError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    return CreatedIdentity(id=new.id, token=token, folder=str(registry.folder_of(new.id)), warnings=warnings)


@router.post(
    "/{identity}/token", response_model=CreatedIdentity, responses={404: {"description": "No token to replace."}}
)
def regenerate_token(
    identity: str, request: Request, _admin: Annotated[Principal, Depends(require_admin)]
) -> CreatedIdentity:
    """Replace an identity's token; only the admin can. The old token stops working at once, and the answer is the
    only place the UI shows the new one."""
    registry: IdentityRegistry = request.app.state.registry
    try:
        token = registry.regenerate(identity)
    except UnknownTokenError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    return CreatedIdentity(id=identity, token=token, folder=str(registry.folder_of(identity)))
