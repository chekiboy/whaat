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


class UndecidedRowsError(ValueError):
    def __init__(self, numbers: list[int]) -> None:
        super().__init__(
            f"rows {', '.join(map(str, numbers))} are not decided as apply on the report page: nothing is applied there"
        )
        self.numbers = numbers


class DecisionsNotFoundError(LookupError):
    def __init__(self, report_id: str) -> None:
        super().__init__(f"no decisions page {report_id!r} in an identity's private folder")
        self.report_id = report_id


class DecisionsAlreadySentError(Exception):
    def __init__(self, report_id: str, at: str) -> None:
        super().__init__(f"{report_id} was answered at {at}; an answer is sent once")
        self.report_id = report_id


class InvalidAnswerError(ValueError):
    pass


class InvalidStoredDocumentError(Exception):
    def __init__(self, report_id: str, reason: str) -> None:
        super().__init__(f"{report_id} is not a valid document ({reason}), so it is left as it is")
        self.report_id = report_id
