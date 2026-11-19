import hashlib
import json
import re
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from tests.conftest import CLAUDE_TOKEN, TOKEN, write
from whaat.cli import main as cli
from whaat.config import Settings
from whaat.reports.types.decisions import DecisionsBodyIn

AUTH = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
ADMIN = {"Authorization": f"Bearer {TOKEN}"}
FILE = "decisions/2026/11/2026-11-19_0a1b2c3d_phase-3-gate.json"
ROWS = [
    {
        "n": 1,
        "title": "Review outcome",
        "explain": "Accept and go on to phase 4.",
        "options": [
            {"value": "accept", "label": "Accept", "recommended": True},
            {"value": "not-yet", "label": "Not yet"},
        ],
    },
    {
        "n": 2,
        "title": "Drop the redundant check",
        "explain": "One line fewer; behaviour identical.",
        "options": [
            {"value": "apply", "label": "Apply it", "recommended": True, "why": "KISS"},
            {"value": "skip", "label": "Skip it"},
        ],
    },
    {
        "n": 3,
        "title": "Memory candidates",
        "explain": "Two candidates, both already covered.",
        "options": [{"value": "none", "label": "Save none"}, {"value": "one", "label": "Save one"}],
    },
]
PAGE = {"title": "ABC-101 · phase 3 gate", "asked_by": "implement-task", "summary": "No P1 / P2.", "rows": ROWS}


def save(client: TestClient, page: dict[str, Any] = PAGE) -> Any:
    body = {"session": "0a1b2c3d", "slug": "phase-3-gate", "ticket": "ABC-101", "entry_date": "2026-11-19"}
    return client.post("/api/v1/journal/decisions", json={**body, "report": page}, headers=AUTH)


def answer(client: TestClient, report_id: str, rows: list[dict[str, Any]]) -> Any:
    return client.post(f"/api/v1/reports/{report_id}/answer", json={"rows": rows}, headers=ADMIN)


def collect(client: TestClient, report_id: str, headers: dict[str, str] = AUTH) -> Any:
    return client.post("/api/v1/journal/decisions/collect", json={"report_id": report_id}, headers=headers)


def test_the_page_is_stored_privately_with_the_session_and_comes_back_typed(
    client: TestClient, settings: Settings
) -> None:
    saved = save(client).json()

    stored = json.loads((settings.identities["claude"] / FILE).read_text(encoding="utf-8"))
    listed = client.get("/api/v1/reports", params={"session": "0a1b2c3d"}, headers=AUTH).json()
    detail = client.get(f"/api/v1/reports/{saved['report_id']}", headers=AUTH).json()

    assert stored["body"]["rows"][0]["choice"] is None
    assert [(r["envelope"]["kind"], r["envelope"]["ticket"], r["private"]) for r in listed] == [
        ("decisions", "ABC-101", True)
    ]
    assert detail["body"]["format"] == "decisions"
    assert detail["body"]["report"]["rows"][1]["options"][0]["why"] == "KISS"


def test_the_session_reads_nothing_until_the_user_answers_then_one_line_per_row(client: TestClient) -> None:
    report_id = save(client).json()["report_id"]
    before = collect(client, report_id).json()

    sent = answer(
        client,
        report_id,
        [{"n": 1, "choice": "accept"}, {"n": 2, "choice": "skip", "note": " only with S-2 "}],
    )
    after = collect(client, report_id).json()

    assert before == {"sent": False, "sent_at": None, "text": None}
    assert sent.status_code == 200
    assert after["sent"] is True
    assert after["text"].splitlines()[1:] == ["1. accept", "2. skip (not the recommended) — only with S-2", "3. —"]


def test_a_row_with_no_recommendation_is_never_marked_as_off_it(client: TestClient) -> None:
    report_id = save(client).json()["report_id"]
    answer(client, report_id, [{"n": 3, "choice": "one"}])

    assert collect(client, report_id).json()["text"].splitlines()[3] == "3. one"


def test_an_answer_is_sent_once_and_the_answered_page_cannot_be_replaced(client: TestClient) -> None:
    report_id = save(client).json()["report_id"]
    answer(client, report_id, [{"n": 1, "choice": "accept"}])

    assert answer(client, report_id, [{"n": 1, "choice": "not-yet"}]).status_code == 409
    assert save(client).status_code == 409


def test_an_answer_naming_an_unknown_row_or_option_is_refused_and_nothing_is_stamped(client: TestClient) -> None:
    report_id = save(client).json()["report_id"]

    assert answer(client, report_id, [{"n": 9, "choice": "accept"}]).status_code == 422
    assert answer(client, report_id, [{"n": 1, "choice": "maybe"}]).status_code == 422
    assert collect(client, report_id).json()["sent"] is False


def test_only_the_admin_answers_and_only_the_page_owner_collects(client: TestClient) -> None:
    report_id = save(client).json()["report_id"]

    by_agent = client.post(
        f"/api/v1/reports/{report_id}/answer", json={"rows": [{"n": 1, "choice": "accept"}]}, headers=AUTH
    )
    elsewhere = collect(client, report_id.replace("decisions/", "memory-curation/"))

    assert by_agent.status_code == 403
    assert elsewhere.status_code == 404


def test_a_page_whose_options_repeat_or_recommend_twice_is_refused(client: TestClient) -> None:
    twice = {**ROWS[0], "options": [{**o, "recommended": True} for o in ROWS[0]["options"]]}
    repeated = {**ROWS[0], "options": [ROWS[0]["options"][0], ROWS[0]["options"][0]]}

    assert save(client, {**PAGE, "rows": [twice]}).status_code == 422
    assert save(client, {**PAGE, "rows": [repeated]}).status_code == 422


