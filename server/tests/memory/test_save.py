import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TOKEN, write
from whaat.config import Settings

ADMIN = {"Authorization": f"Bearer {TOKEN}"}
CONTENT = "---\nname: feedback_x\ndescription: When x\ntype: feedback\n---\nDo x.\n**Why:** y.\n**How to apply:** z.\n"
PATH = "acme/shop/feedback_x.md"


@pytest.fixture
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = write(tmp_path / "gitconfig", "[user]\n\tname = Test\n\temail = test@example.com\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def trial(client: TestClient, isolated_git: None) -> dict[str, str]:
    response = client.post("/api/v1/identities", json={"id": "trial"}, headers=ADMIN)
    return {"Authorization": f"Bearer {response.json()['token']}"}


def root(settings: Settings) -> Path:
    return settings.state_dir / "identities" / "trial" / "memory"


def git(settings: Settings, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root(settings).parent), *args], capture_output=True, text=True, check=True
    ).stdout


def save(client: TestClient, auth: dict[str, str], **memory: Any) -> Any:
    return client.post(
        "/api/v1/memory/memories", json={"path": PATH, "content": CONTENT, "trigger": "When x", **memory}, headers=auth
    )


def test_the_file_and_its_index_line_are_written_as_given_and_committed_alone(
    client: TestClient, settings: Settings, trial: dict[str, str]
) -> None:
    write(root(settings) / "acme/shop/MEMORY.md", "- feedback_a.md — When a\n- feedback_b.md — When b")

    saved = save(client, trial).json()

    assert (saved["path"], saved["created"], saved["warnings"]) == (PATH, True, [])
    assert (root(settings) / PATH).read_bytes() == CONTENT.encode()
    assert (root(settings) / "acme/shop/MEMORY.md").read_text() == (
        "- feedback_a.md — When a\n- feedback_b.md — When b\n- feedback_x.md — When x\n"
    )
    assert git(settings, "show", "--name-only", "--format=%s", "HEAD").split() == [
        "memory:",
        "add",
        PATH,
        "memory/acme/shop/MEMORY.md",
        "memory/acme/shop/feedback_x.md",
    ]
    assert git(settings, "status", "--porcelain") == ""


def test_a_second_save_replaces_the_line_in_place_and_is_an_update(
    client: TestClient, settings: Settings, trial: dict[str, str]
) -> None:
    write(root(settings) / "acme/shop/MEMORY.md", "- feedback_x.md — old\n- feedback_b.md — When b\n")

    updated = save(client, trial, trigger="When x, sharper").json()

    assert updated["created"] is True
    assert (root(settings) / "acme/shop/MEMORY.md").read_text() == (
        "- feedback_x.md — When x, sharper\n- feedback_b.md — When b\n"
    )
    assert save(client, trial).json()["created"] is False
    assert git(settings, "log", "-1", "--format=%s") == f"memory: update {PATH}\n"


def test_a_core_file_is_listed_as_core_in_the_personal_index(
    client: TestClient, settings: Settings, trial: dict[str, str]
) -> None:
    save(client, trial, path="personal/core/claude_self.md", trigger="Who I am")

    assert (root(settings) / "personal/MEMORY.md").read_text() == "- core/claude_self.md — Who I am\n"
    assert not (root(settings) / "personal/core/MEMORY.md").exists()


def test_a_superseding_save_drops_the_old_index_line_keeps_its_file_and_commits_once(
    client: TestClient, settings: Settings, trial: dict[str, str]
) -> None:
    save(client, trial)
    before = git(settings, "rev-list", "--count", "HEAD")

    save(client, trial, path="acme/shop/feedback_x2.md", trigger="When x, now", unindex=[PATH])

    assert (root(settings) / "acme/shop/MEMORY.md").read_text() == "- feedback_x2.md — When x, now\n"
    assert (root(settings) / PATH).exists()
    assert int(git(settings, "rev-list", "--count", "HEAD")) == int(before) + 1


