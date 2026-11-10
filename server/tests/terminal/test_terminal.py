import dataclasses
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import CLAUDE_TOKEN, TOKEN
from whaat.config import Settings
from whaat.main import create_app
from whaat.terminal.tmux import Session

pytestmark = pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
ADMIN = {"Authorization": f"Bearer {TOKEN}"}
ORIGIN = {"origin": "http://testserver"}  # copied per call: the test client writes its own headers into the dict


@pytest.fixture
def terminal(settings: Settings, tmp_path: Path):
    instance = f"t{uuid.uuid4().hex[:10]}"
    configured = dataclasses.replace(
        settings, instance=instance, terminal_command="printf 'whaat-ready\\n'", terminal_cwd=tmp_path
    )
    yield TestClient(create_app(configured, TOKEN))
    subprocess.run(["tmux", "-L", f"whaat-{instance}", "kill-server"], capture_output=True, check=False)


def screen(ws, needle: str, frames: int = 200) -> str:
    seen = ""
    for _ in range(frames):
        seen += ws.receive_bytes().decode(errors="replace")
        if needle in seen:
            return seen
    return seen


def test_sessions_are_numbered_per_persona_and_listed(terminal: TestClient, tmp_path: Path) -> None:
    assert terminal.get("/api/v1/terminal/sessions", headers=ADMIN).json()["sessions"] == []
    first = terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN)
    second = terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN)
    other = terminal.post("/api/v1/terminal/sessions", json={"persona": "second"}, headers=ADMIN)
    assert [first.status_code, second.status_code, other.status_code] == [201, 201, 201]
    assert [first.json()["name"], second.json()["name"], other.json()["name"]] == [
        "whaat-claude-1",
        "whaat-claude-2",
        "whaat-second-1",
    ]
    listed = terminal.get("/api/v1/terminal/sessions", params={"persona": "claude"}, headers=ADMIN).json()
    assert [s["name"] for s in listed["sessions"]] == ["whaat-claude-1", "whaat-claude-2"]
    assert listed["sessions"][0]["command"] == "printf 'whaat-ready\\n'"
    assert listed["cwd"] == str(tmp_path)


def test_a_persona_with_capitals_gets_its_session_listed_and_a_second_one_numbered(
    settings: Settings, tmp_path: Path
) -> None:
    instance = f"t{uuid.uuid4().hex[:10]}"
    configured = dataclasses.replace(
        settings,
        identities={**settings.identities, "wHaat": tmp_path / "whaat-identity"},
        instance=instance,
        terminal_command="printf 'whaat-ready\\n'",
        terminal_cwd=tmp_path,
    )
    client = TestClient(create_app(configured, TOKEN), raise_server_exceptions=False)
    try:
        first = client.post("/api/v1/terminal/sessions", json={"persona": "wHaat"}, headers=ADMIN)
        second = client.post("/api/v1/terminal/sessions", json={"persona": "wHaat"}, headers=ADMIN)
        listed = client.get("/api/v1/terminal/sessions", params={"persona": "wHaat"}, headers=ADMIN).json()
    finally:
        subprocess.run(["tmux", "-L", f"whaat-{instance}", "kill-server"], capture_output=True, check=False)
    assert [first.status_code, second.status_code] == [201, 201]
    assert [s["name"] for s in listed["sessions"]] == ["whaat-wHaat-1", "whaat-wHaat-2"]


def test_an_unknown_persona_gets_no_session(terminal: TestClient) -> None:
    response = terminal.post("/api/v1/terminal/sessions", json={"persona": "nobody"}, headers=ADMIN)
    assert response.status_code == 404


def test_only_the_admin_token_reaches_the_terminal(terminal: TestClient) -> None:
    agent = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
    assert terminal.get("/api/v1/terminal/sessions").status_code == 401
    assert terminal.get("/api/v1/terminal/sessions", headers=agent).status_code == 403
    assert terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=agent).status_code == 403
    assert terminal.delete("/api/v1/terminal/sessions/whaat-claude-1", headers=agent).status_code == 403


@pytest.mark.parametrize(
    ("protocols", "headers"),
    [
        (["whaat", TOKEN], {}),
        (["whaat", TOKEN], {"origin": "http://evil.example"}),
        (["whaat", CLAUDE_TOKEN], ORIGIN),
        (["whaat", "wrong"], ORIGIN),
        ([TOKEN], ORIGIN),
    ],
    ids=["no-origin", "other-origin", "agent-token", "wrong-token", "no-protocol"],
)
def test_the_attach_socket_refuses_what_is_not_whaat_s_own_page(
    terminal: TestClient, protocols: list[str], headers: dict[str, str]
) -> None:
    terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN)
    with (
        pytest.raises(WebSocketDisconnect) as refused,
        terminal.websocket_connect(
            "/api/v1/terminal/sessions/whaat-claude-1/attach", subprotocols=protocols, headers=dict(headers)
        ) as ws,
    ):
        ws.receive_bytes()
    assert refused.value.code == 4401


