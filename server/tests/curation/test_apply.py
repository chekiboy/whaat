import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import CLAUDE_TOKEN, TOKEN, write
from tests.journal.samples import BLOCK

ADMIN = {"Authorization": f"Bearer {TOKEN}"}
CLAUDE = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
ROW = {"n": 1, "file": "feedback_x.md", "actions": ["verify"], "target": None, "reason": "old", "evidence": None}
REPORT = {"lint_summary": "0 problems", "rows": [ROW, {**ROW, "n": 2}], "unchecked": "nothing"}


@pytest.fixture(autouse=True)
def the_memory_the_rows_name(settings: Any) -> None:
    write(
        settings.identities["claude"] / "memory/feedback_x.md",
        "---\nname: feedback_x\ndescription: d\ntype: feedback\n---\nB.\n",
    )


@pytest.fixture
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = write(tmp_path / "gitconfig", "[user]\n\tname = Test\n\temail = test@example.com\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def trial(client: TestClient, isolated_git: None) -> dict[str, str]:
    response = client.post("/api/v1/identities", json={"id": "trial"}, headers=ADMIN)
    return {"Authorization": f"Bearer {response.json()['token']}"}


def memory(client: TestClient, headers: dict[str, str], name: str, body: str) -> str:
    content = f"---\nname: {name}\ndescription: d\ntype: feedback\n---\n{body}\n"
    saved = client.post(
        "/api/v1/memory/memories", json={"path": f"{name}.md", "content": content, "trigger": "t"}, headers=headers
    ).json()
    commit: str = saved["commit"]
    return commit


def git(folder: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True).stdout


def test_applied_cells_are_written_and_emptied_without_touching_the_decisions(
    client: TestClient, settings: Any
) -> None:
    report_id = client.post("/api/v1/journal/curation-reports", json={"report": REPORT}, headers=CLAUDE).json()[
        "report_id"
    ]
    decisions = {"report_id": report_id, "rows": [{"n": 1, "decision": "apply", "note": "keep it short"}]}
    client.post("/api/v1/curation/decisions", json=decisions, headers=ADMIN)

    def applied(value: str | None) -> Any:
        body = {"report_id": report_id, "rows": [{"n": 1, "applied": value}]}
        return client.post("/api/v1/journal/curation-reports/applied", json=body, headers=CLAUDE)

    first = applied("store abc1234")
    stored = json.loads(next((settings.identities["claude"] / "memory-curation").rglob("*.json")).read_text())
    row = stored["body"]["rows"][0]
    assert first.status_code == 200
    assert (row["applied"], row["decision"], row["note"]) == ("store abc1234", "apply", "keep it short")
    applied(None)
    stored = json.loads(next((settings.identities["claude"] / "memory-curation").rglob("*.json")).read_text())
    assert stored["body"]["rows"][0]["applied"] is None
    unknown = {"report_id": report_id, "rows": [{"n": 7, "applied": "x"}]}
    assert client.post("/api/v1/journal/curation-reports/applied", json=unknown, headers=CLAUDE).status_code == 422


def test_a_revert_takes_the_memory_and_its_index_line_back(
    client: TestClient, trial: dict[str, str], settings: Any
) -> None:
    folder = settings.state_dir / "identities" / "trial"
    memory(client, trial, "feedback_stays", "Body.")
    commit = memory(client, trial, "feedback_gone", "Body.")

    reverted = client.post("/api/v1/memory/revert", json={"commits": [commit]}, headers=trial)

    assert reverted.status_code == 200, reverted.text
    assert len(reverted.json()["commits"]) == 1
    assert not (folder / "memory/feedback_gone.md").exists()
    index = (folder / "memory/MEMORY.md").read_text()
    assert "feedback_stays" in index and "feedback_gone" not in index
    assert git(folder, "status", "--porcelain", "memory") == ""


def test_a_commit_outside_the_memory_dir_is_refused(client: TestClient, trial: dict[str, str], settings: Any) -> None:
    folder = settings.state_dir / "identities" / "trial"
    client.post("/api/v1/journal/entries", json={"session": "c08cba1f", "block": BLOCK}, headers=trial)
    journal_commit = git(folder, "rev-parse", "HEAD").strip()

    refused = client.post("/api/v1/memory/revert", json={"commits": [journal_commit]}, headers=trial)

    assert refused.status_code == 409
    assert "outside memory/" in refused.json()["detail"]
    assert git(folder, "rev-parse", "HEAD").strip() == journal_commit


def test_a_conflicting_revert_is_aborted_and_changes_nothing(
    client: TestClient, trial: dict[str, str], settings: Any
) -> None:
    folder = settings.state_dir / "identities" / "trial"
    added = memory(client, trial, "feedback_edited", "First body.")
    memory(client, trial, "feedback_edited", "Second body.")
    head = git(folder, "rev-parse", "HEAD").strip()

    refused = client.post("/api/v1/memory/revert", json={"commits": [added]}, headers=trial)

    assert refused.status_code == 409
    assert "aborted" in refused.json()["detail"]
    assert git(folder, "rev-parse", "HEAD").strip() == head
    assert git(folder, "status", "--porcelain", "memory") == ""
    assert "Second body." in (folder / "memory/feedback_edited.md").read_text()
