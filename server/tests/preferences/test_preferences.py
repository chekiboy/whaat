import json

from fastapi.testclient import TestClient

from tests.conftest import CLAUDE_TOKEN, TOKEN
from whaat.config import Settings
from whaat.main import create_app

ADMIN = {"Authorization": f"Bearer {TOKEN}"}
URL = "/api/v1/preferences"


def test_the_preferences_start_with_english_the_default_command_and_the_whaat_theme(client: TestClient) -> None:
    prefs = client.get(URL, headers=ADMIN).json()
    assert prefs == {
        "language": "en",
        "identity": {"open_with": "last", "last": None, "agents": {}},
        "terminal": {
            "command": "claude",
            "default_command": "claude",
            "theme": "whaat",
            "opener": "browser",
            "projects": [],
        },
    }


def test_a_change_is_kept_in_one_file_and_an_empty_command_goes_back_to_the_default(
    client: TestClient, settings: Settings
) -> None:
    changed = client.patch(
        URL, json={"language": "hu", "terminal": {"command": " codex ", "theme": "terminal-app:Pro"}}, headers=ADMIN
    ).json()
    assert (changed["language"], changed["terminal"]["command"], changed["terminal"]["theme"]) == (
        "hu",
        "codex",
        "terminal-app:Pro",
    )
    saved = json.loads((settings.state_dir / "preferences.json").read_text())
    assert (saved["language"], saved["terminal"]["command"], saved["terminal"]["theme"]) == (
        "hu",
        "codex",
        "terminal-app:Pro",
    )
    again = TestClient(create_app(settings, TOKEN)).get(URL, headers=ADMIN).json()
    assert again["terminal"]["command"] == "codex"
    reset = client.patch(URL, json={"terminal": {"command": ""}}, headers=ADMIN).json()
    assert (reset["language"], reset["terminal"]["command"], reset["terminal"]["theme"]) == (
        "hu",
        "claude",
        "terminal-app:Pro",
    )


def test_the_identity_the_app_opens_with_and_the_one_chosen_last_are_kept_apart(
    client: TestClient, settings: Settings
) -> None:
    client.patch(URL, json={"identity": {"last": "trial"}}, headers=ADMIN)
    fixed = client.patch(URL, json={"identity": {"open_with": "claude"}}, headers=ADMIN).json()
    assert fixed["identity"] == {"open_with": "claude", "last": "trial", "agents": {}}
    saved = json.loads((settings.state_dir / "preferences.json").read_text())["identity"]
    assert (saved["open_with"], saved["last"]) == ("claude", "trial")
    back = client.patch(URL, json={"identity": {"open_with": "last"}, "language": "hu"}, headers=ADMIN).json()
    assert back["identity"] == {"open_with": "last", "last": "trial", "agents": {}}
    for bad in ({"open_with": "Claude!"}, {"last": "last x"}):
        assert client.patch(URL, json={"identity": bad}, headers=ADMIN).status_code == 422


def test_the_saved_folders_of_the_earlier_file_are_taken_in_once(client: TestClient, settings: Settings) -> None:
    old = settings.state_dir / "terminal" / "projects.json"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text(json.dumps([{"path": "/tmp/earlier", "used": 5}]))
    assert client.get(URL, headers=ADMIN).json()["terminal"]["projects"] == [{"path": "/tmp/earlier", "used": 5}]
    client.patch(URL, json={"language": "hu"}, headers=ADMIN)
    old.write_text("[]")
    assert client.get(URL, headers=ADMIN).json()["terminal"]["projects"] == [{"path": "/tmp/earlier", "used": 5}]


def test_only_the_admin_reads_or_changes_the_preferences_and_unknown_values_are_refused(client: TestClient) -> None:
    agent = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
    assert client.get(URL).status_code == 401
    assert client.get(URL, headers=agent).status_code == 403
    assert client.patch(URL, json={"language": "hu"}, headers=agent).status_code == 403
    assert client.patch(URL, json={"language": "de"}, headers=ADMIN).status_code == 422
    assert client.patch(URL, json={"terminal": {"theme": "neon"}}, headers=ADMIN).status_code == 422


def test_without_a_saved_theme_the_machine_s_own_default_is_the_current_one(client: TestClient, monkeypatch) -> None:
    from whaat.terminal import themes

    monkeypatch.setattr(client.app.state.preferences, "default_theme", lambda: "terminal-app:Clear Dark")  # type: ignore[attr-defined]
    assert client.get(URL, headers=ADMIN).json()["terminal"]["theme"] == "terminal-app:Clear Dark"
    client.patch(URL, json={"terminal": {"theme": "terminal-app:Pro"}}, headers=ADMIN)
    assert client.get(URL, headers=ADMIN).json()["terminal"]["theme"] == "terminal-app:Pro"
    client.patch(URL, json={"terminal": {"theme": "dracula"}}, headers=ADMIN)
    assert client.get(URL, headers=ADMIN).json()["terminal"]["theme"] == "terminal-app:Clear Dark"
    assert themes.READERS == []


def test_an_identitys_agent_config_is_kept_taken_off_and_must_be_a_folder(
    client: TestClient, settings: Settings, tmp_path
) -> None:
    folder = tmp_path / "agent-config"
    folder.mkdir()
    kept = client.patch(URL, json={"identity": {"agents": {"wHaat": str(folder)}}}, headers=ADMIN).json()
    assert kept["identity"]["agents"] == {"wHaat": str(folder)}
    missing = client.patch(URL, json={"identity": {"agents": {"wHaat": str(tmp_path / "nope")}}}, headers=ADMIN)
    assert missing.status_code == 422
    off = client.patch(URL, json={"identity": {"agents": {"wHaat": ""}}}, headers=ADMIN).json()
    assert off["identity"]["agents"] == {}
