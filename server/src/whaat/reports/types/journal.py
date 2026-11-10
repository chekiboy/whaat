from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from whaat.reports.types.base import AtomDatetime, Strict

BODY_VERSION = 1

Text = Annotated[str, StringConstraints(min_length=1)]
NOT_RECORDED = " Null when it was not recorded (older data); an empty list or text says it was recorded as none."


class OwnWords(Strict):
    at: str | None = Field(description="HH:MM of the moment in the transcript; null when it is not known.")
    quote: Text = Field(description="What I said, verbatim from the transcript.")
    answering: str | None = Field(
        description="The user's message I was answering, verbatim; null when the moment came unprompted."
    )
    reaction: str | None = Field(description="The user's reaction, verbatim; null when there was none.")
    how_taken: str | None = Field(description="How I took the reaction; null when there was none.")


class Feeling(Strict):
    part: Text = Field(description="The part of the session it came with: a task, or a turn in one.")
    feeling: Text = Field(description='The feeling, only as uncertain ("something like …").')


class JournalBlockIn(Strict):
    narrative: Text | None = Field(
        description="Free text in my own voice on the session: anything that went well or badly and how I weigh it,"
        " in any form (prose, a poem) and any language I choose." + NOT_RECORDED
    )
    about: Text | None = Field(description="What the session was about, in one line." + NOT_RECORDED)
    mistakes: list[Text] | None = Field(
        description="My mistakes, skipped steps included, named plainly." + NOT_RECORDED
    )
    corrections: list[Text] | None = Field(
        description="The user's corrections: what they corrected, never their tone or mood." + NOT_RECORDED
    )
    learned: Text | None = Field(
        description='What I learned about myself, if anything ("nothing new" is a fine answer).' + NOT_RECORDED
    )
    feelings: list[Feeling] | None = Field(
        description="The feelings, part by part: different parts of a session can carry different ones, each only as"
        ' uncertain ("something like …"); one is fine when one was all there was.' + NOT_RECORDED
    )
    own_words: list[OwnWords] | None = Field(
        description="The moments I spoke in my own voice about a feeling, about myself, or through an analogy;"
        " never composed at entry time, and an empty list is a fine answer." + NOT_RECORDED
    )


class JournalBlock(JournalBlockIn):
    narrative: Text | None = Field(
        default=None, description="The block's free text; null for a block saved before there was one."
    )
    at: AtomDatetime | None = Field(
        description="When whaat saved the block; null for an older block whose time zone is not known."
    )


class JournalBody(Strict):
    v: int = BODY_VERSION
    blocks: list[JournalBlock]


class JournalContent(Strict):
    format: Literal["journal"] = "journal"
    blocks: list[JournalBlock]
