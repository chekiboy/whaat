from pathlib import Path

import pytest

from whaat.config import (
    IdentityConfigError,
    Settings,
    SharedReportsConfigError,
    claude_settings_file,
    load_settings,
)


@pytest.mark.parametrize(
    ("identities", "message"),
    [
        ({"claude": Path("/x/archive"), "second": Path("/x/archive/second")}, "overlap"),
        ({"claude": Path("/x/a"), "second": Path("/x/a")}, "overlap"),
        ({"Claude!": Path("/x/a")}, "must match"),
    ],
)
def test_identities_must_have_valid_ids_and_separate_private_folders(
    identities: dict[str, Path], message: str, tmp_path: Path
) -> None:
    with pytest.raises(IdentityConfigError, match=message):
        Settings(shared_roots={}, identities=identities, state_dir=tmp_path)


def test_a_separate_claude_config_dir_is_read_instead_of_the_home_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "trial-config"
    config_dir.mkdir()
    (config_dir / "settings.json").write_text('{"env": {"WHAAT_PORT": "1199"}}', encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("WHAAT_PORT", raising=False)

    assert claude_settings_file() == config_dir / "settings.json"
    assert load_settings().port == 1199


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, ("live", 1111, "whaat.localhost", "whaat")),
        ({"WHAAT_INSTANCE": "dev"}, ("dev", 1112, "dev.whaat.localhost", "whaat-dev")),
        ({"WHAAT_INSTANCE": "dev", "WHAAT_PORT": "1111"}, ("dev", 1111, "dev.whaat.localhost", "whaat-dev")),
    ],
)
def test_an_instance_gets_its_own_port_name_and_state_dir_unless_overridden(
    env: dict[str, str], expected: tuple[str, int, str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("WHAAT_INSTANCE", "WHAAT_PORT", "WHAAT_HOSTNAME", "WHAAT_STATE_DIR"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    settings = load_settings(tmp_path / "no-settings.json")

    assert (settings.instance, settings.port, settings.hostname, settings.state_dir.name) == expected


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, {"claude": Path("/live/archive"), "wHaat": Path("state-dir/identities/wHaat")}),
        ({"WHAAT_INSTANCE": "dev"}, {"wHaat": Path("state-dir/identities/wHaat")}),
        (
            {"WHAAT_INSTANCE": "dev", "WHAAT_IDENTITIES": '{"claude": "/trial/archive"}'},
            {"claude": Path("/trial/archive"), "wHaat": Path("state-dir/identities/wHaat")},
        ),
    ],
    ids=["live", "dev", "dev-with-identities"],
)
def test_whaat_is_the_default_and_the_live_archive_stays_claudes_while_another_instance_keeps_its_data_inside(
    env: dict[str, str], expected: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("WHAAT_INSTANCE", "WHAAT_IDENTITIES", "WHAAT_DEFAULT_IDENTITY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAUDE_PRIVATE_ARCHIVE", "/live/archive")
    monkeypatch.setenv("WHAAT_STATE_DIR", str(tmp_path / "state-dir"))
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    settings = load_settings(tmp_path / "no-settings.json")

    assert settings.default_identity == "wHaat"
    assert settings.identities == {
        identity: (tmp_path / folder if not folder.is_absolute() else folder) for identity, folder in expected.items()
    }


def test_two_identities_that_differ_only_in_case_are_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHAAT_INSTANCE", "dev")
    monkeypatch.setenv("WHAAT_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("WHAAT_IDENTITIES", '{"Claude": "/a", "claude": "/b"}')
    with pytest.raises(IdentityConfigError, match="differ only in case"):
        load_settings(tmp_path / "no-settings.json")


OWN_NAMES = ("WHAAT_LIVE_IDENTITIES", "WHAAT_SHARED_REPORTS", "WHAAT_BROWSER")
OLDER_NAMES = ("CLAUDE_PRIVATE_ARCHIVE", "CLAUDE_ARTIFACTS_ROOT", "CLAUDE_FW_STATE_DIR", "CLAUDE_REPORT_BROWSER")


def settings_with(env: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in (*OWN_NAMES, *OLDER_NAMES, "WHAAT_INSTANCE", "WHAAT_IDENTITIES", "WHAAT_DEFAULT_IDENTITY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WHAAT_STATE_DIR", str(tmp_path / "state-dir"))
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return load_settings(tmp_path / "no-settings.json")


def test_live_identities_name_their_folders_on_the_live_instance_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    named = {"WHAAT_LIVE_IDENTITIES": '{"nova": "/live/nova"}'}

    live = settings_with(named, tmp_path, monkeypatch)
    dev = settings_with({**named, "WHAAT_INSTANCE": "dev"}, tmp_path, monkeypatch)

    assert live.identities.get("nova") == Path("/live/nova")
    assert "nova" not in dev.identities


def test_the_own_names_win_over_the_older_ones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_with(
        {
            "WHAAT_LIVE_IDENTITIES": '{"nova": "/live/nova"}',
            "CLAUDE_PRIVATE_ARCHIVE": "/live/archive",
            "WHAAT_SHARED_REPORTS": '{"team": {"path": "/shared/team", "dirs": ["reviews"]}}',
            "CLAUDE_ARTIFACTS_ROOT": "/older/artifacts",
            "WHAAT_BROWSER": "Firefox",
            "CLAUDE_REPORT_BROWSER": "Safari",
        },
        tmp_path,
        monkeypatch,
    )

    assert "claude" not in settings.identities
    assert settings.shared_roots == {"team": Path("/shared/team")}
    assert settings.shared_report_dirs == {"team": ("reviews",)}
    assert settings.browser == "Firefox"


def test_the_older_names_still_work_when_the_own_ones_are_not_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = settings_with(
        {
            "CLAUDE_PRIVATE_ARCHIVE": "/live/archive",
            "CLAUDE_ARTIFACTS_ROOT": "/older/artifacts",
            "CLAUDE_FW_STATE_DIR": "/older/state",
            "CLAUDE_REPORT_BROWSER": "Safari",
        },
        tmp_path,
        monkeypatch,
    )

    assert settings.identities.get("claude") == Path("/live/archive")
    assert settings.shared_roots == {"artifacts": Path("/older/artifacts"), "fw-state": Path("/older/state")}
    assert settings.shared_report_dirs == {"artifacts": ("reviews", "investigations"), "fw-state": ("memory-curation",)}
    assert settings.browser == "Safari"


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '["/shared/team"]',
        '{"team": "/shared/team"}',
        '{"team": {"path": "/shared/team"}}',
        '{"team": {"path": "/shared/team", "dirs": "reviews"}}',
        '{"Team!": {"path": "/shared/team", "dirs": ["reviews"]}}',
        '{"private-nova": {"path": "/shared/team", "dirs": ["reviews"]}}',
    ],
)
def test_shared_reports_in_another_shape_are_refused(raw: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SharedReportsConfigError):
        settings_with({"WHAAT_SHARED_REPORTS": raw}, tmp_path, monkeypatch)
