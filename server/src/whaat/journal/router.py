from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from whaat.curation import guards
from whaat.identities.registry import IdentityRegistry
from whaat.journal.exceptions import (
    CurationReportNotFoundError,
    InvalidStoredDocumentError,
    UnknownIdentityError,
    UnknownRowsError,
)
from whaat.journal.schemas import (
    CurationAppliedCall,
    CurationReport,
    CurationRowsSaved,
    JournalEntry,
    SavedCurationReport,
    SavedJournalEntry,
    SavedSessionReport,
    SessionReport,
)
from whaat.journal.service import JournalService
from whaat.memory.service import MEMORY_DIR
from whaat.security import require_identity

router = APIRouter(prefix="/api/v1/journal", tags=["journal"])


def get_journal_service(request: Request) -> JournalService:
    service: JournalService = request.app.state.journal_service
    return service


JournalServiceDep = Annotated[JournalService, Depends(get_journal_service)]
IdentityDep = Annotated[str, Depends(require_identity)]


@router.post("/entries", response_model=SavedJournalEntry, status_code=status.HTTP_201_CREATED)
def save_journal_entry(entry: JournalEntry, service: JournalServiceDep, identity: IdentityDep) -> SavedJournalEntry:
    try:
        return service.save_entry(entry, identity)
    except UnknownIdentityError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    except InvalidStoredDocumentError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err


@router.post("/session-reports", response_model=SavedSessionReport, status_code=status.HTTP_201_CREATED)
def save_session_report(report: SessionReport, service: JournalServiceDep, identity: IdentityDep) -> SavedSessionReport:
    try:
        return service.save_session_report(report, identity)
    except UnknownIdentityError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    except InvalidStoredDocumentError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err


@router.post("/curation-reports", response_model=SavedCurationReport, status_code=status.HTTP_201_CREATED)
def save_curation_report(
    request: Request, report: CurationReport, service: JournalServiceDep, identity: IdentityDep
) -> SavedCurationReport:
    """memory-curation's report: one per day in the identity's private folder; a later save that day replaces it. A
    row without what its actions require (a target, evidence, an existing memory) is refused, each named."""
    registry: IdentityRegistry = request.app.state.registry
    if identity in registry.folders():
        refused = guards.problems(str(registry.folder_of(identity) / MEMORY_DIR), report.report.rows)
        if refused:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=refused)
    try:
        return service.save_curation_report(report, identity)
    except UnknownIdentityError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    except InvalidStoredDocumentError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err


@router.post("/curation-reports/applied", response_model=CurationRowsSaved)
def save_curation_applied(
    call: CurationAppliedCall, service: JournalServiceDep, identity: IdentityDep
) -> CurationRowsSaved:
    """apply-rows' Applied cells on the identity's own curation report; the rest of the report stays as it is."""
    try:
        _, commit, warnings = service.save_curation_applied(call.report_id, identity, call.rows)
    except CurationReportNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except UnknownRowsError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    except InvalidStoredDocumentError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    return CurationRowsSaved(commit=commit, warnings=warnings)
