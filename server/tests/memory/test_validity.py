import datetime
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TOKEN, write

ADMIN = {"Authorization": f"Bearer {TOKEN}"}
TODAY = datetime.date.today()


@pytest.fixture
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = write(tmp_path / "gitconfig", "[user]\n\tname = Test\n\temail = test@example.com\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def trial(client: TestClient, isolated_git: None) -> dict[str, str]:
    response = client.post("/api/v1/identities", json={"id": "trial"}, headers=ADMIN)
    return {"Authorization": f"Bearer {response.json()['token']}"}


def memory_file(name: str, **fields: str) -> str:
    head = "".join(f"{key}: {value}\n" for key, value in fields.items())
    return f"---\nname: {name}\ndescription: When {name}\n{head}---\nBody.\n"


@pytest.fixture
def folder(client: TestClient, trial: dict[str, str], settings: Any) -> Path:
    root = settings.state_dir / "identities" / "trial"
    client.post(
        "/api/v1/memory/memories",
        json={
            "path": "acme/shop/feedback_new.md",
            "content": memory_file("feedback_new", source="measured"),
            "trigger": "When new",
        },
        headers=trial,
    )
    memory = root / "memory"
    write(
        memory / "acme/shop/feedback_old.md", memory_file("feedback_old", source="inference", confirmed="'2026-01-01'")
    )
    write(memory / "acme/shop/feedback_gone.md", memory_file("feedback_gone", confirmed="2026-10-01"))
    write(
        memory / "acme/shop/feedback_now.md",
        memory_file("feedback_now", confirmed="2026-10-01", supersedes="feedback_gone"),
    )
    with (memory / "acme/shop/MEMORY.md").open("a") as handle:
        handle.write("- feedback_old.md — When old\n- feedback_now.md — When now\n")
    write(memory / "personal/user_x.md", memory_file("user_x", confirmed="2020-01-01"))
    return root


def post(client: TestClient, auth: dict[str, str], endpoint: str, **body: Any) -> Any:
    return client.post(f"/api/v1/memory/{endpoint}", json=body, headers=auth)


def expected(base: float, day: datetime.date) -> float:
    return round(max(0.0, base - 0.2 / 120 * (TODAY - day).days), 3)


def test_refresh_scores_from_source_and_latest_anchor_and_leaves_personal_out(
    client: TestClient, trial: dict[str, str], folder: Path
) -> None:
    summary = post(client, trial, "validity/refresh").json()["text"]
    data = json.loads((folder / "state/memory-validity.json").read_text())

    assert summary.startswith(f"{folder / 'state/memory-validity.json'}: ")
    assert data["store"] == str((folder / "memory").resolve())
    assert sorted(data["memories"]) == [
        "acme/shop/feedback_gone.md",
        "acme/shop/feedback_new.md",
        "acme/shop/feedback_now.md",
        "acme/shop/feedback_old.md",
    ]
    new, old = data["memories"]["acme/shop/feedback_new.md"], data["memories"]["acme/shop/feedback_old.md"]
    assert (new["anchors"], new["score"], new["level"]) == ({"first_commit": TODAY.isoformat()}, 1.0, "certain")
    assert old["anchors"] == {"confirmed": "2026-01-01"}
    assert old["score"] == expected(0.75, datetime.date(2026, 1, 1))
    assert data["memories"]["acme/shop/feedback_gone.md"]["history"] == "acme/shop/feedback_now.md"


def test_a_store_file_a_personal_memory_supersedes_is_history_and_not_scored(
    client: TestClient, trial: dict[str, str], folder: Path
) -> None:
    memory = folder / "memory"
    write(memory / "acme/shop/reference_old_pointer.md", memory_file("reference_old_pointer", confirmed="2026-10-01"))
    write(
        memory / "personal/reference_new_pointer.md",
        memory_file("reference_new_pointer", supersedes="reference_old_pointer"),
    )

    post(client, trial, "validity/refresh")
    entry = json.loads((folder / "state/memory-validity.json").read_text())["memories"][
        "acme/shop/reference_old_pointer.md"
    ]

    assert entry.get("history") == "personal:reference_new_pointer"
    assert "score" not in entry


def test_a_read_is_logged_and_a_weak_memory_named_but_not_a_personal_one_or_an_index(
    client: TestClient, trial: dict[str, str], folder: Path
) -> None:
    memory = folder / "memory"
    gone = post(client, trial, "outcome/read", session="abcd1234ef", path=str(memory / "acme/shop/feedback_gone.md"))
    fresh = post(client, trial, "outcome/read", session="abcd1234ef", path=str(memory / "acme/shop/feedback_new.md"))
    personal = post(client, trial, "outcome/read", session="abcd1234ef", path=str(memory / "personal/user_x.md"))
    index = post(client, trial, "outcome/read", session="abcd1234ef", path=str(memory / "acme/shop/MEMORY.md"))

    assert gone.json()["text"] == (
        "Memory acme/shop/feedback_gone.md is superseded by acme/shop/feedback_now.md: history, never act on it."
    )
    assert fresh.json()["text"] is personal.json()["text"] is index.json()["text"] is None
    assert (folder / "state/memory-reads.log").read_text().splitlines() == [
        f"{TODAY.isoformat()}\tread\tacme/shop/feedback_gone.md\tabcd1234",
        f"{TODAY.isoformat()}\tread\tacme/shop/feedback_new.md\tabcd1234",
    ]
    assert post(client, trial, "outcome/reads", session="abcd1234").json()["text"] == (
        "acme/shop/feedback_gone.md\nacme/shop/feedback_new.md"
    )
    assert post(client, trial, "outcome/reads", session="other000").json()["text"] == (
        "no store reads logged for session other000"
    )


def test_record_keeps_store_memories_only_and_a_held_one_is_rescored_at_once(
    client: TestClient, trial: dict[str, str], folder: Path
) -> None:
    recorded = post(
        client,
        trial,
        "outcome/record",
        session="abcd1234ef",
        outcome="held",
        paths=["acme/shop/feedback_old.md", "personal/user_x.md", "personal:user_x.md"],
    ).json()["text"]
    data = json.loads((folder / "state/memory-validity.json").read_text())

    assert recorded.splitlines() == [
        "skipped personal/user_x.md: not a memory file in the store (use the path `reads` prints)",
        "skipped personal:user_x.md: not a memory file in the store (use the path `reads` prints)",
        "recorded held for 1 memories",
    ]
    assert data["memories"]["acme/shop/feedback_old.md"]["anchors"]["held"] == TODAY.isoformat()
    assert data["memories"]["acme/shop/feedback_old.md"]["score"] == 0.75


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            {"session": "abcd1234", "outcome": "fine", "paths": ["x.md"]},
            "outcome must be one of held, misled, irrelevant",
        ),
        (
            {"session": "", "outcome": "held", "paths": ["x.md"]},
            "no session id: pass <session8>, or run inside Claude Code",
        ),
    ],
)
def test_record_refuses_what_memory_outcome_refuses(
    client: TestClient, trial: dict[str, str], folder: Path, body: dict[str, Any], message: str
) -> None:
    refused = post(client, trial, "outcome/record", **body)

    assert (refused.status_code, refused.json()["detail"]) == (422, message)


