"""A decisions page: questions an agent session puts to the user, each with its options and a recommended one. The
user answers on the page; the waiting session reads the answer. The agent writes the questions only: the choice,
the note and the stamps are written by whaat."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from whaat.reports.types.base import Strict
from whaat.reports.types.journal import BODY_VERSION

Text = Annotated[str, StringConstraints(min_length=1)]
OptionValue = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")]


class DecisionsOption(Strict):
    value: OptionValue = Field(description="What the session reads back when this option is chosen, e.g. `apply`.")
    label: Text = Field(description="The option as the user reads it.")
    recommended: bool = Field(default=False, description="The option the agent recommends; at most one per row.")
    why: str | None = Field(default=None, description="A word on why it is recommended, e.g. `KISS`; optional.")


class DecisionRowIn(Strict):
    n: int = Field(ge=1, description="The row's number; the answer names rows by it.")
    title: Text
    explain: Text = Field(description="What the user needs to decide well, as markdown: what, why, the cost.")
    options: list[DecisionsOption] = Field(min_length=2)

    @field_validator("options")
    @classmethod
    def _options_are_distinct(cls, options: list[DecisionsOption]) -> list[DecisionsOption]:
        values = [option.value for option in options]
        if len(values) != len(set(values)):
            raise ValueError("option values must be unique within a row")
        if sum(option.recommended for option in options) > 1:
            raise ValueError("at most one option of a row is recommended")
        return options


class DecisionRow(DecisionRowIn):
    choice: str | None = Field(default=None, description="Set by whaat: the chosen option's value.")
    note: str | None = Field(default=None, description="Set by whaat: the user's note on the row.")


class DecisionsBodyIn(Strict):
    title: Text = Field(description="What the page decides, e.g. `ABC-101 · phase 3 gate`.")
    asked_by: str | None = Field(default=None, description="The step that asks, e.g. `implement-task · phase 3`.")
    summary: Text = Field(description="What the user should know before deciding, as markdown (tables allowed).")
    rows: list[DecisionRowIn] = Field(min_length=1)

    @field_validator("rows")
    @classmethod
    def _numbers_are_unique(cls, rows: list[DecisionRowIn]) -> list[DecisionRowIn]:
        numbers = [row.n for row in rows]
        if len(numbers) != len(set(numbers)):
            raise ValueError("row numbers must be unique")
        return rows


class DecisionsBody(DecisionsBodyIn):
    v: int = BODY_VERSION
    rows: list[DecisionRow] = Field(min_length=1)  # type: ignore[assignment]
    sent_at: str | None = Field(default=None, description="Set by whaat: when the user sent the answer.")


class DecisionsContent(Strict):
    format: Literal["decisions"] = "decisions"
    report: DecisionsBody
