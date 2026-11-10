import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import CLAUDE_TOKEN, TOKEN
from whaat.config import REPO_UI_DIR
from whaat.ui_build import UiBuild, build_ui

ADMIN = {"Authorization": f"Bearer {TOKEN}"}


def test_only_the_admin_restarts_the_server_and_health_says_when_it_started(client: TestClient) -> None:
    calls: list[int] = []
    client.app.state.restart = lambda: calls.append(1)  # type: ignore[attr-defined]
    client.app.state.build_ui = lambda: UiBuild(built=True)  # type: ignore[attr-defined]
    assert client.post("/api/v1/health/restart").status_code == 401
    assert client.post("/api/v1/health/restart", headers={"Authorization": f"Bearer {CLAUDE_TOKEN}"}).status_code == 403
    assert calls == []
    answer = client.post("/api/v1/health/restart", headers=ADMIN)
    assert answer.status_code == 202
    assert answer.json() == {"ui_built": True}
    assert calls == [1]
    assert isinstance(client.get("/api/v1/health").json()["started"], int)


def test_only_the_admin_stops_the_server(client: TestClient) -> None:
    calls: list[int] = []
    client.app.state.stop = lambda: calls.append(1)  # type: ignore[attr-defined]
    assert client.post("/api/v1/health/stop").status_code == 401
    assert client.post("/api/v1/health/stop", headers={"Authorization": f"Bearer {CLAUDE_TOKEN}"}).status_code == 403
    assert calls == []
    assert client.post("/api/v1/health/stop", headers=ADMIN).status_code == 202
    assert calls == [1]


def test_a_failed_ui_build_keeps_the_server_running_and_answers_with_the_build_output(client: TestClient) -> None:
    calls: list[int] = []
    client.app.state.restart = lambda: calls.append(1)  # type: ignore[attr-defined]
    client.app.state.build_ui = lambda: UiBuild(built=False, error="src/x.ts(1,1): error TS2322")  # type: ignore[attr-defined]
    answer = client.post("/api/v1/health/restart", headers=ADMIN)
    assert answer.status_code == 409
    assert answer.json()["detail"] == "src/x.ts(1,1): error TS2322"
    assert calls == []


def _runner(returncode: int, seen: list[tuple[list[str], Path]]):
    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        seen.append((command, cwd))
        return subprocess.CompletedProcess(command, returncode, stdout="vite\n" * 30 + "last line", stderr="")

    return run


def test_the_checkouts_ui_is_built_with_pnpm_in_its_own_folder() -> None:
    seen: list[tuple[list[str], Path]] = []
    assert build_ui(REPO_UI_DIR, _runner(0, seen), pnpm="/bin/pnpm") == UiBuild(built=True)
    assert seen == [(["/bin/pnpm", "build"], REPO_UI_DIR.parent)]


def test_a_ui_from_another_folder_is_served_as_it_is(tmp_path: Path) -> None:
    seen: list[tuple[list[str], Path]] = []
    assert build_ui(tmp_path / "dist", _runner(0, seen), pnpm="/bin/pnpm") == UiBuild(built=False)
    assert build_ui(None, _runner(0, seen), pnpm="/bin/pnpm") == UiBuild(built=False)
    assert seen == []


def test_a_failed_build_reports_the_end_of_its_output() -> None:
    build = build_ui(REPO_UI_DIR, _runner(1, []), pnpm="/bin/pnpm")
    assert build.built is False
    assert build.error is not None
    assert build.error.endswith("last line")
    assert len(build.error.splitlines()) == 20


def test_pnpm_is_found_where_it_is_installed_when_the_path_lacks_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from whaat import ui_build

    pnpm = tmp_path / "pnpm"
    pnpm.write_text("#!/bin/sh\n")
    pnpm.chmod(0o755)
    monkeypatch.setattr(ui_build.shutil, "which", lambda name: None)
    monkeypatch.setattr(ui_build, "PNPM_DIRS", ("/no/such/dir", str(tmp_path)))

    assert ui_build.find_pnpm() == str(pnpm)


def test_the_build_runs_with_pnpms_folder_first_on_the_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from whaat import ui_build

    pnpm = tmp_path / "bin" / "pnpm"
    pnpm.parent.mkdir()
    pnpm.write_text('#!/bin/sh\necho "$PATH"\n')
    pnpm.chmod(0o755)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    result = ui_build._run([str(pnpm), "build"], tmp_path)

    assert result.stdout.strip().split(":")[0] == str(pnpm.parent)
