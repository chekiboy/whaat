"""The decisions page's own call: the user's answer, saved once into the page. The waiting session collects it
through the journal API with its identity's token; nothing is typed into a terminal."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from whaat.identities.registry import Principal
from whaat.journal.exceptions import (
    DecisionsAlreadySentError,
    DecisionsNotFoundError,
    InvalidAnswerError,
    InvalidStoredDocumentError,
)
from whaat.journal.schemas import DecisionsAnswerCall
from whaat.journal.service import JournalService
from whaat.security import require_admin

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])
AdminDep = Annotated[Principal, Depends(require_admin)]


class AnswerSaved(BaseModel):
    commit: str | None
    warnings: list[str]


def _journal(request: Request) -> JournalService:
    journal: JournalService = request.app.state.journal_service
    return journal


JournalDep = Annotated[JournalService, Depends(_journal)]


@router.post("/answer", response_model=AnswerSaved)
def answer(body: DecisionsAnswerCall, _: AdminDep, journal: JournalDep) -> AnswerSaved:
    """Save the user's choice and note per row and stamp the page as sent; a page is answered once."""
    try:
        commit, warnings = journal.answer_decisions(body.report_id, body.rows)
    except DecisionsNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except DecisionsAlreadySentError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    except InvalidAnswerError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
    except InvalidStoredDocumentError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    return AnswerSaved(commit=commit, warnings=warnings)
