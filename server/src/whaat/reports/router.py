import subprocess
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from whaat.reports.exceptions import ReportNotFoundError
from whaat.reports.schemas import ReportDetail, ReportOpened, ReportSummary
from whaat.reports.service import ReportService
from whaat.reports.store import FileReportStore, report_key
from whaat.security import PrincipalDep

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def get_report_service(request: Request, principal: PrincipalDep) -> ReportService:
    """The reports this caller may see: the admin all of them, an identity only its own folder."""
    return ReportService(FileReportStore(request.app.state.registry.roots_for(principal)))


ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]


@router.get("", response_model=list[ReportSummary])
def list_reports(
    service: ReportServiceDep,
    kind: str | None = None,
    identity: str | None = None,
    tag: str | None = None,
    session: str | None = None,
) -> list[ReportSummary]:
    return service.list_reports(kind, identity, tag, session)


@router.get("/by-key/{key}", response_model=ReportDetail)
def get_report_by_key(key: str, service: ReportServiceDep) -> ReportDetail:
    try:
        return service.get_report_by_key(key)
    except ReportNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err


@router.post("/{report_id:path}/open", response_model=ReportOpened)
def open_report(report_id: str, request: Request, service: ReportServiceDep) -> ReportOpened:
    """Open one of the caller's reports in the UI, in this machine's browser; the address comes back either way."""
    try:
        service.get_report(report_id)
    except ReportNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    settings = request.app.state.settings
    url = f"{settings.public_url}/ui/reports/{report_key(report_id)}"
    try:
        request.app.state.open_url(url, settings.browser)
    except (OSError, subprocess.CalledProcessError) as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"could not open {url}: {err}") from err
    return ReportOpened(url=url)


@router.get("/{report_id:path}", response_model=ReportDetail)
def get_report(report_id: str, service: ReportServiceDep) -> ReportDetail:
    try:
        return service.get_report(report_id)
    except ReportNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
