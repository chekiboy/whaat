import dataclasses
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import CLAUDE_TOKEN, TOKEN, write
from whaat.config import Settings
from whaat.main import create_app
from whaat.terminal.agent import Launch
from whaat.terminal.tmux import PROMPT_MARK, prompt_line, same_text

ADMIN = {"Authorization": f"Bearer {TOKEN}"}
CLAUDE = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
ROW = {"n": 1, "file": "feedback_x.md", "actions": ["verify"], "target": None, "reason": "old", "evidence": None}
REPORT = {"lint_summary": "0 problems", "rows": [ROW, {**ROW, "n": 2}], "unchecked": "nothing"}


@pytest.fixture(autouse=True)
def the_memory_the_rows_name(settings: Settings) -> None:
    write(
        settings.identities["claude"] / "memory/feedback_x.md",
        "---\nname: feedback_x\ndescription: d\ntype: feedback\n---\nB.\n",
    )


# a stand-in for claude, not a shell (the terminal takes a pane back at its shell as idle): shows a prompt, and writes
# its first argument and every line it reads into a file
FAKE_CLAUDE = """import os, sys
seen = open(os.environ["SEEN"], "a", buffering=1)
seen.write(f"arg: {sys.argv[1]}\\n")
while True:
    sys.stdout.write("\\u276f "); sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        break
    seen.write(f"got: {line}")
"""


@pytest.fixture
def app(settings: Settings, tmp_path: Path):
    instance = f"t{uuid.uuid4().hex[:10]}"
    configured = dataclasses.replace(settings, instance=instance, terminal_cwd=tmp_path)
    client = TestClient(create_app(configured, TOKEN))
    yield client
    subprocess.run(["tmux", "-L", f"whaat-{instance}", "kill-server"], capture_output=True, check=False)


def saved_report(client: TestClient) -> str:
    response = client.post("/api/v1/journal/curation-reports", json={"report": REPORT}, headers=CLAUDE)
    assert response.status_code == 201, response.text
    report_id: str = response.json()["report_id"]
    return report_id


def with_fake_claude(client: TestClient, tmp_path: Path) -> Path:
    script = write(tmp_path / "fake-claude", FAKE_CLAUDE)
    seen = tmp_path / "seen.txt"
    client.app.state.terminals.launch = lambda persona: Launch(  # type: ignore[attr-defined]
        command=f"SEEN={seen} python3 {script}", env={}
    )
    return seen


def wait_for(path: Path, needle: str) -> str:
    for _ in range(100):
        text = path.read_text() if path.exists() else ""
        if needle in text:
            return text
        time.sleep(0.05)
    return path.read_text() if path.exists() else ""


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_the_button_starts_the_report_and_the_decisions_are_saved_and_typed_into_that_session(
    app: TestClient, settings: Settings, tmp_path: Path
) -> None:
    report_id = saved_report(app)
    seen = with_fake_claude(app, tmp_path)

    started = app.post("/api/v1/curation/start", json={"identity": "claude"}, headers=ADMIN).json()
    assert "arg: /whaat:memory-curation report" in wait_for(seen, "arg:")
    again = app.post("/api/v1/curation/start", json={"identity": "claude"}, headers=ADMIN).json()
    sent = app.post(
        "/api/v1/curation/decisions",
        json={"report_id": report_id, "rows": [{"n": 1, "decision": "apply", "note": "only the path"}]},
        headers=ADMIN,
    ).json()

    call = f"/whaat:memory-curation apply-rows report={report_id} confirmed=report-page"
    stored = json.loads(next((settings.identities["claude"] / "memory-curation").rglob("*.json")).read_text())
    assert (started["started"], started["session"]["label"], again["started"]) == (True, "memory-curation", False)
    assert (sent["typed"], sent["session"], sent["command"]) == (True, started["session"]["name"], call)
    assert f"got: {call}" in wait_for(seen, "got:")
    assert [(r["decision"], r["note"]) for r in stored["body"]["rows"]] == [("apply", "only the path"), (None, None)]


def test_without_a_running_session_the_decisions_are_saved_and_the_call_is_handed_back(app: TestClient) -> None:
    report_id = saved_report(app)
    body = {"report_id": report_id, "rows": [{"n": 2, "decision": "apply"}]}

    sent = app.post("/api/v1/curation/decisions", json=body, headers=ADMIN).json()

    assert (sent["typed"], sent["detail"]) == (False, "no curation session runs for this identity")
    assert sent["command"].endswith(f"report={report_id} confirmed=report-page")


def test_decisions_are_refused_for_an_unknown_row_or_report_and_for_an_identity(app: TestClient) -> None:
    report_id = saved_report(app)
    row = [{"n": 9, "decision": "apply"}]
    assert (
        app.post("/api/v1/curation/decisions", json={"report_id": report_id, "rows": row}, headers=ADMIN).status_code
        == 422
    )
    missing = {"report_id": "private-claude:memory-curation/x.json", "rows": []}
    assert app.post("/api/v1/curation/decisions", json=missing, headers=ADMIN).status_code == 404
    assert (
        app.post("/api/v1/curation/decisions", json={"report_id": report_id, "rows": []}, headers=CLAUDE).status_code
        == 403
    )


def test_an_identity_without_an_agent_config_cannot_start_a_curation(app: TestClient) -> None:
    response = app.post("/api/v1/curation/start", json={"identity": "claude"}, headers=ADMIN)
    assert response.status_code == 409


def test_the_prompt_is_read_back_and_a_dim_suggestion_counts_as_empty() -> None:
    assert prompt_line(f"x\n{PROMPT_MARK} hello world\n") == ("hello world", False)
    assert prompt_line(f"{PROMPT_MARK} \x1b[2mTry this\x1b[0m\n") == ("Try this", True)
    assert prompt_line("no prompt here") == (None, False)
    assert same_text("a b", "ab") and not same_text(None, "a")


def test_discarding_only_saves_and_types_nothing_and_the_next_run_sees_it(app: TestClient) -> None:
    report_id = saved_report(app)
    body = {"report_id": report_id, "rows": [{"n": 2, "decision": "reject", "note": "not now"}]}

    sent = app.post("/api/v1/curation/decisions", json=body, headers=ADMIN).json()
    discarded = app.get("/api/v1/curation/discarded", headers=CLAUDE).json()

    assert (sent["typed"], sent["detail"]) == (False, "only discarded rows: nothing to apply, the decisions are saved")
    assert [(d["file"], d["actions"], d["note"], d["report_id"]) for d in discarded] == [
        ("feedback_x.md", ["verify"], "not now", report_id)
    ]
    assert discarded[0]["changed_since"] is False


def test_a_rejected_row_of_a_report_saved_before_the_actions_list_is_still_discarded(
    app: TestClient, settings: Settings
) -> None:
    saved_report(app)
    path = next((settings.identities["claude"] / "memory-curation").rglob("*_memory-curation.json"))
    document = json.loads(path.read_text(encoding="utf-8"))
    old = {k: v for k, v in document["body"]["rows"][0].items() if k != "actions"}
    document["body"]["rows"] = [old | {"action": "verify", "decision": "reject"}]
    path.write_text(json.dumps(document), encoding="utf-8")

    discarded = app.get("/api/v1/curation/discarded", headers=CLAUDE).json()

    assert [(d["file"], d["actions"]) for d in discarded] == [("feedback_x.md", ["verify"])]