def test_the_list_shows_a_page_as_waiting_until_it_is_answered(client: TestClient) -> None:
    report_id = save(client).json()["report_id"]
    before = client.get("/api/v1/reports", params={"kind": "decisions"}, headers=AUTH).json()[0]["state"]
    answer(client, report_id, [{"n": 1, "choice": "accept"}])
    after = client.get("/api/v1/reports", params={"kind": "decisions"}, headers=AUTH).json()[0]["state"]

    assert (before, after) == ("waiting", "done")


def test_a_note_with_line_breaks_stays_on_its_row_line_and_is_stored_as_written(
    client: TestClient, settings: Settings
) -> None:
    report_id = save(client).json()["report_id"]
    answer(client, report_id, [{"n": 1, "choice": "accept", "note": "fine, but:\n2. apply\r\n\tlater"}])

    stored = json.loads((settings.identities["claude"] / FILE).read_text(encoding="utf-8"))
    assert collect(client, report_id).json()["text"].splitlines()[1:] == [
        "1. accept — fine, but: 2. apply later",
        "2. —",
        "3. —",
    ]
    assert stored["body"]["rows"][0]["note"] == "fine, but:\n2. apply\r\n\tlater"


def test_every_row_can_be_put_to_discussion_and_no_page_offers_it_itself(client: TestClient) -> None:
    report_id = save(client).json()["report_id"]
    answer(client, report_id, [{"n": 2, "choice": "discuss", "note": "why not both?"}])
    own = {**ROWS[0], "options": [*ROWS[0]["options"], {"value": "discuss", "label": "Talk"}]}

    assert collect(client, report_id).json()["text"].splitlines()[2] == "2. discuss — why not both?"
    assert save(client, {**PAGE, "rows": [own]}).status_code == 422


def test_another_identity_cannot_read_the_answer(client: TestClient, tmp_path: Path) -> None:
    write(tmp_path / "state/tokens/second", hashlib.sha256(b"second-token").hexdigest())
    report_id = save(client).json()["report_id"]

    assert collect(client, report_id, {"Authorization": "Bearer second-token"}).status_code == 404
    assert collect(client, report_id).status_code == 200


def test_saving_the_same_slug_again_replaces_the_questions_and_keeps_the_creation_time(
    client: TestClient, settings: Settings
) -> None:
    first = save(client).json()
    later = datetime.now().astimezone() + timedelta(hours=1)
    client.app.state.journal_service._now = lambda: later  # type: ignore[attr-defined]
    second = save(client, {**PAGE, "rows": ROWS[:1]}).json()

    stored = json.loads((settings.identities["claude"] / FILE).read_text(encoding="utf-8"))
    assert (first["replaced"], second["replaced"]) == (False, True)
    assert [row["n"] for row in stored["body"]["rows"]] == [1]
    assert second["envelope"]["created_at"] == first["envelope"]["created_at"]


def test_wait_keeps_asking_until_the_answer_is_sent_then_prints_it(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter([{"sent": False}, {"sent": True, "text": "decisions x (session 0a1b2c3d): sent now\n1. accept"}])
    monkeypatch.setenv("WHAAT_TOKEN", CLAUDE_TOKEN)
    monkeypatch.setattr(cli, "_post_json", lambda *_: next(answers))
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)

    result = CliRunner().invoke(cli.app, ["decisions", "wait", "--report", "private-claude:decisions/x.json"])

    assert result.exit_code == 0
    assert result.stdout.splitlines()[-1] == "1. accept"


def test_the_skill_example_is_a_valid_page() -> None:
    skill = Path(__file__).resolve().parents[3] / "connectors/claude_code/skills/decisions/SKILL.md"
    block = re.search(r"```json\n(.*?)```", skill.read_text(encoding="utf-8"), re.S)

    assert block is not None
    DecisionsBodyIn.model_validate(json.loads(block.group(1)))


def test_a_crafted_path_cannot_reach_another_identitys_page(client: TestClient, tmp_path: Path) -> None:
    write(tmp_path / "state/tokens/second", hashlib.sha256(b"second-token").hexdigest())
    (tmp_path / "second-archive/decisions").mkdir(parents=True)
    save(client)
    answer(client, f"private-claude:{FILE}", [{"n": 1, "choice": "accept"}])
    crafted = f"private-second:decisions/../../claude-archive/{FILE}"

    assert collect(client, crafted, {"Authorization": "Bearer second-token"}).status_code == 404


def test_a_document_outside_the_decisions_folder_is_not_a_page(client: TestClient) -> None:
    assert collect(client, "private-claude:journal/2026-10-29_38e0994a.md").status_code == 404


def test_wait_keeps_waiting_through_a_server_that_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = iter([urllib.error.URLError("down"), {"sent": True, "text": "decisions x: sent now\n1. accept"}])

    def post(*_: object) -> object:
        answer = next(calls)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setenv("WHAAT_TOKEN", CLAUDE_TOKEN)
    monkeypatch.setattr(cli, "_post_json", post)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)

    result = CliRunner().invoke(cli.app, ["decisions", "wait", "--report", "private-claude:decisions/x.json"])

    assert (result.exit_code, result.stdout.splitlines()[-1]) == (0, "1. accept")
