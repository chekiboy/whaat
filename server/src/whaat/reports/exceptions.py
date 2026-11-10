class ReportNotFoundError(Exception):
    def __init__(self, report_id: str) -> None:
        super().__init__(f"no report with id {report_id!r}")
        self.report_id = report_id
