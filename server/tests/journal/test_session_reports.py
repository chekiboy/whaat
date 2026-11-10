import copy
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import CLAUDE_TOKEN, TOKEN
from tests.journal.samples import BLOCK, REPORT
from tests.journal.test_api import git, isolated_git  # noqa: F401
from whaat.config import Settings
from whaat.git import GitCommitter
from whaat.journal.schemas import SessionReport
from whaat.journal.service import JournalService
from whaat.journal.store import FileJournalStore
from whaat.reports.store import roots_from

AUTH = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
ADMIN = {"Authorization": f"Bearer {TOKEN}"}
FIRST = "session-reports/2026/10/2026-10-29_session-report_c08cba1f_whaat-journal.json"


def save(client: TestClient, **report: object) -> dict[str, object]:
    response = client.post("/api/v1/journal/session-reports", json=report, headers=AUTH)
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def stored(settings: Settings, rel: str = FIRST) -> Any:
    data: Any = json.loads((settings.identities["claude"] / rel).read_text(encoding="utf-8"))
    return data


def test_the_report_is_stored_as_sent_and_comes_back_typed(client: TestClient, settings: Settings) -> None:
    saved = save(
        client, session="c08cba1f", slug="whaat-journal", entry_date="2026-10-29", report=REPORT, tags=["whaat"]
    )

    body = stored(settings)["body"]
    detail = client.get(f"/api/v1/reports/{saved['report_id']}", headers=AUTH).json()

    assert {key: value for key, value in body.items() if key != "v"} == REPORT
    assert detail["body"]["format"] == "session-report"
    assert {key: value for key, value in detail["body"]["report"].items() if key != "v"} == REPORT
    assert stored(settings)["envelope"]["title"] == REPORT["topic"]


def test_a_later_save_in_another_month_replaces_the_first_file(client: TestClient, settings: Settings) -> None:
    final = {**REPORT, "topic": "Design patterns and the whaat journal, final"}
    first = save(
        client, session="c08cba1f", slug="whaat-journal", entry_date="2026-10-29", report=REPORT, tags=["whaat"]
    )
    second = save(client, session="c08cba1f", slug="other", entry_date="2026-11-02", report=final, tags=["reports"])

    files = sorted(
        p.relative_to(settings.identities["claude"]).as_posix()
        for p in (settings.identities["claude"] / "session-reports").rglob("*c08cba1f*")
    )
    assert files == [FIRST]
    assert stored(settings)["body"]["topic"] == final["topic"]
    assert stored(settings)["envelope"]["tags"] == ["whaat", "reports"]
    assert stored(settings)["envelope"]["created_date"] == "2026-10-29"
    assert (first["replaced"], second["replaced"]) == (False, True)


def test_created_at_stays_the_first_save(settings: Settings) -> None:
    times = iter(
        [datetime(2026, 10, 29, 14, 5, tzinfo=timezone(timedelta(hours=1))), datetime(2026, 10, 29, 15, 0, tzinfo=UTC)]
    )
    service = JournalService(FileJournalStore(), lambda _: roots_from(settings), GitCommitter(), lambda: next(times))
    payload = {"session": "c08cba1f", "slug": "whaat-journal", "report": REPORT}

    service.save_session_report(SessionReport.model_validate(payload), "claude")
    service.save_session_report(SessionReport.model_validate(payload), "claude")

    assert stored(settings)["envelope"]["created_at"] == "2026-10-29T14:05:00+01:00"


def test_a_git_folder_gets_a_commit_of_the_report(
    client: TestClient,
    settings: Settings,
    isolated_git: None,  # noqa: F811
) -> None:
    folder: Path = settings.identities["claude"]
    git(folder, "init", "--quiet")

    saved = save(client, session="c08cba1f", slug="whaat-journal", entry_date="2026-10-29", report=REPORT)

    assert git(folder, "log", "-1", "--format=%s") == "journal: session c08cba1f report\n"
    assert saved["commit"] == git(folder, "rev-parse", "HEAD").strip()
    assert git(folder, "show", "--name-only", "--format=", "HEAD").split() == [FIRST]


def test_the_report_holds_no_copy_of_the_journal(client: TestClient) -> None:
    response = client.post(
        "/api/v1/journal/session-reports",
        json={"session": "c08cba1f", "slug": "x", "report": {**REPORT, "journal": [BLOCK]}},
        headers=AUTH,
    )
    assert response.status_code == 422


def test_an_invalid_report_is_refused(client: TestClient) -> None:
    missing = copy.deepcopy(REPORT)
    del missing["drift"]
    outcome: Any = REPORT["outcome"]
    bad_status = {**REPORT, "outcome": {**outcome, "status": "almost"}}
    for report, slug in ((missing, "x"), (bad_status, "x"), (REPORT, "Whaat_X")):
        response = client.post(
            "/api/v1/journal/session-reports",
            json={"session": "c08cba1f", "slug": slug, "report": report},
            headers=AUTH,
        )
        assert response.status_code == 422
