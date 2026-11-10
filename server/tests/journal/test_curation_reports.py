import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import CLAUDE_TOKEN, write
from tests.journal.test_api import git, isolated_git  # noqa: F401
from whaat.config import Settings

AUTH = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
FILE = "memory-curation/2026/11/2026-11-05_memory-curation.json"
ROW = {
    "n": 1,
    "file": "acme/shop/reference_old_recipe.md",
    "actions": ["verify"],
    "target": None,
    "reason": "stale at 0.35",
    "evidence": None,
}
REPORT = {"lint_summary": "1 index, 0 problems", "rows": [ROW], "unchecked": "Nothing left unchecked."}


@pytest.fixture(autouse=True)
def the_memory_the_rows_name(settings: Settings) -> None:
    write(
        settings.identities["claude"] / "memory/acme/shop/reference_old_recipe.md",
        "---\nname: reference_old_recipe\ndescription: d\ntype: feedback\n---\nB.\n",
    )


def save(client: TestClient, report: dict[str, Any]) -> Any:
    return client.post(
        "/api/v1/journal/curation-reports", json={"entry_date": "2026-11-05", "report": report}, headers=AUTH
    )


def test_the_report_is_stored_privately_listed_and_comes_back_typed(client: TestClient, settings: Settings) -> None:
    saved = save(client, REPORT).json()

    stored = json.loads((settings.identities["claude"] / FILE).read_text(encoding="utf-8"))
    listed = client.get("/api/v1/reports", params={"kind": "memory-curation"}, headers=AUTH).json()
    detail = client.get(f"/api/v1/reports/{saved['report_id']}", headers=AUTH).json()

    assert stored["body"]["rows"] == [{**ROW, "applied": None, "decision": None, "note": None, "sent_at": None}]
    assert [(r["id"], r["envelope"]["identity"], r["private"]) for r in listed] == [
        (saved["report_id"], "claude", True)
    ]
    assert detail["body"]["format"] == "memory-curation"
    assert detail["body"]["report"]["rows"][0]["actions"] == ["verify"]


def test_a_later_save_that_day_replaces_the_report(client: TestClient, settings: Settings) -> None:
    save(client, REPORT)
    second = save(client, {**REPORT, "rows": [{**ROW, "applied": "store abc1234"}]}).json()

    stored = json.loads((settings.identities["claude"] / FILE).read_text(encoding="utf-8"))
    assert second["replaced"] is True
    assert stored["body"]["rows"][0]["applied"] == "store abc1234"


def test_an_unknown_action_or_a_repeated_row_number_is_refused(client: TestClient) -> None:
    assert save(client, {**REPORT, "rows": [{**ROW, "actions": ["trim", "rename"]}]}).status_code == 422
    assert save(client, {**REPORT, "rows": [{**ROW, "actions": []}]}).status_code == 422
    assert save(client, {**REPORT, "rows": [{**ROW, "actions": ["trim", "trim"]}]}).status_code == 422
    assert save(client, {**REPORT, "rows": [ROW, ROW]}).status_code == 422


def test_actions_that_build_on_each_other_keep_their_order(client: TestClient, settings: Settings) -> None:
    reason = "The trim leaves a body whose line needs a new trigger."
    save(client, {**REPORT, "rows": [{**ROW, "actions": ["trim", "retrigger"], "reason": reason}]})

    stored = json.loads((settings.identities["claude"] / FILE).read_text(encoding="utf-8"))
    assert stored["body"]["rows"][0]["actions"] == ["trim", "retrigger"]


def test_a_row_saved_with_one_action_before_the_list_is_read_as_a_one_element_list(
    client: TestClient, settings: Settings
) -> None:
    old = {k: v for k, v in ROW.items() if k != "actions"} | {"action": "verify"}
    save(client, REPORT)
    path = settings.identities["claude"] / FILE
    document = json.loads(path.read_text(encoding="utf-8"))
    document["body"]["rows"] = [old | {"applied": None, "decision": None, "note": None, "sent_at": None}]
    path.write_text(json.dumps(document), encoding="utf-8")

    listed = client.get("/api/v1/reports", params={"kind": "memory-curation"}, headers=AUTH).json()
    detail = client.get(f"/api/v1/reports/{listed[0]['id']}", headers=AUTH).json()

    assert detail["body"]["report"]["rows"][0]["actions"] == ["verify"]


def test_a_row_without_what_its_actions_require_is_refused_and_named(client: TestClient) -> None:
    def row(n: int, actions: list[str], **fields: Any) -> dict[str, Any]:
        return {**ROW, "n": n, "actions": actions, "evidence": "develop 2026-11-04", **fields}

    rows = [
        row(1, ["verify"], file="feedback_nowhere.md"),
        row(2, ["fix"], target=None),
        row(3, ["merge"], target="`feedback_nowhere.md`"),
        row(4, ["move"], target="`acme/shop`"),
        row(5, ["retrigger"], target="When " + "w" * 150),
        row(6, ["delete"], evidence=None),
        row(7, ["trim", "retrigger"], reason="Too long, and the line is too."),
    ]

    response = save(client, {**REPORT, "rows": rows})

    assert response.status_code == 422
    assert response.json()["detail"] == [
        "row 1: 'feedback_nowhere.md' names no memory of this identity",
        "row 2: `fix` needs a target (the corrected text, or the new file names)",
        "row 3: `merge` needs a target that is another existing memory",
        "row 4: `move` target acme/shop is the dir the file is in",
        "row 5: `retrigger` target is over 150 chars",
        "row 6: `delete` needs evidence",
        "row 7: a row with several actions says in its reason what the later one needs from the earlier",
    ]
