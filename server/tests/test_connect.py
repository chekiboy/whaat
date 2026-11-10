import json
import os
import stat
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from whaat.cli import main as cli
from whaat.cli.main import _connect_token, claude_settings_file
from whaat.config import Settings
from whaat.git import GitCommitter
from whaat.identities.registry import IdentityRegistry
from whaat.security import load_or_create_token
from whaat.terminal.agent import CONNECTOR, add_connector, with_connector


def test_the_connector_joins_the_other_plugin_folders_once_and_last() -> None:
    joined = with_connector(os.pathsep.join(["/opt/one", "/opt/two"]))

    assert joined.split(os.pathsep) == ["/opt/one", "/opt/two", str(CONNECTOR)]
    assert with_connector(joined) == joined


def test_another_checkouts_whaat_connector_is_replaced_and_other_plugins_stay(tmp_path: Path) -> None:
    other_whaat, other_plugin = tmp_path / "old-whaat", tmp_path / "other"
    write_manifest(other_whaat, "whaat")
    write_manifest(other_plugin, "notes")

    joined = with_connector(os.pathsep.join([str(other_whaat), str(other_plugin)]))

    assert joined.split(os.pathsep) == [str(other_plugin), str(CONNECTOR)]


def write_manifest(folder: Path, name: str) -> None:
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}))


def test_the_connector_goes_into_the_settings_and_keeps_the_rest(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"model": "opus", "env": {"OTHER": "kept", "CLAUDE_CODE_PLUGIN_DIRS": "/opt/one"}}))

    add_connector(target)

    data = json.loads(target.read_text())
    assert data["model"] == "opus"
    assert data["env"] == {"OTHER": "kept", "CLAUDE_CODE_PLUGIN_DIRS": os.pathsep.join(["/opt/one", str(CONNECTOR)])}
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_a_project_connects_in_its_own_local_settings_and_global_in_the_config_in_use(tmp_path: Path) -> None:
    assert claude_settings_file(False, tmp_path, {}) == tmp_path / ".claude" / "settings.local.json"
    assert claude_settings_file(True, tmp_path, {"CLAUDE_CONFIG_DIR": "/cfg"}) == Path("/cfg/settings.json")
    assert claude_settings_file(True, tmp_path, {}) == Path("~/.claude/settings.json").expanduser()


def test_a_known_identity_connects_with_its_kept_token(settings: Settings) -> None:
    registry = IdentityRegistry(settings, load_or_create_token(settings.state_dir), GitCommitter())
    token, _ = registry.add("agent")

    assert _connect_token(settings, "agent") == token


def test_a_known_identity_without_a_kept_token_is_refused(settings: Settings) -> None:
    with pytest.raises(typer.Exit):
        _connect_token(settings, next(iter(settings.identities)))


@pytest.fixture
def connecting(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    project, config = tmp_path / "project", tmp_path / "config"
    project.mkdir()
    config.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    monkeypatch.setattr(cli, "_ensure_running", lambda settings: "runs")
    monkeypatch.setattr(cli, "_connect_token", lambda settings, identity: "the-token")
    return project / ".claude" / "settings.local.json", config / "settings.json"


def test_a_project_holds_the_identity_and_the_user_settings_the_plugin(connecting: tuple[Path, Path]) -> None:
    project_file, user_file = connecting

    result = CliRunner().invoke(cli.app, ["connect", "agent"])

    assert result.exit_code == 0, result.output
    assert set(json.loads(project_file.read_text())["env"]) == {"WHAAT_TOKEN", "WHAAT_INSTANCE", "WHAAT_PORT"}
    assert json.loads(user_file.read_text())["env"] == {"CLAUDE_CODE_PLUGIN_DIRS": str(CONNECTOR)}
    assert "the-token" not in result.output


def test_a_settings_file_that_is_not_json_is_left_as_it_is(connecting: tuple[Path, Path]) -> None:
    project_file, user_file = connecting
    user_file.write_text('{"hooks": {},}')

    result = CliRunner().invoke(cli.app, ["connect", "agent"])

    assert result.exit_code == 1
    assert user_file.read_text() == '{"hooks": {},}'
    assert not project_file.exists()
