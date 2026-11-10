import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TOKEN, write
from whaat.config import Settings

ADMIN = {"Authorization": f"Bearer {TOKEN}"}


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
def memory(settings: Settings) -> Path:
    root = settings.state_dir / "identities" / "trial" / "memory"
    write(root / "MEMORY.md", "- feedback_g.md — When g\n")
    write(root / "feedback_g.md", "G.\n")
    write(root / "acme/shop/MEMORY.md", "- [feedback_r.md](feedback_r.md) — When r\n")
    write(root / "acme/shop/feedback_r.md", "R.\n")
    write(root / "personal/MEMORY.md", "- core/claude_self.md — Who I am\n- user_x.md — When x\n")
    write(root / "personal/core/claude_self.md", "Self.\n")
    write(root / "personal/user_x.md", "X.\n")
    write(root.parent / "journal/outside.md", "Not a memory.\n")
    return root


def call(client: TestClient, auth: dict[str, str], op: str, **body: Any) -> Any:
    return client.post(f"/api/v1/memory/recall/{op}", json={"session": "abcd1234", **body}, headers=auth)


def logged(settings: Settings) -> list[dict[str, Any]]:
    text = (settings.state_dir / "identities" / "trial" / "state" / "memory-recall.log").read_text()
    return [json.loads(line) for line in text.splitlines()]


def test_index_lists_each_layer_with_its_prefix_and_logs_the_task(
    client: TestClient, settings: Settings, trial: dict[str, str], memory: Path
) -> None:
    found = call(client, trial, "index", task="review the shop", cwd="/x/shop", key=["acme", "shop"]).json()

    assert found["store"] == str(memory.resolve())
    assert [(s["label"], s["prefix"], s["entries"]) for s in found["sections"]] == [
        ("global", "", [{"file": "feedback_g.md", "trigger": "When g"}]),
        ("project", "acme/", None),
        ("repo", "acme/shop/", [{"file": "acme/shop/feedback_r.md", "trigger": "When r"}]),
        (
            "personal",
            "personal:",
            [
                {"file": "personal:core/claude_self.md", "trigger": "Who I am"},
                {"file": "personal:user_x.md", "trigger": "When x"},
            ],
        ),
    ]
    [line] = logged(settings)
    assert {k: v for k, v in line.items() if k != "at"} == {
        "session": "abcd1234",
        "op": "index",
        "task": "review the shop",
        "cwd": "/x/shop",
        "repo": None,
    }


def test_index_needs_a_task_and_a_repo_that_is_a_store_dir(
    client: TestClient, trial: dict[str, str], memory: Path
) -> None:
    short = call(client, trial, "index", task="x", cwd="/x")
    personal = call(client, trial, "index", task="review the shop", cwd="/x", repo="personal")
    project = call(client, trial, "index", task="review the shop", cwd="/x", repo="acme").json()

    assert short.status_code == 422
    assert "task=" in short.json()["detail"]
    assert personal.status_code == 422
    assert "repo='personal' is no memory dir" in personal.json()["detail"]
    assert [s["label"] for s in project["sections"]] == ["global", "project", "personal"]


def test_a_recall_open_returns_no_text_and_logs_the_trigger_and_why(
    client: TestClient, settings: Settings, trial: dict[str, str], memory: Path
) -> None:
    opened = call(client, trial, "open", file="personal:core/claude_self.md", because="session start: core").json()

    assert opened == {
        "file": "personal:core/claude_self.md",
        "path": str((memory / "personal/core/claude_self.md").resolve()),
        "trigger": "- core/claude_self.md — Who I am",
        "purpose": "recall",
        "text": None,
    }
    [line] = logged(settings)
    assert {k: v for k, v in line.items() if k != "at"} == {
        "session": "abcd1234",
        "op": "open",
        "file": "personal:core/claude_self.md",
        "trigger": "- core/claude_self.md — Who I am",
        "because": "session start: core",
        "purpose": "recall",
    }


def test_a_read_that_is_no_recall_returns_the_text(client: TestClient, trial: dict[str, str], memory: Path) -> None:
    opened = call(client, trial, "open", file="acme/shop/feedback_r.md", because="updating r", purpose="save").json()

    assert (opened["trigger"], opened["text"]) == ("- [feedback_r.md](feedback_r.md) — When r", "R.\n")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"file": "personal/core/claude_self.md", "because": "who I am now"}, "is not a memory in the store"),
        ({"file": "../journal/outside.md", "because": "who I am now"}, "is not a memory in the store"),
        ({"file": "feedback_g.md", "because": "short"}, 'because="<which words'),
        ({"file": "feedback_g.md", "because": "when g holds", "purpose": ""}, "purpose must be one of"),
    ],
)
def test_open_refuses_what_memory_recall_refuses(
    client: TestClient, settings: Settings, trial: dict[str, str], memory: Path, body: dict[str, str], message: str
) -> None:
    refused = call(client, trial, "open", **body)

    assert refused.status_code == 422
    assert message in refused.json()["detail"]
    assert not (settings.state_dir / "identities" / "trial" / "state" / "memory-recall.log").exists()


