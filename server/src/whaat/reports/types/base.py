from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, PlainSerializer, WithJsonSchema


def _atom(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


AtomDatetime = Annotated[
    AwareDatetime,
    PlainSerializer(_atom, return_type=str),
    WithJsonSchema({"type": "string", "format": "date-time"}),
]


class Strict(BaseModel):
    """A field the skill does not ask for is refused, so nothing is invented or misspelled silently."""

    model_config = ConfigDict(extra="forbid")
