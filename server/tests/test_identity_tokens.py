import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from tests.conftest import CLAUDE_TOKEN, TOKEN
from tests.journal.samples import BLOCK
from whaat.cli import main as cli
from whaat.config import Settings

ADMIN = {"Authorization": f"Bearer {TOKEN}"}
CLAUDE = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
ENTRY = {"session": "9007036a", "entry_date": "2026-10-30", "block": BLOCK}
SKELETON = [
    ".gitignore",
    "distilled/.private",
    "journal/.private",
    "memory/personal/.private",
    "session-reports/.private",
]


def add(client: TestClient, identity: str) -> dict[str, str]:
    response = client.post("/api/v1/identities", json={"id": identity}, headers=ADMIN)
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def files(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and ".git" not in p.parts)


def test_an_identity_added_while_the_server_runs_writes_only_into_its_own_folder(
    client: TestClient, settings: Settings
) -> None:
    claude_before = files(settings.identities["claude"])
    trial = add(client, "trial")

    saved = client.post("/api/v1/journal/entries", json=ENTRY, headers=trial).json()

    trial_folder = settings.state_dir / "identities" / "trial"
    assert (saved["report_id"], saved["envelope"]["identity"]) == (
        "private-trial:journal/2026/10/2026-10-30_9007036a.json",
        "trial",
    )
    assert files(trial_folder) == sorted([*SKELETON, "journal/2026/10/2026-10-30_9007036a.json"])
    assert files(settings.identities["claude"]) == claude_before


def test_a_new_identity_marks_only_what_is_never_shared_commits_it_and_gets_its_token_only_once(
    client: TestClient, settings: Settings
) -> None:
    created = client.post("/api/v1/identities", json={"id": "trial"}, headers=ADMIN).json()

    folder = Path(created["folder"])
    tracked = subprocess.run(["git", "-C", str(folder), "ls-files"], capture_output=True, text=True, check=True)
    assert files(folder) == SKELETON
    assert sorted(tracked.stdout.split()) == SKELETON
    assert (folder / ".gitignore").read_text() == "state/\n"
    assert created["token"] not in (settings.state_dir / "tokens" / "trial").read_text()
    assert client.post("/api/v1/identities", json={"id": "trial"}, headers=ADMIN).status_code == 409


def test_a_new_identitys_token_is_kept_owner_only_in_the_state_folder_outside_its_git_folder(
    client: TestClient, settings: Settings
) -> None:
    created = client.post("/api/v1/identities", json={"id": "trial"}, headers=ADMIN).json()

    kept = settings.state_dir / "identity-secrets" / "trial"
    assert kept.is_file()
    assert kept.read_text() == created["token"]
    assert kept.stat().st_mode & 0o777 == 0o600
    assert kept.parent.stat().st_mode & 0o777 == 0o700
    assert client.app.state.registry.stored_token("trial") == created["token"]  # type: ignore[attr-defined]
    assert client.app.state.registry.stored_token("claude") is None  # type: ignore[attr-defined]
    assert not kept.is_relative_to(Path(created["folder"]))
    me = client.get("/api/v1/identities", headers={"Authorization": f"Bearer {kept.read_text()}"})
    assert [i["id"] for i in me.json()] == ["trial"]


def test_an_identity_that_differs_from_a_known_one_only_in_case_is_refused_and_capitals_are_allowed(
    client: TestClient, settings: Settings
) -> None:
    tokens = settings.state_dir / "tokens"
    before = (tokens / "claude").read_text()
    clash = client.post("/api/v1/identities", json={"id": "Claude"}, headers=ADMIN)
    assert clash.status_code == 409
    assert "already exists as 'claude'" in clash.json()["detail"]
    assert sorted(path.name for path in tokens.iterdir()) == ["claude"]
    assert (tokens / "claude").read_text() == before
    assert client.post("/api/v1/identities", json={"id": "wHaat"}, headers=ADMIN).status_code == 201
    assert client.post("/api/v1/identities", json={"id": "WHAAT"}, headers=ADMIN).status_code == 409


@pytest.mark.parametrize(
    ("body", "headers", "status"),
    [
        ({"id": "other"}, CLAUDE, 403),
        ({"id": "Trial!"}, ADMIN, 422),
        ({"id": "other"}, {"Authorization": "Bearer wrong"}, 401),
    ],
    ids=["identity-token", "invalid-id", "wrong-token"],
)
def test_only_the_admin_adds_identities(
    client: TestClient, body: dict[str, str], headers: dict[str, str], status: int
) -> None:
    assert client.post("/api/v1/identities", json=body, headers=headers).status_code == status


@pytest.mark.parametrize(
    ("headers", "status"),
    [(ADMIN, 403), ({"Authorization": "Bearer wrong"}, 401), ({}, 401)],
    ids=["admin", "wrong", "none"],
)
def test_only_an_identity_token_writes_the_journal(client: TestClient, headers: dict[str, str], status: int) -> None:
    assert client.post("/api/v1/journal/entries", json=ENTRY, headers=headers).status_code == status


def test_an_identity_sees_only_its_own_reports_and_itself(client: TestClient) -> None:
    trial = add(client, "trial")
    client.post("/api/v1/journal/entries", json=ENTRY, headers=trial)

    reports = client.get("/api/v1/reports", headers=trial).json()
    claude_report = client.get("/api/v1/reports", headers=CLAUDE).json()[0]["id"]
    identities = client.get("/api/v1/identities", headers=trial).json()

    assert [report["id"] for report in reports] == ["private-trial:journal/2026/10/2026-10-30_9007036a.json"]
    assert client.get(f"/api/v1/reports/{claude_report}", headers=trial).status_code == 404
    assert [identity["id"] for identity in identities] == ["trial"]
    assert len(client.get("/api/v1/reports", headers=ADMIN).json()) > len(reports)


def test_the_cli_sends_nothing_without_an_identity_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("WHAAT_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    sent: list[object] = []
    monkeypatch.setattr(cli, "_post_to_whaat", lambda *args: sent.append(args))

    result = CliRunner().invoke(cli.app, ["journal", "save", "--session", "9007036a"], input="{}")

    assert (result.exit_code, sent) == (1, [])
    assert "WHAAT_TOKEN" in result.output


def test_a_regenerated_token_replaces_the_old_one_at_once_and_is_kept(client: TestClient, settings: Settings) -> None:
    old = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
    assert client.post("/api/v1/identities/claude/token", headers=old).status_code == 403

    answer = client.post("/api/v1/identities/claude/token", headers=ADMIN)

    assert answer.status_code == 200
    new = answer.json()["token"]
    assert new != CLAUDE_TOKEN
    assert client.get("/api/v1/identities", headers=old).status_code == 401
    me = client.get("/api/v1/identities", headers={"Authorization": f"Bearer {new}"})
    assert [i["id"] for i in me.json()] == ["claude"]
    assert (settings.state_dir / "identity-secrets" / "claude").read_text() == new
    assert (settings.state_dir / "tokens" / "claude").stat().st_mode & 0o777 == 0o600


def test_only_a_token_on_disk_under_its_exact_name_is_regenerated(client: TestClient, settings: Settings) -> None:
    before = (settings.state_dir / "tokens" / "claude").read_text()
    assert client.post("/api/v1/identities/Claude/token", headers=ADMIN).status_code == 404
    assert client.post("/api/v1/identities/second/token", headers=ADMIN).status_code == 404
    assert (settings.state_dir / "tokens" / "claude").read_text() == before
    assert client.get("/api/v1/identities", headers={"Authorization": f"Bearer {CLAUDE_TOKEN}"}).status_code == 200
