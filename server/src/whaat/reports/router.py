from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from whaat.reports.exceptions import ReportNotFoundError
from whaat.reports.schemas import ReportDetail, ReportSummary
from whaat.reports.service import ReportService
from whaat.reports.store import FileReportStore
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


@router.get("/{report_id:path}", response_model=ReportDetail)
def get_report(report_id: str, service: ReportServiceDep) -> ReportDetail:
    try:
        return service.get_report(report_id)
    except ReportNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