def test_dump_needs_a_purpose_and_logs_every_file(
    client: TestClient, settings: Settings, trial: dict[str, str], memory: Path
) -> None:
    missing = call(client, trial, "dump", dir="personal:", because="weekly curation")
    dumped = call(client, trial, "dump", dir="personal:", because="weekly curation", purpose="curate").json()

    assert "purpose=curate|review|save is required" in missing.json()["detail"]
    files = ["personal:MEMORY.md", "personal:user_x.md"]
    assert [f["file"] for f in dumped["files"]] == files
    [line] = logged(settings)
    assert (line["op"], line["dir"], line["files"], line["purpose"]) == ("dump", "personal:.", files, "curate")


def frame(client: TestClient, auth: dict[str, str], memory: Path, rel: str, **body: Any) -> Any:
    path = str((memory / rel.replace("personal:", "personal/")).resolve())
    opened = [{"file": rel, "path": path}]
    return client.post(
        "/api/v1/memory/recall/frame", json={"session": "abcd1234", "opened": opened, **body}, headers=auth
    )


def test_frame_puts_a_memory_in_once_per_agent_unless_forced(
    client: TestClient, settings: Settings, trial: dict[str, str], memory: Path
) -> None:
    first = frame(client, trial, memory, "feedback_g.md").json()["context"]
    again = frame(client, trial, memory, "feedback_g.md").json()["context"]
    forced = frame(client, trial, memory, "feedback_g.md", force=True).json()["context"]
    subagent = frame(client, trial, memory, "feedback_g.md", agent="a1").json()["context"]

    assert first == (
        "Memory: feedback_g.md\nTruthness: source unset; since its last change held 0, misled 0, irrelevant 0\n"
        "Validity: undated (no confirmed date, held outcome or commit)\n\nG.\n"
    )
    assert again.startswith("[memory] feedback_g.md is already in your context (put in at ")
    assert forced == subagent == first
    assert [(e["op"], e["agent"], e["file"]) for e in logged(settings)] == [
        ("inject", "", "feedback_g.md"),
        ("inject", "", "feedback_g.md"),
        ("inject", "a1", "feedback_g.md"),
    ]


def test_the_core_load_counts_for_the_main_agent_until_a_compaction(
    client: TestClient, settings: Settings, trial: dict[str, str], memory: Path
) -> None:
    log = settings.state_dir / "identities" / "trial" / "state" / "memory-recall.log"
    core = {"at": "2026-11-02T09:00:00", "session": "abcd1234", "op": "open", "file": "personal:core/claude_self.md"}
    write(log, json.dumps({**core, "because": "session start: core (hook)", "purpose": "load"}) + "\n")

    loaded = frame(client, trial, memory, "personal:core/claude_self.md").json()["context"]
    with log.open("a") as handle:
        handle.write(json.dumps({"at": "2026-11-02T10:00:00", "session": "abcd1234", "op": "compact"}) + "\n")
    after_compaction = frame(client, trial, memory, "personal:core/claude_self.md").json()["context"]

    assert "already in your context (put in at 09:00)" in loaded
    assert after_compaction == (
        "Memory: personal:core/claude_self.md\nTruthness: source unset\n"
        "Validity: not scored (personal memory)\n\nSelf.\n"
    )


def test_frame_says_nothing_about_a_file_outside_the_memory(
    client: TestClient, trial: dict[str, str], memory: Path
) -> None:
    outside = str(memory.parent / "journal/outside.md")
    body = {"session": "abcd1234", "opened": [{"file": "x.md", "path": outside}]}

    assert client.post("/api/v1/memory/recall/frame", json=body, headers=trial).json() == {"context": None}


def guard(client: TestClient, auth: dict[str, str], *paths: Path, must_exist: bool = True) -> Any:
    body = {"session": "abcd1234", "paths": [str(p) for p in paths], "must_exist": must_exist}
    return client.post("/api/v1/memory/recall/guard", json=body, headers=auth).json()["file"]


def test_guard_names_the_first_memory_not_opened_this_session(
    client: TestClient, trial: dict[str, str], memory: Path
) -> None:
    other = memory.parent / "journal/outside.md"
    personal = memory / "personal/user_x.md"
    missing = memory / "acme/shop/feedback_new.md"

    assert guard(client, trial, other, personal) == "personal:user_x.md"
    assert guard(client, trial, missing) is None
    assert guard(client, trial, missing, must_exist=False) == "acme/shop/feedback_new.md"
    call(client, trial, "open", file="personal:user_x.md", because="when x holds now")
    call(client, trial, "dump", dir=".", because="weekly curation", purpose="curate")
    assert guard(client, trial, personal, memory / "feedback_g.md", memory / "MEMORY.md") is None
    assert guard(client, trial, memory / "acme/shop/feedback_r.md") == "acme/shop/feedback_r.md"
