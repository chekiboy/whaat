import copy
import json
import subprocess
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import CLAUDE_TOKEN, TOKEN, write
from tests.journal.samples import BLOCK
from whaat.config import Settings
from whaat.git import GitCommitter
from whaat.journal.schemas import JournalEntry
from whaat.journal.service import JournalService
from whaat.journal.store import FileJournalStore
from whaat.reports.store import roots_from

AUTH = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}
ADMIN = {"Authorization": f"Bearer {TOKEN}"}
ENTRY = "journal/2026/10/2026-10-29_a976c334.json"


@pytest.fixture
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = write(tmp_path / "gitconfig", "[user]\n\tname = Test\n\temail = test@example.com\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def git(folder: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, check=True).stdout


def save(client: TestClient, **entry: object) -> dict[str, object]:
    response = client.post("/api/v1/journal/entries", json=entry, headers=AUTH)
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def document(settings: Settings, rel: str = ENTRY) -> Any:
    data: Any = json.loads((settings.identities["claude"] / rel).read_text(encoding="utf-8"))
    return data


def test_a_block_is_stored_as_sent_with_its_envelope_in_the_same_file(client: TestClient, settings: Settings) -> None:
    saved = save(client, session="a976c334", entry_date="2026-10-29", block=BLOCK, tags=["whaat"])

    stored = document(settings)
    block = stored["body"]["blocks"][0]
    assert {key: value for key, value in block.items() if key != "at"} == BLOCK
    assert datetime.fromisoformat(block["at"]).utcoffset() is not None
    assert {key: stored["envelope"][key] for key in ("kind", "session", "identity", "writer", "tags")} == {
        "kind": "journal",
        "session": "a976c334",
        "identity": "claude",
        "writer": "whaat:journal",
        "tags": ["whaat"],
    }
    assert saved["report_id"] == f"private-claude:{ENTRY}"
    assert not (settings.identities["claude"] / ENTRY).with_suffix(".meta.json").exists()
    assert (settings.identities["claude"] / ENTRY).stat().st_mode & 0o777 == 0o600
    assert (settings.identities["claude"] / "journal/2026").stat().st_mode & 0o777 == 0o700


def test_a_later_block_is_appended_and_tags_only_grow(client: TestClient, settings: Settings) -> None:
    second = {**BLOCK, "about": "The second block."}
    first = save(client, session="a976c334", entry_date="2026-10-29", block=BLOCK, tags=["whaat", "identity"])
    again = save(client, session="a976c334", entry_date="2026-10-29", block=second, tags=["journal", "whaat"])

    stored = document(settings)
    assert [block["about"] for block in stored["body"]["blocks"]] == [BLOCK["about"], "The second block."]
    assert stored["envelope"]["tags"] == ["whaat", "identity", "journal"]
    assert (first["appended"], again["appended"]) == (False, True)


def test_the_detail_gives_the_blocks_and_the_list_filters_by_session_and_tag(client: TestClient) -> None:
    save(client, session="a976c334", entry_date="2026-10-29", block=BLOCK, tags=["whaat"])
    report_id = f"private-claude:{ENTRY}"

    detail = client.get(f"/api/v1/reports/{report_id}", headers=AUTH).json()
    by_session = client.get("/api/v1/reports", params={"session": "a976c334"}, headers=AUTH).json()
    by_tag = client.get("/api/v1/reports", params={"tag": "whaat"}, headers=AUTH).json()

    assert detail["envelope_source"] == "embedded"
    assert detail["body"]["format"] == "journal"
    assert {key: value for key, value in detail["body"]["blocks"][0].items() if key != "at"} == BLOCK
    assert [report["id"] for report in by_session] == [report_id]
    assert [report["id"] for report in by_tag] == [report_id]


def test_created_at_is_the_first_save_in_atom_form(settings: Settings) -> None:
    times = iter(
        [
            datetime(2026, 10, 29, 10, 17, 5, 999, tzinfo=timezone(timedelta(hours=1))),
            datetime(2026, 10, 29, 11, 20, tzinfo=UTC),
        ]
    )
    service = JournalService(FileJournalStore(), lambda _: roots_from(settings), GitCommitter(), lambda: next(times))

    service.save_entry(JournalEntry.model_validate({"session": "a976c334", "block": BLOCK}), "claude")
    service.save_entry(JournalEntry.model_validate({"session": "a976c334", "block": BLOCK}), "claude")

    stored = document(settings)
    assert stored["envelope"]["created_at"] == "2026-10-29T10:17:05+01:00"
    assert [block["at"] for block in stored["body"]["blocks"]] == [
        "2026-10-29T10:17:05+01:00",
        "2026-10-29T11:20:00+00:00",
    ]


def test_a_git_folder_gets_a_commit_of_the_document_only(
    client: TestClient, settings: Settings, isolated_git: None
) -> None:
    folder = settings.identities["claude"]
    git(folder, "init", "--quiet")
    write(folder / "drafts/unrelated.md", "staged by another session\n")
    git(folder, "add", "drafts/unrelated.md")

    saved = save(client, session="a976c334", entry_date="2026-10-29", block=BLOCK)

    assert saved["commit"] == git(folder, "rev-parse", "HEAD").strip()
    assert git(folder, "log", "-1", "--format=%s") == "journal: session a976c334 entry\n"
    assert git(folder, "show", "--name-only", "--format=", "HEAD").split() == [ENTRY]
    assert git(folder, "diff", "--cached", "--name-only") == "drafts/unrelated.md\n"


def test_a_folder_without_git_keeps_the_entry_and_says_it_is_not_committed(client: TestClient) -> None:
    saved = save(client, session="a976c334", block=BLOCK)

    assert saved["commit"] is None
    assert saved["warnings"] == ["the private folder of claude is not a git repository; it is not committed"]


def without(key: str) -> dict[str, Any]:
    block: dict[str, Any] = copy.deepcopy(BLOCK)
    del block[key]
    return block


@pytest.mark.parametrize(
    "entry",
    [
        {"session": "a976c334", "block": BLOCK, "identity": "second"},
        {"session": "A976C334", "block": BLOCK},
        {"session": "a976c334", "block": BLOCK, "tags": ["Whaat"]},
        {"session": "a976c334", "block": {**BLOCK, "mood": "invented"}},
        {"session": "a976c334", "block": without("corrections")},
        {"session": "a976c334", "block": without("narrative")},
        {"session": "a976c334", "block": {**BLOCK, "learned": ""}},
        {"session": "a976c334", "text": "## 10:17\n- markdown\n"},
    ],
    ids=[
        "identity-in-body",
        "session",
        "tag",
        "invented-field",
        "missing-field",
        "missing-narrative",
        "empty-text",
        "markdown",
    ],
)
def test_invalid_entries_are_refused(client: TestClient, entry: dict[str, object]) -> None:
    assert client.post("/api/v1/journal/entries", json=entry, headers=AUTH).status_code == 422


def test_an_invalid_stored_document_is_left_alone(client: TestClient, settings: Settings) -> None:
    path = write(settings.identities["claude"] / ENTRY, '{"envelope": {}, "body": "broken"}')

    response = client.post(
        "/api/v1/journal/entries",
        json={"session": "a976c334", "entry_date": "2026-10-29", "block": BLOCK},
        headers=AUTH,
    )

    assert response.status_code == 409
    assert path.read_text() == '{"envelope": {}, "body": "broken"}'


def test_saving_needs_the_token(client: TestClient) -> None:
    assert client.post("/api/v1/journal/entries", json={"session": "a976c334", "block": BLOCK}).status_code == 401


def test_not_recorded_is_null_and_stays_apart_from_recorded_as_none(client: TestClient, settings: Settings) -> None:
    moment: dict[str, Any] = {**without("own_words"), "own_words": None}
    first_words: Any = BLOCK["own_words"]
    older = {**moment, "corrections": None, "own_words": [{**first_words[0], "at": None}]}
    save(client, session="a976c334", entry_date="2026-10-29", block=older)

    block = document(settings)["body"]["blocks"][0]
    assert (block["corrections"], block["mistakes"], block["own_words"][0]["at"]) == (None, BLOCK["mistakes"], None)


def test_a_stored_block_from_before_the_narrative_still_reads(client: TestClient, settings: Settings) -> None:
    save(client, session="a976c334", entry_date="2026-10-29", block=BLOCK)
    stored = document(settings)
    del stored["body"]["blocks"][0]["narrative"]
    write(settings.identities["claude"] / ENTRY, json.dumps(stored))

    save(client, session="a976c334", entry_date="2026-10-29", block=BLOCK)

    blocks = document(settings)["body"]["blocks"]
    assert (blocks[0]["narrative"], blocks[1]["narrative"]) == (None, BLOCK["narrative"])
