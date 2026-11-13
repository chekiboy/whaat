from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TOKEN, write

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


def save(client: TestClient, headers: dict[str, str], path: str, content: str) -> None:
    body = {"path": path, "content": content, "trigger": f"when {path}"}
    assert client.post("/api/v1/memory/memories", json=body, headers=headers).status_code == 201


def test_lint_reports_the_live_checks_and_leaves_the_personal_dir_out(
    client: TestClient, trial: dict[str, str], settings: Any
) -> None:
    save(client, trial, "feedback_good.md", "---\nname: feedback_good\ndescription: d\ntype: feedback\n---\nB.\n")
    save(client, trial, "reference_misnamed.md", "---\nname: other\ndescription: d\ntype: reference\n---\n[[gone]]\n")
    personal = settings.state_dir / "identities/trial/memory/personal"
    write(personal / "feedback_also_misnamed.md", "---\nname: x\ndescription: d\ntype: feedback\n---\nB.\n")

    text = client.post("/api/v1/memory/lint", json={}, headers=trial).json()["text"]

    assert "| reference_misnamed.md | name | name: 'other' ≠ filename |" in text
    assert "| reference_misnamed.md | broken-link | [[gone]] |" in text
    assert "personal" not in text
    assert text.startswith("# memory-lint — ")


def test_links_into_the_personal_dir_resolve_and_an_older_name_form_gets_a_suggestion(
    client: TestClient, trial: dict[str, str], settings: Any
) -> None:
    personal = settings.state_dir / "identities/trial/memory/personal"
    write(personal / "core/user_profile.md", "---\nname: user_profile\ndescription: d\n---\nB.\n")
    write(
        personal / "feedback_pair_review.md",
        "---\nname: feedback_pair_review\ndescription: d\ntype: feedback\n---\nB.\n",
    )
    body = "[[user_profile]] [[feedback_pair_review]] [[user-profile]] [[pair-review]] [[gone]]"
    save(
        client,
        trial,
        "reference_links.md",
        f"---\nname: reference_links\ndescription: d\ntype: reference\n---\n{body}\n",
    )

    text = client.post("/api/v1/memory/lint", json={}, headers=trial).json()["text"]

    assert "[[user_profile]] |" not in text
    assert "[[feedback_pair_review]] |" not in text
    assert "| reference_links.md | broken-link | [[user-profile]] (now [[user_profile]]?) |" in text
    assert "| reference_links.md | broken-link | [[pair-review]] (now [[feedback_pair_review]]?) |" in text
    assert "| reference_links.md | broken-link | [[gone]] |" in text


def test_a_store_file_a_personal_memory_supersedes_is_history_not_unindexed(
    client: TestClient, trial: dict[str, str], settings: Any
) -> None:
    memory = settings.state_dir / "identities/trial/memory"
    write(
        memory / "reference_old_pointer.md",
        "---\nname: reference_old_pointer\ndescription: d\ntype: reference\n---\nB.\n",
    )
    new = (
        "---\nname: reference_new_pointer\ndescription: d\ntype: reference\n"
        "supersedes: reference_old_pointer\n---\nB.\n"
    )
    write(memory / "personal/reference_new_pointer.md", new)

    text = client.post("/api/v1/memory/lint", json={}, headers=trial).json()["text"]

    assert "| reference_old_pointer.md | unindexed |" not in text
    assert "- history: reference_old_pointer.md, superseded by personal:reference_new_pointer" in text


def test_only_an_identity_lints_its_own_memory(client: TestClient) -> None:
    assert client.post("/api/v1/memory/lint", json={}).status_code == 401


def test_the_curation_brief_holds_the_fixed_text_and_every_candidate_of_its_dir(
    client: TestClient, trial: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    long = "x" * 1600
    for when in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
        monkeypatch.setenv(when, "2026-01-01T10:00:00+00:00")
    save(client, trial, "feedback_old.md", f"---\nname: feedback_old\ndescription: d\ntype: feedback\n---\n{long}\n")
    for when in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
        monkeypatch.delenv(when)
    save(client, trial, "feedback_new.md", f"---\nname: feedback_new\ndescription: d\ntype: feedback\n---\n{long}\n")
    trigger = "When " + "w" * 160
    body = {"path": "feedback_wide.md", "trigger": trigger}
    body["content"] = "---\nname: feedback_wide\ndescription: d\ntype: feedback\n---\nB.\n"
    assert client.post("/api/v1/memory/memories", json=body, headers=trial).status_code == 201

    text = client.post("/api/v1/memory/curation-brief", json={"dir": "."}, headers=trial).json()["text"]

    assert text.startswith("# Curation judge: (global: the memory root)")
    assert "## What each action requires" in text
    assert "- feedback_old.md: over-budget — body 1601 chars > 1200 by more than 25%" in text
    assert "feedback_new.md: over-budget" not in text
    assert f"- feedback_wide.md: long-index-line — 165 chars > 150: {trigger}" in text
    assert "## Candidates (4)" in text
    assert "{{" not in text


def test_the_curation_brief_refuses_a_dir_that_is_not_one(client: TestClient, trial: dict[str, str]) -> None:
    save(client, trial, "feedback_good.md", "---\nname: feedback_good\ndescription: d\ntype: feedback\n---\nB.\n")
    assert client.post("/api/v1/memory/curation-brief", json={"dir": "nope"}, headers=trial).status_code == 404


def test_the_refuter_brief_holds_the_fixed_text_and_the_judges_rows_as_they_came(
    client: TestClient, trial: dict[str, str]
) -> None:
    save(client, trial, "feedback_good.md", "---\nname: feedback_good\ndescription: d\ntype: feedback\n---\nB.\n")
    rows = [{"file": "feedback_good.md", "actions": ["trim"], "target": None, "reason": "ő long", "evidence": None}]

    text = client.post("/api/v1/memory/curation-refute-brief", json={"dir": ".", "rows": rows}, headers=trial).json()

    assert text["text"].startswith("# Curation refuter: (global: the memory root)")
    assert '"reason": "ő long"' in text["text"]
    assert "## The other aspect, per action" in text["text"]
    assert "{{" not in text["text"]


def test_the_fidelity_table_marks_every_old_sentence_the_new_text_no_longer_holds(
    client: TestClient, trial: dict[str, str]
) -> None:
    head = "---\nname: feedback_rule\ndescription: d\ntype: feedback\n---\n"
    save(client, trial, "feedback_rule.md", head + "Keep the trap. Story of how we found it. Run `make x`.\n")
    save(client, trial, "feedback_rule.md", head + "Keep the trap. Run `make x`.\n")

    text = client.post(
        "/api/v1/memory/fidelity",
        json={"file": "feedback_rule.md", "rev": "HEAD~1", "new": ["feedback_rule.md"]},
        headers=trial,
    ).json()["text"]

    assert "3 sentences; 2 kept word for word; 1 to account for" in text
    assert "| 2 | **account for it** | Story of how we found it. |" in text
    assert "| 1 | kept in feedback_rule.md | Keep the trap. |" in text
