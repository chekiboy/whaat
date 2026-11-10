from collections import Counter

from whaat.config import Settings
from whaat.identities.registry import IdentityRegistry, Principal
from whaat.identities.schemas import IdentitySummary
from whaat.reports.service import ReportService
from whaat.reports.store import FileReportStore


class IdentityService:
    def __init__(self, settings: Settings, registry: IdentityRegistry) -> None:
        self._settings = settings
        self._registry = registry

    def list_identities(self, principal: Principal) -> list[IdentitySummary]:
        reports = ReportService(FileReportStore(self._registry.roots_for(principal)))
        summaries = reports.list_reports()
        totals = Counter(summary.envelope.identity for summary in summaries)
        private = Counter(summary.envelope.identity for summary in summaries if summary.private)
        folders = self._registry.folders()
        known = (
            {self._settings.default_identity, *folders, *(i for i in totals if i)}
            if principal.admin
            else {principal.identity}
        )
        return [
            IdentitySummary(
                id=identity,
                default=identity == self._settings.default_identity,
                has_private_folder=identity in folders,
                has_token=self._registry.has_token(identity),
                report_count=totals[identity],
                private_report_count=private[identity],
            )
            for identity in sorted(i for i in known if i)
        ]