def test_attaching_to_a_missing_session_is_refused(terminal: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as gone,
        terminal.websocket_connect(
            "/api/v1/terminal/sessions/whaat-claude-9/attach", subprotocols=["whaat", TOKEN], headers=dict(ORIGIN)
        ) as ws,
    ):
        ws.receive_bytes()
    assert gone.value.code == 4404


def test_a_closed_window_leaves_the_session_running_and_it_opens_again(terminal: TestClient) -> None:
    terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN)
    url = "/api/v1/terminal/sessions/whaat-claude-1/attach"
    with terminal.websocket_connect(url, subprotocols=["whaat", TOKEN], headers=dict(ORIGIN)) as ws:
        assert ws.accepted_subprotocol == "whaat"
        ws.send_text('{"cols": 100, "rows": 30}')
        assert "whaat-ready" in screen(ws, "whaat-ready")
        ws.send_bytes(b"echo typed-$((40+2))\r")
        assert "typed-42" in screen(ws, "typed-42")
    listed = terminal.get("/api/v1/terminal/sessions", headers=ADMIN).json()["sessions"]
    assert [s["name"] for s in listed] == ["whaat-claude-1"]
    with terminal.websocket_connect(url, subprotocols=["whaat", TOKEN], headers=dict(ORIGIN)) as ws:
        ws.send_text('{"cols": 100, "rows": 30}')
        assert "typed-42" in screen(ws, "typed-42")


def test_closing_a_session_stops_it(terminal: TestClient) -> None:
    terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN)
    assert terminal.delete("/api/v1/terminal/sessions/whaat-claude-1", headers=ADMIN).status_code == 204
    assert terminal.get("/api/v1/terminal/sessions", headers=ADMIN).json()["sessions"] == []
    assert terminal.delete("/api/v1/terminal/sessions/whaat-claude-1", headers=ADMIN).status_code == 404


def test_a_session_starts_in_the_picked_project_and_the_project_is_saved_first(
    terminal: TestClient, tmp_path: Path
) -> None:
    first, second = (tmp_path / "proj-a").resolve(), (tmp_path / "proj-b").resolve()
    first.mkdir()
    second.mkdir()
    for project in (first, second, first):
        made = terminal.post(
            "/api/v1/terminal/sessions", json={"persona": "claude", "cwd": str(project)}, headers=ADMIN
        )
        assert made.status_code == 201
        assert Path(made.json()["cwd"]).resolve() == project
    saved = terminal.get("/api/v1/terminal/projects", headers=ADMIN).json()["projects"]
    assert [p["path"] for p in saved] == [str(first), str(second)]
    assert all(p["exists"] for p in saved)


def test_a_session_does_not_start_in_a_folder_that_is_not_there(terminal: TestClient, tmp_path: Path) -> None:
    for cwd in (str(tmp_path / "missing"), "relative/path"):
        made = terminal.post("/api/v1/terminal/sessions", json={"persona": "claude", "cwd": cwd}, headers=ADMIN)
        assert made.status_code == 422
    assert terminal.get("/api/v1/terminal/projects", headers=ADMIN).json()["projects"] == []


def test_the_folder_browser_lists_subfolders_and_marks_repos(terminal: TestClient, tmp_path: Path) -> None:
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    (tmp_path / "plain").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("x")
    listed = terminal.get("/api/v1/terminal/folders", params={"path": str(tmp_path)}, headers=ADMIN).json()
    assert listed["path"] == str(tmp_path.resolve())
    assert listed["parent"] == str(tmp_path.resolve().parent)
    names = {f["name"]: f["repo"] for f in listed["folders"]}
    assert names["repo"] is True and names["plain"] is False
    assert ".hidden" not in names and "file.txt" not in names
    shown = terminal.get("/api/v1/terminal/folders", params={"path": str(tmp_path), "hidden": True}, headers=ADMIN)
    assert ".hidden" in {f["name"] for f in shown.json()["folders"]}
    bad = terminal.get("/api/v1/terminal/folders", params={"path": str(tmp_path / "file.txt")}, headers=ADMIN)
    assert bad.status_code == 422


