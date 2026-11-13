import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from whaat.config import Settings
from whaat.main import create_app

TOKEN = "test-token"
CLAUDE_TOKEN = "claude-test-token"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    artifacts = tmp_path / "artifacts"
    fw_state = tmp_path / "fw-state"
    claude = tmp_path / "claude-archive"
    second = tmp_path / "second-archive"
    write(
        artifacts / "reviews/acme/shop/ABC-101/20261028-remove-metrics.md",
        "# Review: ABC-101\n\n## Context pin\n\n- Repository: shop\n\n## Verdict: Approve\n\nShip it.\n",
    )
    write(artifacts / "reviews/acme/shop/ABC-102/20261027-v2-development.md", "# Development: ABC-102\n")
    write(fw_state / "memory-curation/2026-10-26.md", "# Memory curation — 2026-10-26\n\n27 rows.\n")
    write(fw_state / "memory-curation/2026-10-26.sent.jsonl", "{}\n")
    write(
        claude / "session-reports/2026-10-28_session-report_4c2f638a_abc-102-and-skills.md",
        "# Session — ABC-102\n\n- Type: session report\n- Repo: acme/tools (main)\n",
    )
    write(
        claude / "journal/2026-10-29_38e0994a.md",
        "# 2026-10-29 · session 38e0994a\n\n## 08:26\n- Reviewed three MRs.\n",
    )
    write(claude / ".private", "")
    write(second / "journal/2026-10-29_5011e7aa.md", "# 2026-10-29 · session 5011e7aa\n\n## 09:00\n- First day.\n")
    write(second / ".private", "")
    write(tmp_path / "state/tokens/claude", hashlib.sha256(CLAUDE_TOKEN.encode()).hexdigest())
    return Settings(
        shared_roots={"artifacts": artifacts, "fw-state": fw_state},
        identities={"claude": claude, "second": second},
        state_dir=tmp_path / "state",
        default_identity="claude",
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings, TOKEN))


@pytest.fixture(autouse=True)
def no_machine_identities(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never read this machine's live identities; a test that wants them sets WHAAT_LIVE_IDENTITIES itself."""
    monkeypatch.delenv("WHAAT_LIVE_IDENTITIES", raising=False)


@pytest.fixture(autouse=True)
def no_machine_themes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Tests never read this machine's terminal apps; a test that wants themes sets the readers itself."""
    from whaat.terminal import themes

    monkeypatch.setattr(themes, "READERS", [])
    monkeypatch.setattr(themes, "TERMINAL_APP", tmp_path / "no-terminal.plist")
    monkeypatch.setattr(themes.default_theme_id, "__defaults__", (tmp_path / "no-terminal.plist",))
