import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TOKEN, write
from whaat.config import Settings

ADMIN = {"Authorization": f"Bearer {TOKEN}"}
EVERY_AGENT = "---\nname: watch_list\nreach: every-agent\n---\nWatch.\n"


@pytest.fixture
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = write(tmp_path / "gitconfig", "[user]\n\tname = Test\n\temail = test@example.com\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def trial(client: TestClient, isolated_git: None) -> dict[str, str]:
    response = client.post("/api/v1/identities", json={"id": "trial"}, headers=ADMIN)
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def folder(settings: Settings) -> Path:
    return settings.state_dir / "identities" / "trial"


def start(client: TestClient, auth: dict[str, str], level: str, part: int, parts: int, **body: Any) -> Any:
    payload = {"level": level, "part": part, "parts": parts, "session": "abcd1234ef", "cli": "/p/whaat", **body}
    return client.post("/api/v1/memory/recall/start", json=payload, headers=auth).json()


def logged(folder: Path) -> list[dict[str, Any]]:
    path = folder / "state" / "memory-recall.log"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_project_and_repo_parts_name_the_store_and_split_the_index(
    client: TestClient, trial: dict[str, str], folder: Path
) -> None:
    memory = folder / "memory"
    write(memory / "acme/shop/MEMORY.md", "".join(f"- feedback_{i:03}.md — {'x' * 90}\n" for i in range(300)))
    key = {"key": ["acme", "shop"]}

    project = start(client, trial, "project", 1, 2, **key)
    second = start(client, trial, "project", 2, 2, **key)
    repo = [start(client, trial, "repo", n, 3, **key)["text"] for n in (1, 2, 3)]

    assert project["text"].splitlines() == [
        f"[memory] store {memory.resolve()} — global index via the global SessionStart hook;"
        " save/update/delete → whaat:memory skill",
        f"[memory] project acme dir {memory.resolve()}/acme — no memories yet",
    ]
    assert project["additional_context"] is False
    assert second["text"] is None
    assert repo[0].startswith(f"[memory] repo acme/shop dir {memory.resolve()}/acme/shop — index part 1/4:\n")
    assert all(len(text) < 10_000 for text in repo)
    shown = sum(text.count("\n- feedback_") for text in repo)
    assert repo[2].endswith(
        f"[memory] index continues beyond the hooks (line {shown + 1} on): run memory-recall index"
        ' task="<what you are doing>" path=<repo>'
    )


def test_outside_git_only_the_store_line_comes(client: TestClient, trial: dict[str, str], folder: Path) -> None:
    project = start(client, trial, "project", 1, 2)["text"]

    assert project.splitlines()[1] == "[memory] not in a git repo — no project/repo memory"
    assert start(client, trial, "repo", 1, 3)["text"] is None


def test_the_global_index_is_a_level_of_its_own(client: TestClient, trial: dict[str, str], folder: Path) -> None:
    write(folder / "memory/MEMORY.md", "- feedback_g.md — When g\n")

    assert start(client, trial, "global", 1, 2)["text"] == (
        f"[memory] global dir {(folder / 'memory').resolve()} — index part 1/1:\n- feedback_g.md — When g"
    )
    assert start(client, trial, "global", 2, 2)["text"] is None


def test_the_core_with_its_every_agent_files_is_put_in_logged_as_loaded_and_exported(
    client: TestClient, trial: dict[str, str], folder: Path
) -> None:
    core = folder / "memory/personal/core"
    write(core / "claude_self.md", "Self.\n")
    write(core / "watch_list.md", EVERY_AGENT)

    first = start(client, trial, "personal", 1, 2, source="compact")
    second = start(client, trial, "personal", 2, 2)

    assert first["additional_context"] is True
    assert first["text"] == (
        f"[memory] personal dir {(folder / 'memory/personal').resolve()}\nThe context was just compacted; your core,"
        ' read at every session start (other personal memories are listed by memory-recall index under "personal"):'
        f"\n# personal:core/claude_self.md\nSelf.\n\n# personal:core/watch_list.md\n{EVERY_AGENT.strip()}\n"
    )
    assert second["text"] is None
    assert [(e["op"], e.get("file"), e.get("because"), e.get("purpose")) for e in logged(folder)] == [
        ("compact", None, None, None),
        ("open", "personal:core/claude_self.md", "session start: core (hook)", "load"),
        ("open", "personal:core/watch_list.md", "session start: core (hook)", "load"),
    ]
    assert {e["session"] for e in logged(folder)} == {"abcd1234"}
    assert (folder / "state/subagent-core.md").read_text() == (
        "## Personal core for every agent\n(personal:core/watch_list.md)\nWatch.\n"
    )


def test_a_core_over_the_hooks_ends_with_the_open_commands(
    client: TestClient, trial: dict[str, str], folder: Path
) -> None:
    for name in ("a", "b", "c"):
        write(folder / f"memory/personal/core/{name}.md", name * 6000 + "\n")

    text = start(client, trial, "personal", 1, 1)["text"]

    assert "# personal:core/a.md" in text
    assert text.endswith(
        "[memory] core continues beyond the hooks; before your first reply, open:\n"
        '  "/p/whaat" memory open file=personal:core/b.md because="session start: core" purpose=load\n'
        '  "/p/whaat" memory open file=personal:core/c.md because="session start: core" purpose=load'
    )
    assert [e["file"] for e in logged(folder)] == ["personal:core/a.md"]


def test_a_subagent_gets_the_every_agent_files_without_their_frontmatter(
    client: TestClient, trial: dict[str, str], folder: Path
) -> None:
    core = folder / "memory/personal/core"
    write(core / "claude_self.md", "Self.\n")
    unmarked = client.get("/api/v1/memory/recall/subagent-core", headers=trial).json()
    write(core / "watch_list.md", EVERY_AGENT)

    marked = client.get("/api/v1/memory/recall/subagent-core", headers=trial).json()

    assert unmarked["text"].startswith("## Memory map\n")
    assert marked["text"] == (
        "## Personal core for every agent\n(personal:core/watch_list.md)\nWatch.\n\n" + unmarked["text"]
    )


def test_a_subagent_gets_the_global_index_the_every_agent_core_and_the_map_in_the_order_claude_md_imports_them(
    client: TestClient, trial: dict[str, str], folder: Path
) -> None:
    write(folder / "memory/MEMORY.md", "- feedback_a.md — when a\n- feedback_b.md — when b\n")
    write(folder / "memory/personal/core/watch_list.md", EVERY_AGENT)

    text = client.get("/api/v1/memory/recall/subagent-core", headers=trial).json()["text"]

    index, rest = text.split("\n\n", 1)
    assert index == "- feedback_a.md — when a\n- feedback_b.md — when b"
    core = "## Personal core for every agent\n(personal:core/watch_list.md)\nWatch.\n"
    assert rest.startswith(core + "\n## Memory map\n")


def test_the_memory_map_lists_each_indexed_dir_below_the_root_with_its_count_and_leaves_personal_out(
    client: TestClient, trial: dict[str, str], folder: Path
) -> None:
    memory = folder / "memory"
    write(memory / "MEMORY.md", "- feedback_a.md — when a\n")
    write(memory / "acme/MEMORY.md", "- project_x.md — when x\n- project_y.md — when y\n")
    write(memory / "acme/shop/MEMORY.md", "- reference_z.md — when z\n  not a row\n")
    write(memory / "acme/no-index/note.md", "no index here\n")
    write(memory / "personal/MEMORY.md", "- core/claude_self.md — who I am\n")
    write(memory / ".hidden/MEMORY.md", "- x.md — y\n")

    shown = start(client, trial, "map", 1, 1)

    assert shown["additional_context"] is False
    assert isinstance(shown["text"], str)
    assert shown["text"].splitlines()[2:] == [
        "Memory dirs below the root (memory count):",
        "- `acme` (2)",
        "- `acme/shop` (1)",
        'For a task in another repo than the current one, read its index with memory-recall index task="<what you are'
        ' doing>" repo=<dir>.',
    ]
    assert shown["text"].startswith(
        "## Memory map\nBuilt by whaat when a session or a subagent starts; there is no file to edit."
    )
    assert start(client, trial, "map", 2, 2)["text"] is None