def test_a_saved_project_can_be_forgotten(terminal: TestClient, tmp_path: Path) -> None:
    terminal.post("/api/v1/terminal/sessions", json={"persona": "claude", "cwd": str(tmp_path)}, headers=ADMIN)
    path = str(tmp_path.resolve())
    assert terminal.delete("/api/v1/terminal/projects", params={"path": path}, headers=ADMIN).status_code == 204
    assert terminal.get("/api/v1/terminal/projects", headers=ADMIN).json()["projects"] == []
    assert terminal.delete("/api/v1/terminal/projects", params={"path": path}, headers=ADMIN).status_code == 404


def test_the_folder_browser_and_projects_need_the_admin_token(terminal: TestClient) -> None:
    agent = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
    assert terminal.get("/api/v1/terminal/folders", headers=agent).status_code == 403
    assert terminal.get("/api/v1/terminal/projects", headers=agent).status_code == 403
    assert terminal.delete("/api/v1/terminal/projects", params={"path": "/"}, headers=agent).status_code == 403


def test_a_session_can_be_named_and_the_name_taken_off(terminal: TestClient) -> None:
    terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN)
    url = "/api/v1/terminal/sessions/whaat-claude-1"
    named = terminal.patch(url, json={"label": "  ABC-103   review\tfix  "}, headers=ADMIN)
    assert named.status_code == 200
    assert named.json()["label"] == "ABC-103 review fix"
    listed = terminal.get("/api/v1/terminal/sessions", headers=ADMIN).json()["sessions"]
    assert listed[0]["label"] == "ABC-103 review fix"
    assert terminal.patch(url, json={"label": ""}, headers=ADMIN).json()["label"] == ""
    assert (
        terminal.patch("/api/v1/terminal/sessions/whaat-claude-9", json={"label": "x"}, headers=ADMIN).status_code
        == 404
    )
    agent = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
    assert terminal.patch(url, json={"label": "x"}, headers=agent).status_code == 403


@pytest.mark.parametrize(
    ("program", "idle"), [("zsh", True), ("-zsh", True), ("bash", True), ("2.1.317", False), ("sleep", False)]
)
def test_a_session_is_idle_when_only_the_shell_runs(program: str, idle: bool) -> None:
    assert Session("whaat-claude-1", "claude", 1, 0, 0, "/", "claude", program=program).idle is idle


def test_a_session_whose_command_exited_is_listed_as_idle(terminal: TestClient) -> None:
    terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN)
    for _ in range(50):
        session = terminal.get("/api/v1/terminal/sessions", headers=ADMIN).json()["sessions"][0]
        if session["idle"]:
            break
        time.sleep(0.1)
    assert session["idle"] is True
    assert session["program"].lstrip("-") in {"zsh", "bash", "sh"}


def test_a_started_session_is_recorded_on_disk_with_its_tmux_id(terminal: TestClient, settings: Settings) -> None:
    made = terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN).json()
    recorded = json.loads((settings.state_dir / "terminal" / "sessions.json").read_text())
    assert [(e["name"], e["persona"], e["tmux_server"]) for e in recorded] == [
        ("whaat-claude-1", "claude", f"whaat-{terminal.app.state.settings.instance}")  # type: ignore[attr-defined]
    ]
    assert recorded[0]["tmux_id"].startswith("$") and recorded[0]["tmux_id"] == made["tmux_id"]


def test_a_new_server_knows_what_the_last_one_started_and_keeps_its_name(
    terminal: TestClient, settings: Settings
) -> None:
    terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN)
    terminal.patch("/api/v1/terminal/sessions/whaat-claude-1", json={"label": "review"}, headers=ADMIN)
    again = TestClient(create_app(terminal.app.state.settings, TOKEN))  # type: ignore[attr-defined]
    listed = again.get("/api/v1/terminal/sessions", headers=ADMIN).json()["sessions"]
    assert [(s["name"], s["label"], s["gone"]) for s in listed] == [("whaat-claude-1", "review", False)]


def test_a_session_tmux_lost_is_listed_as_gone_until_it_is_forgotten(terminal: TestClient) -> None:
    terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN)
    label = terminal.app.state.tmux.label  # type: ignore[attr-defined]
    subprocess.run(["tmux", "-L", label, "kill-server"], capture_output=True, check=False)
    listed = terminal.get("/api/v1/terminal/sessions", headers=ADMIN).json()["sessions"]
    assert [(s["name"], s["gone"]) for s in listed] == [("whaat-claude-1", True)]
    with (
        pytest.raises(WebSocketDisconnect) as gone,
        terminal.websocket_connect(
            "/api/v1/terminal/sessions/whaat-claude-1/attach", subprotocols=["whaat", TOKEN], headers=dict(ORIGIN)
        ) as ws,
    ):
        ws.receive_bytes()
    assert gone.value.code == 4404
    again = terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN).json()
    assert again["name"] == "whaat-claude-2"
    assert terminal.delete("/api/v1/terminal/sessions/whaat-claude-1", headers=ADMIN).status_code == 204
    listed = terminal.get("/api/v1/terminal/sessions", headers=ADMIN).json()["sessions"]
    assert [(s["name"], s["gone"]) for s in listed] == [("whaat-claude-2", False)]


