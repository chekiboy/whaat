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
    assert found["unchanged_since"] is None
    [line] = logged(settings)
    assert {k: v for k, v in line.items() if k != "at"} == {
        "session": "abcd1234",
        "op": "index",
        "task": "review the shop",
        "cwd": "/x/shop",
        "repo": None,
        "digest": found["digest"],
        "part": 1,
        "parts": 1,
        "unchanged": False,
    }
    assert (found["part"], found["parts"]) == (1, 1)


def test_a_long_index_comes_in_parts_and_counts_as_known_only_once_every_part_was_read(
    client: TestClient, settings: Settings, trial: dict[str, str], memory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from whaat.memory import recall

    write(memory / "MEMORY.md", "".join(f"- feedback_g{n}.md — When g{n} happens\n" for n in range(6)))
    monkeypatch.setattr(recall, "PART_BUDGET", 80)
    first = call(client, trial, "index", task="review the shop", cwd="/x").json()
    digest, parts = first["digest"], first["parts"]
    early = call(client, trial, "index", task="review the shop", cwd="/x", known=digest).json()
    skipped = call(client, trial, "index", task="review the shop", cwd="/x", part=parts).json()
    rest = [call(client, trial, "index", task="review the shop", cwd="/x", part=n).json() for n in range(2, parts + 1)]
    known = call(client, trial, "index", task="review the shop", cwd="/x", known=digest, part=2).json()
    beyond = call(client, trial, "index", task="review the shop", cwd="/x", part=parts + 1)

    files = [e["file"] for page in [first, *rest] for s in page["sections"] if s["entries"] for e in s["entries"]]
    assert parts > 2
    assert {page["digest"] for page in [first, *rest]} == {digest}
    assert files == [f"feedback_g{n}.md" for n in range(6)] + ["personal:core/claude_self.md", "personal:user_x.md"]
    assert early["sections"] is not None
    assert first["text"].startswith(f"store {memory.resolve()}\nindex {digest} part 1/{parts} ")
    assert "Open a memory only through: whaat memory open" in first["text"]
    assert first["footer"] == f"Part 1 of {parts}: run index again with part=2 for the next part.\n"
    assert skipped["footer"].startswith("Not complete yet: this session has not read part 2,")
    assert rest[-1]["footer"] == f"That was the last part ({parts} of {parts}).\n"
    assert f"index {digest} unchanged since " in known["text"] and f"({parts} parts)" in known["text"]
    assert skipped["missing"] == list(range(2, parts))
    assert rest[-1]["missing"] == []
    assert known["sections"] is None
    assert beyond.status_code == 422
    assert "out of range" in beyond.json()["detail"]


def test_a_known_index_comes_back_as_unchanged_only_in_the_session_that_got_it_and_until_a_compaction(
    client: TestClient, settings: Settings, trial: dict[str, str], memory: Path
) -> None:
    first = call(client, trial, "index", task="review the shop", cwd="/x").json()
    digest = first["digest"]
    again = call(client, trial, "index", task="another task", cwd="/x", known=digest).json()
    stale = call(client, trial, "index", task="another task", cwd="/x", known="0" * 12).json()
    elsewhere = client.post(
        "/api/v1/memory/recall/index",
        json={"session": "ffff0000", "task": "another task", "cwd": "/x", "known": digest},
        headers=trial,
    ).json()
    log = settings.state_dir / "identities" / "trial" / "state" / "memory-recall.log"
    with log.open("a") as handle:
        handle.write(json.dumps({"at": "2026-11-17T12:00:00", "session": "abcd1234", "op": "compact"}) + "\n")
    compacted = call(client, trial, "index", task="another task", cwd="/x", known=digest).json()
    write(memory / "MEMORY.md", "- feedback_g.md — When g changes\n")
    changed = call(client, trial, "index", task="another task", cwd="/x", known=digest).json()

    assert first["sections"] is not None
    assert again["sections"] is None
    assert again["digest"] == digest
    assert again["unchanged_since"] == logged(settings)[0]["at"]
    assert stale["sections"] == first["sections"]
    assert elsewhere["sections"] == first["sections"]
    assert compacted["sections"] == first["sections"]
    assert changed["sections"] is not None
    assert changed["digest"] != digest


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
        "Memory: feedback_g.md · Truthness: unset; held 0, misled 0, irrelevant 0 · Validity: undated\n\nG.\n"
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
        "Memory: personal:core/claude_self.md · Truthness: unset · Validity: not scored (personal)\n\nSelf.\n"
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


def test_an_opened_memory_lists_the_memories_it_links_to_by_index_line_and_only_a_weak_ones_trust(
    client: TestClient, trial: dict[str, str], memory: Path
) -> None:
    write(memory / "feedback_g.md", "G.\nRelated: [[feedback_r]], [[user_x]], [[feedback_gone]], [[feedback_g]].\n")

    context = frame(client, trial, memory, "feedback_g.md").json()["context"]
    assert "\nRelated:\n" in context
    links = context.split("\nRelated:\n", 1)[1]

    assert "This memory" not in context
    assert "- acme/shop/feedback_r.md — When r\n" in links
    assert "- personal:user_x.md — When x\n" in links
    assert "Truthness" not in links
    assert "- [[feedback_gone]]: no memory of that name" in links
    assert "feedback_g.md —" not in links
    assert "R." not in links and "X." not in links


def test_a_long_memory_with_many_links_is_put_in_and_its_links_give_way(
    client: TestClient, trial: dict[str, str], memory: Path
) -> None:
    for n in range(8):
        write(memory / f"feedback_l{n}.md", f"L{n}.\n")
    links = ", ".join(f"[[feedback_l{n}]]" for n in range(8))
    write(memory / "feedback_g.md", "G" * 8_950 + f"\nRelated: {links}.\n")

    context = frame(client, trial, memory, "feedback_g.md").json()["context"]

    assert context.startswith("Memory: feedback_g.md")
    assert "not put in" not in context
    assert "related line(s) left out: over the size limit" in context
    assert len(context) <= 9_500 + 100


def test_memories_left_out_of_one_call_are_named_first_and_the_note_stays_under_the_hook_cap(
    client: TestClient, trial: dict[str, str], memory: Path
) -> None:
    names = [f"feedback_big{n}" for n in range(6)]
    for name in names:
        write(memory / f"{name}.md", "B" * 3_000 + "\n")
    opened = [{"file": f"{name}.md", "path": str((memory / f"{name}.md").resolve())} for name in names]

    context = client.post(
        "/api/v1/memory/recall/frame", json={"session": "abcd1234", "opened": opened}, headers=trial
    ).json()["context"]

    first = context.splitlines()[0]
    put_in = [name for name in names if f"Memory: {name}.md" in context]
    assert first.startswith("[memory] not put in: ")
    assert put_in and len(put_in) < len(names)
    assert all((f"{name}.md" in first) != (name in put_in) for name in names)
    assert len(context) <= 10_000


def test_a_note_carries_the_type_and_what_a_memory_supersedes_instead_of_its_frontmatter(
    client: TestClient, trial: dict[str, str], memory: Path
) -> None:
    write(
        memory / "feedback_g.md",
        "---\nname: feedback_g\ndescription: When g\ntype: feedback\nsupersedes: feedback_old\n---\nG.\n",
    )

    context = frame(client, trial, memory, "feedback_g.md").json()["context"]

    assert context.startswith("Memory: feedback_g.md (feedback) · supersedes feedback_old · Truthness: ")
    assert "name: feedback_g" not in context and "description:" not in context
    assert "\n\nG.\n" in context


def test_a_linked_memory_shows_its_trust_only_where_it_is_weak(
    client: TestClient, trial: dict[str, str], memory: Path
) -> None:
    write(memory / "MEMORY.md", "- feedback_g.md — When g\n- feedback_guess.md — When guessed\n")
    write(memory / "feedback_guess.md", "---\nname: feedback_guess\nsource: inference\n---\nGuess.\n")
    write(memory / "feedback_g.md", "G.\nRelated: [[feedback_guess]], [[feedback_r]].\n")

    context = frame(client, trial, memory, "feedback_g.md").json()["context"]

    assert "\nRelated:\n" in context
    links = context.split("\nRelated:\n", 1)[1]
    assert "- feedback_guess.md — When guessed\n  Truthness: inference;" in links
    assert "⚠ Weak truthness: it was inferred" in links
    assert "- acme/shop/feedback_r.md — When r\n" in links
    assert links.count("Truthness") == 1


def test_an_index_answer_is_corrected_for_an_agent_that_did_not_read_the_parts_itself(
    client: TestClient, trial: dict[str, str], memory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from whaat.memory import recall

    write(memory / "MEMORY.md", "".join(f"- feedback_g{n}.md — When g{n} happens\n" for n in range(6)))
    monkeypatch.setattr(recall, "PART_BUDGET", 80)

    def index(session: str, **body: Any) -> Any:
        payload = {"session": session, "task": "review the shop", "cwd": "/x", **body}
        return client.post("/api/v1/memory/recall/index", json=payload, headers=trial).json()

    def seen(session: str, agent: str, **body: Any) -> Any:
        payload = {"session": session, "agent": agent, **body}
        return client.post("/api/v1/memory/recall/seen", json=payload, headers=trial).json()["note"]

    first = index("abcd1234")
    digest, parts = first["digest"], first["parts"]
    for n in range(1, parts + 1):
        index("abcd1234", part=n)
        assert seen("abcd1234", "", digest=digest, part=n, parts=parts) is None
    index("abcd1234", part=1)
    assert seen("abcd1234", "sub1", digest=digest, part=1, parts=parts) is None

    told_unchanged = index("abcd1234", known=digest)
    unchanged = seen("abcd1234", "sub1", digest=digest, unchanged=True, parts=parts)
    told_complete = index("abcd1234", part=parts)
    jumped = seen("abcd1234", "sub1", digest=digest, part=parts, parts=parts)
    main = seen("abcd1234", "", digest=digest, unchanged=True, parts=parts)
    index("ffff0000", part=1)
    assert seen("ffff0000", "", digest=digest, part=1, parts=parts) is None
    alone = index("ffff0000", part=parts)
    named = seen("ffff0000", "", digest=digest, part=parts, parts=parts)
    beyond = client.post(
        "/api/v1/memory/recall/seen",
        json={"session": "abcd1234", "digest": digest, "part": 1, "parts": 1_000_000},
        headers=trial,
    )

    assert parts > 2
    assert told_unchanged["sections"] is None and told_complete["missing"] == []
    assert unchanged is not None and "has not read every part" in unchanged
    assert jumped is not None and f"has not read part {', '.join(str(n) for n in range(2, parts))} of index" in jumped
    assert main is None
    assert alone["missing"] == list(range(2, parts)) and named is None
    assert beyond.status_code == 422