def test_a_delete_removes_the_file_and_its_line_in_one_commit(
    client: TestClient, settings: Settings, trial: dict[str, str]
) -> None:
    save(client, trial)

    deleted = client.delete(f"/api/v1/memory/memories/{PATH}", headers=trial).json()

    assert not (root(settings) / PATH).exists()
    assert (root(settings) / "acme/shop/MEMORY.md").read_text() == ""
    assert git(settings, "log", "-1", "--format=%s") == f"memory: delete {PATH}\n"
    assert deleted["commit"] and git(settings, "status", "--porcelain") == ""


@pytest.mark.parametrize(
    "memory",
    [
        {"path": "../outside.md"},
        {"path": "acme/shop/MEMORY.md"},
        {"path": "acme/shop/feedback_x.txt"},
        {"trigger": "two\nlines"},
        {"unindex": ["../../journal/x.md"]},
    ],
    ids=["outside", "an-index", "not-md", "multiline-trigger", "unindex-outside"],
)
def test_a_path_or_trigger_that_is_not_a_memory_is_refused(
    client: TestClient, trial: dict[str, str], memory: dict[str, Any]
) -> None:
    assert save(client, trial, **memory).status_code == 422


def test_only_an_identity_token_saves(client: TestClient, trial: dict[str, str]) -> None:
    assert save(client, ADMIN).status_code == 403


def test_a_delete_out_of_the_memory_root_is_refused(
    client: TestClient, settings: Settings, trial: dict[str, str]
) -> None:
    write(root(settings).parent / "outside.md", "not a memory")

    assert client.delete("/api/v1/memory/memories/%2E%2E/outside.md", headers=trial).status_code == 422
    assert (root(settings).parent / "outside.md").exists()


def test_where_names_the_roots_and_an_absolute_path_inside_them_saves(
    client: TestClient, settings: Settings, trial: dict[str, str]
) -> None:
    roots = client.get("/api/v1/memory/where", headers=trial).json()

    saved = save(client, trial, path=f"{roots['memory']}/acme/shop/feedback_x.md").json()

    assert roots == {
        "memory": str(root(settings)),
        "personal": str(root(settings) / "personal"),
        "state": str(root(settings).parent / "state"),
    }
    assert saved["path"] == PATH


def test_browse_shows_each_layer_marks_history_and_follows_the_token(
    client: TestClient, settings: Settings, trial: dict[str, str]
) -> None:
    save(client, trial)
    save(client, trial, path="acme/shop/feedback_x2.md", trigger="When x, now", unindex=[PATH])
    save(client, trial, path="personal/core/claude_self.md", trigger="Who I am")

    mine = client.get("/api/v1/memory/browse", headers=trial).json()
    everyone = client.get("/api/v1/memory/browse", headers=ADMIN).json()

    assert [i["identity"] for i in mine] == ["trial"]
    assert {i["identity"] for i in everyone} >= {"claude", "second", "trial"}
    layers = {(layer["layer"], m["path"]): m for layer in mine[0]["layers"] for m in layer["memories"]}
    assert {key: m["indexed"] for key, m in layers.items()} == {
        ("repo", "acme/shop/feedback_x.md"): False,
        ("repo", "acme/shop/feedback_x2.md"): True,
        ("core", "personal/core/claude_self.md"): True,
    }
    assert layers[("repo", "acme/shop/feedback_x2.md")]["frontmatter"]["type"] == "feedback"
    assert layers[("repo", "acme/shop/feedback_x2.md")]["body"].startswith("Do x.")


def test_browse_carries_each_store_memorys_score_and_none_for_a_personal_one(
    client: TestClient, settings: Settings, trial: dict[str, str]
) -> None:
    save(client, trial)
    write(root(settings) / "personal/user_y.md", "---\nname: user_y\nconfirmed: 2020-01-01\n---\nY.\n")

    memory = client.get("/api/v1/memory/browse", headers=trial).json()[0]
    cards = {card["path"]: card for layer in memory["layers"] for card in layer["memories"]}

    assert cards[PATH]["validity"] == {
        "level": "certain",
        "score": 0.9,
        "age_days": 0,
        "history": None,
        "source": None,
        "outcomes": {},
    }
    assert cards["personal/user_y.md"]["validity"] is None