def test_level_names_each_memory_as_memory_validity_does(
    client: TestClient, trial: dict[str, str], folder: Path
) -> None:
    text = post(
        client,
        trial,
        "validity/level",
        paths=["acme/shop/feedback_new.md", "acme/shop/feedback_gone.md", "acme/shop/none.md"],
    ).json()["text"]

    assert text.splitlines() == [
        "acme/shop/feedback_new.md: certain 1.00 (0 days, source measured)",
        "acme/shop/feedback_gone.md: history, superseded by acme/shop/feedback_now.md",
        "acme/shop/none.md: not a memory in the store",
    ]


def test_a_returning_memory_carries_its_truthness_and_validity(
    client: TestClient, trial: dict[str, str], folder: Path
) -> None:
    memory = folder / "memory"
    write(
        memory / "acme/shop/feedback_stale.md",
        memory_file("feedback_stale", source="user-decision", confirmed="2025-03-01"),
    )
    with (memory / "acme/shop/MEMORY.md").open("a") as handle:
        handle.write("- feedback_stale.md — When stale\n")
    post(client, trial, "outcome/record", session="abcd1234", outcome="misled", paths=["acme/shop/feedback_stale.md"])
    post(
        client, trial, "outcome/record", session="abcd1234", outcome="irrelevant", paths=["acme/shop/feedback_stale.md"]
    )

    def framed(rel: str, path: Path) -> str:
        body = {"session": "s1", "opened": [{"file": rel, "path": str(path.resolve())}]}
        return client.post("/api/v1/memory/recall/frame", json=body, headers=trial).json()["context"]

    stale = framed("acme/shop/feedback_stale.md", memory / "acme/shop/feedback_stale.md")
    gone = framed("acme/shop/feedback_gone.md", memory / "acme/shop/feedback_gone.md")
    personal = framed("personal:user_x.md", memory / "personal/user_x.md")

    age = (TODAY - datetime.date(2025, 3, 1)).days
    assert stale.splitlines()[:5] == [
        "Memory: acme/shop/feedback_stale.md",
        "Truthness: source user-decision; since its last change held 0, misled 1, irrelevant 1",
        f"Validity: stale 0.00 ({age} days since it was last confirmed, held or added)",
        f"⚠ Stale: nobody has confirmed it or relied on it for {age} days.",
        "⚠ Weak truthness: it misled 1 time(s) since its last change.",
    ]
    assert gone.splitlines()[2:4] == [
        "Validity: history, superseded by acme/shop/feedback_now.md",
        "⚠ History: acme/shop/feedback_now.md replaced it.",
    ]
    assert personal.splitlines()[1:4] == ["Truthness: source unset", "Validity: not scored (personal memory)", ""]


def test_a_memory_added_after_todays_scores_is_scored_when_it_returns(
    client: TestClient, trial: dict[str, str], folder: Path
) -> None:
    post(client, trial, "validity/refresh")
    memory = folder / "memory"
    write(
        memory / "acme/shop/reference_late.md",
        memory_file("reference_late", source="inference", confirmed="2025-01-15"),
    )
    body = {
        "session": "s1",
        "opened": [{"file": "acme/shop/reference_late.md", "path": str(memory / "acme/shop/reference_late.md")}],
    }

    note = client.post("/api/v1/memory/recall/frame", json=body, headers=trial).json()["context"]

    assert note.splitlines()[1].startswith("Truthness: source inference;")
    assert note.splitlines()[2].startswith("Validity: stale 0.00 (")
    assert note.splitlines()[4] == "⚠ Weak truthness: it was inferred, not measured or decided by the user."
