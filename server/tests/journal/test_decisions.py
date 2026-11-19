import json
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import CLAUDE_TOKEN, TOKEN
from whaat.config import Settings

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
