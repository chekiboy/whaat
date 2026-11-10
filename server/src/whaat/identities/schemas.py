from pydantic import BaseModel, Field

from whaat.reports.types.base import Strict


class IdentitySummary(BaseModel):
    id: str
    default: bool
    has_private_folder: bool
    has_token: bool
    report_count: int
    private_report_count: int


class NewIdentity(Strict):
    id: str = Field(
        description="The identity's id: letters, digits and dashes, starting with a letter; two ids may not differ only"
        " in case."
    )


class CreatedIdentity(BaseModel):
    id: str
    token: str = Field(
        description="The identity's token. whaat checks requests against its hash and keeps the token itself in the"
        " state folder (owner-only), so it can later write it into the identity's agent config."
    )
    folder: str
    warnings: list[str] = Field(default_factory=list)
