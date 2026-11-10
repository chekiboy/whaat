import dataclasses
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import whaat.curation.router as curation_router
from tests.conftest import CLAUDE_TOKEN, TOKEN, write
from whaat.config import Settings
from whaat.main import create_app
from whaat.terminal.agent import Launch

ADMIN = {"Authorization": f"Bearer {TOKEN}"}
CLAUDE = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
# a stand-in for claude: shows a prompt, logs what it reads, answers the session-end call with the closing line and
# leaves on /exit
FAKE_CLAUDE = """import os, sys
seen = open(os.environ["SEEN"], "a", buffering=1)
while True:
    sys.stdout.write("\\u276f "); sys.stdout.flush()
    line = sys.stdin.readline()
    if not line or line.strip() == "/exit":
        break
    seen.write(f"got: {line}")
    if line.startswith("/whaat:session-end"):
        sys.stdout.write("SESSION-END: nothing open\\n"); sys.stdout.flush()
"""


def memory(folder: Path, rel: str, body: str) -> None:
    stem = Path(rel).stem
    write(folder / "memory" / rel, f"---\nname: {stem}\ndescription: d\ntype: feedback\n---\n{body}")


@pytest.fixture
def app(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(curation_router, "WATCH_SECONDS", 0.1)
    instance = f"t{uuid.uuid4().hex[:10]}"
    client = TestClient(create_app(dataclasses.replace(settings, instance=instance, terminal_cwd=tmp_path), TOKEN))
    yield client
    subprocess.run(["tmux", "-L", f"whaat-{instance}", "kill-server"], capture_output=True, check=False)


def report(client: TestClient, rows: list[dict[str, object]]) -> str:
    body = {"report": {"lint_summary": "x", "rows": rows, "unchecked": "nothing"}}
    response = client.post("/api/v1/journal/curation-reports", json=body, headers=CLAUDE)
    assert response.status_code == 201, response.text
    report_id: str = response.json()["report_id"]
    return report_id


def row(n: int, file: str, action: str, target: str | None = None, applied: str | None = None) -> dict[str, object]:
    return {
        "n": n,
        "file": file,
        "actions": [action],
        "target": target,
        "reason": "r",
        "evidence": "e",
        "applied": applied,
    }


def running_fake(client: TestClient, tmp_path: Path) -> Path:
    script = write(tmp_path / "fake-claude", FAKE_CLAUDE)
    seen = tmp_path / "seen.txt"
    client.app.state.terminals.launch = lambda persona: Launch(  # type: ignore[attr-defined]
        command=f"SEEN={seen} python3 {script}", env={}
    )
    assert client.post("/api/v1/curation/start", json={"identity": "claude"}, headers=ADMIN).json()["started"]
    time.sleep(0.5)
    return seen


def wait_for(path: Path, needle: str) -> str:
    for _ in range(100):
        text = path.read_text() if path.exists() else ""
        if needle in text:
            return text
        time.sleep(0.05)
    return path.read_text() if path.exists() else ""


def test_the_view_counts_the_map_as_the_live_page_and_draws_each_row(app: TestClient, settings: Settings) -> None:
    home = settings.identities["claude"]
    memory(home, "feedback_old.md", "x" * 1300)
    memory(home, "feedback_kept.md", "y")
    write(home / "memory/MEMORY.md", "- feedback_old.md — when old\n- feedback_kept.md — when kept\n")
    memory(home, "acme/feedback_far.md", "z")
    memory(home, "personal/feedback_mine.md", "p")
    report_id = report(
        app,
        [
            row(1, "`feedback_old.md`", "delete"),
            row(2, "`feedback_kept.md`", "retrigger", 'new line "when it matters"'),
            row(3, "`acme/feedback_far.md`", "move", "to the global level"),
            row(4, "`feedback_old.md`", "trim"),
        ],
    )

    view = app.get("/api/v1/curation/view", params={"report_id": report_id}, headers=ADMIN).json()

    dirs = {d["dir"]: (d["before"], d["after_lo"], d["after_hi"]) for d in view["map"]["dirs"]}
    assert dirs == {"": (2, 2, 2), "acme": (1, 0, 0)}
    assert (view["map"]["total_before"], view["map"]["total_hi"]) == (3, 2)
    figures = {f["n"]: f for f in view["rows"]}
    assert figures[2]["now"] == "when kept" and figures[2]["after"] == "when it matters"
    assert (figures[3]["from_dir"], figures[3]["dest"]) == ("acme", "")
    assert (figures[4]["size"], figures[4]["budget"]) == (1300, 1200)
    assert not any("personal" in c["file"] for d in view["map"]["dirs"] for c in d["cells"])


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_a_sent_row_is_stamped_refused_again_and_open_again_after_a_revert(
    app: TestClient, settings: Settings, tmp_path: Path
) -> None:
    memory(settings.identities["claude"], "feedback_a.md", "a")
    memory(settings.identities["claude"], "feedback_b.md", "b")
    report_id = report(
        app, [row(1, "feedback_a.md", "verify"), row(2, "feedback_b.md", "fix", "the fix", applied="store abc")]
    )
    seen = running_fake(app, tmp_path)
    send = {"report_id": report_id, "rows": [{"n": 1, "decision": "apply"}]}

    first = app.post("/api/v1/curation/decisions", json=send, headers=ADMIN).json()
    again = app.post("/api/v1/curation/decisions", json=send, headers=ADMIN)
    refused = app.post("/api/v1/curation/revert", json={"report_id": report_id, "n": 1}, headers=ADMIN)
    reverted = app.post("/api/v1/curation/revert", json={"report_id": report_id, "n": 2}, headers=ADMIN).json()

    stored = json.loads(next((settings.identities["claude"] / "memory-curation").rglob("*.json")).read_text())
    assert first["typed"] and first["at"]
    assert stored["body"]["rows"][0]["sent_at"] == first["at"]
    assert (again.status_code, again.json()["detail"]) == (409, "already sent: rows 1")
    assert (refused.status_code, refused.json()["detail"]) == (400, "rows must be applied rows of this report")
    assert reverted["typed"]
    assert f"report={report_id} rows=2 confirmed=report-page" in wait_for(seen, "revert-applied-rows")


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_done_ends_the_session_and_types_exit_once_it_printed_its_closing_line(app: TestClient, tmp_path: Path) -> None:
    seen = running_fake(app, tmp_path)
    assert app.get("/api/v1/curation/run-state", params={"identity": "claude"}, headers=ADMIN).json()["state"] == "open"

    done = app.post("/api/v1/curation/done", json={"identity": "claude"}, headers=ADMIN).json()

    states = []
    for _ in range(100):
        states.append(
            app.get("/api/v1/curation/run-state", params={"identity": "claude"}, headers=ADMIN).json()["state"]
        )
        if states[-1] == "exited":
            break
        time.sleep(0.1)
    assert done["typed"] and done["command"] == "/whaat:session-end steps=none confirmed=report-page"
    assert "got: /whaat:session-end" in wait_for(seen, "session-end")
    assert states[-1] == "exited"