def test_a_whaat_session_tmux_runs_but_the_record_lacks_is_taken_in(terminal: TestClient, settings: Settings) -> None:
    terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN)
    (settings.state_dir / "terminal" / "sessions.json").unlink()
    listed = terminal.get("/api/v1/terminal/sessions", headers=ADMIN).json()["sessions"]
    assert [(s["name"], s["gone"]) for s in listed] == [("whaat-claude-1", False)]
    recorded = json.loads((settings.state_dir / "terminal" / "sessions.json").read_text())
    assert [e["name"] for e in recorded] == ["whaat-claude-1"]


def test_a_new_session_runs_the_command_saved_in_the_preferences_without_a_restart(terminal: TestClient) -> None:
    terminal.patch("/api/v1/preferences", json={"terminal": {"command": "printf 'saved\\n'"}}, headers=ADMIN)
    made = terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN).json()
    assert made["command"] == "printf 'saved\\n'"
    assert terminal.get("/api/v1/terminal/sessions", headers=ADMIN).json()["command"] == "printf 'saved\\n'"


def test_a_running_session_opens_in_a_terminal_app_attached_to_the_same_tmux_session(terminal: TestClient) -> None:
    opened: list[tuple[str, list[str]]] = []
    terminal.app.state.native_open = lambda app, argv: opened.append((app, argv))  # type: ignore[attr-defined]
    terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN)
    url = "/api/v1/terminal/sessions/whaat-claude-1/open"
    assert terminal.post(url, json={}, headers=ADMIN).status_code == 422  # the preference is still the browser
    terminal.patch("/api/v1/preferences", json={"terminal": {"opener": "terminal-app"}}, headers=ADMIN)
    assert terminal.post(url, json={}, headers=ADMIN).status_code == 204
    assert terminal.post(url, json={"app": "iterm2"}, headers=ADMIN).status_code == 204
    label = terminal.app.state.tmux.label  # type: ignore[attr-defined]
    assert [app for app, _ in opened] == ["terminal-app", "iterm2"]
    assert all(argv[1:] == ["-L", label, "attach-session", "-t", "whaat-claude-1"] for _, argv in opened)
    assert terminal.post("/api/v1/terminal/sessions/whaat-claude-9/open", json={}, headers=ADMIN).status_code == 404
    agent = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
    assert terminal.post(url, json={}, headers=agent).status_code == 403


def test_the_applescript_quotes_the_attach_command() -> None:
    from whaat.terminal.native import script_for

    script = script_for("terminal-app", 'tmux -L "x" attach -t a\\b')
    assert 'do script "tmux -L \\"x\\" attach -t a\\\\b"' in script
    assert 'create window with default profile command "' in script_for("iterm2", "tmux attach")


