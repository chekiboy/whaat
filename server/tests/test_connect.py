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
from whaat.terminal.agent import (
    CONNECTOR,
    RECALL_RULE,
    ClaudeMdUnusableError,
    add_connector,
    add_recall_rule,
    check_claude_md,
    launch_for,
    with_connector,
)


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
    assert (user_file.parent / "CLAUDE.md").read_text() == RECALL_RULE
    assert "the-token" not in result.output


def test_the_recall_rule_heads_a_users_claude_md_once_and_keeps_the_rest(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# Mine\nKeep this.\n")
    add_recall_rule(claude_md)
    once = claude_md.read_text()
    claude_md.write_text("# Mine\n" + once.replace("Before every reply", "An older rule").replace("# Mine\n", "", 1))
    add_recall_rule(claude_md)
    add_recall_rule(claude_md)

    assert once.startswith("<memory_handling>\n")
    assert once == RECALL_RULE + "\n# Mine\nKeep this.\n"
    assert claude_md.read_text().count("<memory_handling>") == 1
    assert claude_md.read_text().startswith(RECALL_RULE)
    assert "An older rule" not in claude_md.read_text()
    assert "# Mine\n" in claude_md.read_text() and "Keep this.\n" in claude_md.read_text()


def test_a_settings_file_that_is_not_json_is_left_as_it_is(connecting: tuple[Path, Path]) -> None:
    project_file, user_file = connecting
    user_file.write_text('{"hooks": {},}')

    result = CliRunner().invoke(cli.app, ["connect", "agent"])

    assert result.exit_code == 1
    assert user_file.read_text() == '{"hooks": {},}'
    assert not project_file.exists()


def test_a_users_own_memory_handling_block_stays(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("<memory_handling>\nMy own rule: never store secrets.\n</memory_handling>\n")

    add_recall_rule(claude_md)
    add_recall_rule(claude_md)

    text = claude_md.read_text()
    assert text.startswith(RECALL_RULE)
    assert text.count("whaat:memory-recall") == 1
    assert "My own rule: never store secrets." in text


def test_a_claude_md_that_is_not_utf8_stops_connect_before_any_write(connecting: tuple[Path, Path]) -> None:
    project_file, user_file = connecting
    (user_file.parent / "CLAUDE.md").write_bytes(b"\xff\xfe not utf-8")

    result = CliRunner().invoke(cli.app, ["connect", "agent"])

    assert result.exit_code == 1
    assert "cannot be read as UTF-8 text" in result.output
    assert not project_file.exists()
    assert not user_file.exists()


def test_a_claude_md_linked_into_a_folder_that_cannot_be_written_is_refused(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "CLAUDE.md").write_text("# Mine\n")
    link = tmp_path / "CLAUDE.md"
    link.symlink_to(locked / "CLAUDE.md")
    locked.chmod(0o555)
    try:
        with pytest.raises(ClaudeMdUnusableError, match="its folder is not writable"):
            check_claude_md(link)
    finally:
        locked.chmod(0o755)


def test_a_terminal_start_skips_a_claude_md_it_cannot_write(tmp_path: Path, settings: Settings) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "CLAUDE.md").write_bytes(b"\xff not utf-8")

    launch = launch_for("agent", str(config), "claude", settings, lambda identity: "the-token")

    assert launch is not None
    assert (config / "CLAUDE.md").read_bytes() == b"\xff not utf-8"
    assert (config / "settings.json").exists()


def test_a_read_only_claude_md_in_a_writable_folder_is_refused(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# Mine\n")
    claude_md.chmod(0o444)
    try:
        with pytest.raises(ClaudeMdUnusableError, match="is not writable"):
            check_claude_md(claude_md)
    finally:
        claude_md.chmod(0o644)
