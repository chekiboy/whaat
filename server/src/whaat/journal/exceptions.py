class UnknownIdentityError(Exception):
    def __init__(self, identity: str) -> None:
        super().__init__(f"no identity {identity!r} with a private folder")
        self.identity = identity


class CurationReportNotFoundError(LookupError):
    def __init__(self, report_id: str) -> None:
        super().__init__(f"no curation report {report_id!r} in an identity's private folder")
        self.report_id = report_id


class UnknownRowsError(ValueError):
    def __init__(self, numbers: list[int]) -> None:
        super().__init__(f"the report has no rows {', '.join(map(str, numbers))}")
        self.numbers = numbers


class InvalidStoredDocumentError(Exception):
    def __init__(self, report_id: str, reason: str) -> None:
        super().__init__(f"{report_id} is not a valid document ({reason}), so it is left as it is")
        self.report_id = report_id
