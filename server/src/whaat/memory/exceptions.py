class InvalidMemoryPathError(ValueError):
    def __init__(self, path: str) -> None:
        super().__init__(f"{path!r} is not a memory path below this identity's memory root")


class MemoryNotFoundError(LookupError):
    def __init__(self, path: str) -> None:
        super().__init__(f"no memory {path!r}")