def test_an_identity_with_an_agent_config_starts_claude_with_it_the_plugin_and_its_token_in_the_config(
    terminal: TestClient, tmp_path: Path
) -> None:
    token = terminal.post("/api/v1/identities", json={"id": "agent"}, headers=ADMIN).json()["token"]
    config = tmp_path / "agent-config"
    config.mkdir()
    (config / "settings.json").write_text(json.dumps({"env": {"KEEP": "1"}, "theme": "dark"}))
    terminal.patch("/api/v1/preferences", json={"identity": {"agents": {"agent": str(config)}}}, headers=ADMIN)

    made = terminal.post("/api/v1/terminal/sessions", json={"persona": "agent"}, headers=ADMIN)

    assert made.status_code == 201
    written = json.loads((config / "settings.json").read_text())
    assert written["env"].get("WHAAT_TOKEN") == token
    assert written["env"]["KEEP"] == "1" and written["theme"] == "dark"
    assert (config / "settings.json").stat().st_mode & 0o777 == 0o600
    assert "--plugin-dir" in made.json()["command"] and token not in made.json()["command"]
    label = terminal.app.state.tmux.label  # type: ignore[attr-defined]
    shown = subprocess.run(
        ["tmux", "-L", label, "show-environment", "-t", made.json()["name"], "CLAUDE_CONFIG_DIR"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert shown.stdout.strip() == f"CLAUDE_CONFIG_DIR={config}"
    plain = terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN).json()
    assert "--plugin-dir" not in plain["command"]


def test_an_agent_config_without_a_kept_token_refuses_the_session(terminal: TestClient, tmp_path: Path) -> None:
    config = tmp_path / "agent-config"
    config.mkdir()
    terminal.patch("/api/v1/preferences", json={"identity": {"agents": {"claude": str(config)}}}, headers=ADMIN)

    refused = terminal.post("/api/v1/terminal/sessions", json={"persona": "claude"}, headers=ADMIN)

    assert refused.status_code == 409
    assert "new token" in refused.json()["detail"]
    assert not (config / "settings.json").exists()


def test_the_migration_starts_in_the_agent_config_unless_a_folder_is_given(
    terminal: TestClient, tmp_path: Path
) -> None:
    terminal.post("/api/v1/identities", json={"id": "agent"}, headers=ADMIN)
    config, project = tmp_path / "agent-config", tmp_path / "project"
    config.mkdir()
    project.mkdir()
    terminal.patch("/api/v1/preferences", json={"identity": {"agents": {"agent": str(config)}}}, headers=ADMIN)

    started = terminal.post("/api/v1/memory/migration/start", json={"identity": "agent"}, headers=ADMIN).json()
    terminal.delete(f"/api/v1/terminal/sessions/{started['name']}", headers=ADMIN)
    chosen = terminal.post(
        "/api/v1/memory/migration/start", json={"identity": "agent", "cwd": str(project)}, headers=ADMIN
    ).json()

    assert started["cwd"] == str(config.resolve())
    assert chosen["cwd"] == str(project.resolve())


MARK = "❯"  # noqa: RUF001 - Claude Code's prompt mark

TRUST = f""" Accessing workspace:
 /Users/me
 Quick safety check: Is this a project you created or one you trust?
 {MARK} No, exit
   Yes, I trust this folder
 Enter to confirm · Esc to cancel
"""
IMPORTS = f"""  Allow external CLAUDE.md file imports?
  {MARK} No, disable external imports
    Yes, allow external imports
  Enter to confirm · Esc to cancel
"""
PERMISSION = f""" Bash command
   git status
 Do you want to proceed?
 {MARK} 1. Yes
   2. No
"""
QUESTION = f"""│ Which memory sources should it include?
{MARK} 1. Configured only (Recommended)
  2. Configured + ~/.claude
  3. Type something.
  4. Chat about this
Enter to select · ↑/↓ to navigate · Esc to cancel
"""
WORKING = f"""✶ Percolating… (25s · ↓ 2.4k tokens)
{MARK}
  ⏵⏵ auto mode on (shift+tab to cycle) · esc to interrupt
"""
DONE = f"""✻ Crunched for 26s · done 12:58 PM
{MARK}
  ⏵⏵ auto mode on (shift+tab to cycle)
"""
GOES_ON = "Continuing automatically in 5s · Esc to cancel\n"
TEXT_QUESTION = f"""Reply with which of links 1-2 to apply.
[whaat] waiting for your answer
✻ Brewed for 37s · done 2:02 PM
{MARK}
"""
FINISHED = f"""The three memories stay where they are.
[whaat] done
✻ Brewed for 12s · done 2:05 PM
{MARK}
"""
ANSWERED_THEN_FINISHED = "[whaat] waiting for your answer\n" + FINISHED


@pytest.mark.parametrize(
    ("screen", "asking"),
    [
        (TRUST, True),
        (IMPORTS, True),
        (PERMISSION, True),
        (QUESTION, True),
        (WORKING, False),
        (DONE, False),
        (GOES_ON, False),
        (TEXT_QUESTION, True),
        (FINISHED, False),
        (ANSWERED_THEN_FINISHED, False),
    ],
    ids=["trust", "imports", "permission", "question", "working", "done", "goes-on", "text", "finished", "answered"],
)
def test_a_session_asks_while_a_dialog_waits_for_the_user(screen: str, asking: bool) -> None:
    from whaat.terminal.tmux import waits_for_answer

    assert waits_for_answer(screen) is asking


@pytest.mark.parametrize(
    ("screen", "done"),
    [(FINISHED, True), (ANSWERED_THEN_FINISHED, True), (TEXT_QUESTION, False), (WORKING + "[whaat] done\n", False)],
    ids=["finished", "answered", "text", "working"],
)
def test_a_skill_says_it_is_done_with_its_last_turn_mark(screen: str, done: bool) -> None:
    from whaat.terminal.tmux import says_done

    assert says_done(screen) is done
