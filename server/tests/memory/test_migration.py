import datetime
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import CLAUDE_TOKEN, TOKEN, write
from whaat.config import Settings

ADMIN = {"Authorization": f"Bearer {TOKEN}"}
CLAUDE = {"Authorization": f"Bearer {CLAUDE_TOKEN}"}


def memory(name: str, body: str = "Do it.") -> str:
    return f"---\nname: {name}\ndescription: When {name}\ntype: feedback\n---\n{body}\n"


@pytest.fixture
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = write(tmp_path / "gitconfig", "[user]\n\tname = Test\n\temail = test@example.com\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def trial(client: TestClient, isolated_git: None) -> dict[str, str]:
    response = client.post("/api/v1/identities", json={"id": "trial"}, headers=ADMIN)
    return {"Authorization": f"Bearer {response.json()['token']}"}


def git(folder: Path, *args: str, day: str | None = None) -> str:
    env = {
        **os.environ,
        **({"GIT_AUTHOR_DATE": f"{day}T12:00:00", "GIT_COMMITTER_DATE": f"{day}T12:00:00"} if day else {}),
    }
    return subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, check=True, env=env).stdout


@pytest.fixture
def store(tmp_path: Path, isolated_git: None) -> Path:
    """A store under git: two root memories, a group's own memory, a repo's memory, and what must never be a group."""
    root = tmp_path / "store"
    write(root / "feedback_a.md", memory("feedback_a"))
    write(root / "feedback_b.md", memory("feedback_b"))
    write(root / "MEMORY.md", "- feedback_a.md — When a\n- feedback_b.md — When b\n")
    write(root / "memory-map.md", "## Memory map\n")
    write(root / "acme/feedback_g.md", memory("feedback_g"))
    write(root / "acme/MEMORY.md", "- feedback_g.md — When g\n")
    write(root / "acme/shop/reference_r.md", memory("reference_r"))
    write(root / "acme/shop/MEMORY.md", "- reference_r.md — When r\n")
    write(root / "acme/web/project_w.md", memory("project_w"))
    write(root / "acme/web/MEMORY.md", "- project_w.md — When w\n")
    write(root / ".claude/agent-memory/x.md", memory("x"))
    write(root / "acme/.cache/y.md", memory("y"))
    git(root, "init", "--quiet")
    git(root, "add", "-A")
    git(root, "commit", "--quiet", "-m", "first", day="2025-01-10")
    write(root / "feedback_b.md", memory("feedback_b", "Do it twice."))
    git(root, "commit", "--quiet", "-am", "second", day="2025-03-01")
    return root


def call(client: TestClient, auth: dict[str, str], what: str, body: dict[str, Any]) -> Any:
    return client.post(f"/api/v1/memory/migration/{what}", json=body, headers=auth)


def trial_root(settings: Settings) -> Path:
    return settings.state_dir / "identities" / "trial"


def test_the_listing_names_every_layer_and_skips_dot_dirs_the_map_and_the_index(
    client: TestClient, trial: dict[str, str], store: Path
) -> None:
    listed = call(client, trial, "groups", {"sources": [{"path": str(store), "kind": "store"}]}).json()

    assert [(g["id"], g["files"]) for g in listed["groups"]] == [
        ("1:.", ["feedback_a.md", "feedback_b.md"]),
        ("1:acme", ["acme/feedback_g.md"]),
        ("1:acme/shop", ["acme/shop/reference_r.md"]),
        ("1:acme/web", ["acme/web/project_w.md"]),
    ]
    assert all(g["new"] == g["files"] and not g["dropped"] for g in listed["groups"])
    assert listed["warnings"] == []


def test_the_import_copies_only_the_picked_groups_byte_for_byte_with_their_index_lines_one_commit_each(
    client: TestClient, settings: Settings, trial: dict[str, str], store: Path
) -> None:
    before = {p: p.read_bytes() for p in store.rglob("*") if p.is_file() and ".git" not in p.parts}

    imported = call(
        client, trial, "import", {"sources": [{"path": str(store), "kind": "store"}], "groups": ["1:.", "1:acme/shop"]}
    ).json()

    root = trial_root(settings) / "memory"
    assert [g["copied"] for g in imported["groups"]] == [
        ["feedback_a.md", "feedback_b.md"],
        ["acme/shop/reference_r.md"],
    ]
    for rel in ("feedback_a.md", "feedback_b.md", "acme/shop/reference_r.md"):
        assert (root / rel).read_bytes() == (store / rel).read_bytes()
    assert (root / "MEMORY.md").read_text() == "- feedback_a.md — When a\n- feedback_b.md — When b\n"
    assert (root / "acme/shop/MEMORY.md").read_text() == "- reference_r.md — When r\n"
    assert not (root / "acme/feedback_g.md").exists() and not (root / "acme/web").exists()
    assert not (root / "memory-map.md").exists()
    log = git(trial_root(settings), "log", "--format=%s").splitlines()
    assert [s for s in log if s.startswith("memory: import")][:2] == [
        f"memory: import 1 from {store / 'acme/shop'} into acme/shop",
        f"memory: import 2 from {store} into .",
    ]
    assert git(trial_root(settings), "status", "--porcelain") == ""
    assert {p: p.read_bytes() for p in store.rglob("*") if p.is_file() and ".git" not in p.parts} == before


def test_a_file_already_in_place_is_skipped_and_one_with_other_content_is_never_overwritten(
    client: TestClient, settings: Settings, trial: dict[str, str], store: Path
) -> None:
    root = trial_root(settings) / "memory"
    write(root / "feedback_a.md", memory("feedback_a"))
    write(root / "feedback_b.md", memory("feedback_b", "Mine."))
    sources = {"sources": [{"path": str(store), "kind": "store"}]}

    listed = call(client, trial, "groups", sources).json()["groups"][0]
    imported = call(client, trial, "import", {**sources, "groups": ["1:."]}).json()["groups"][0]

    assert (listed["new"], listed["same"], listed["conflicts"]) == ([], ["feedback_a.md"], ["feedback_b.md"])
    assert (imported["copied"], imported["same"], imported["conflicts"], imported["commit"]) == (
        [],
        ["feedback_a.md"],
        ["feedback_b.md"],
        None,
    )
    assert (root / "feedback_b.md").read_text() == memory("feedback_b", "Mine.")


def factory(name: str, kind: str, description: str, body: str) -> str:
    """A memory file as Claude Code's auto-memory writes it."""
    return (
        f'---\nname: {name}\ndescription: "{description}"\nmetadata:\n  node_type: memory\n  type: {kind}\n'
        f"  originSessionId: 9be49ccb\n  modified: 2026-10-22T07:40:19.972Z\n---\n\n{body}\n"
    )


def test_claude_codes_own_memory_comes_in_whaats_form_and_recall_finds_it(
    client: TestClient, settings: Settings, trial: dict[str, str], tmp_path: Path
) -> None:
    auto = tmp_path / "projects/-x/memory"
    write(
        auto / "user_taste.md",
        factory("user-report-taste", "user", "Visual taste", "Cards. See [[feedback-decision-pages]]."),
    )
    write(
        auto / "feedback_pages.md",
        factory("feedback-decision-pages", "feedback", "Pages", "Decide there. [[user-report-taste]]"),
    )
    write(auto / "testing_conventions.md", factory("testing-conventions", "project", "Tests", "Run make test."))
    write(auto / "feedback_ok.md", memory("feedback_ok"))
    write(
        auto / "MEMORY.md",
        "- **Open TODOs:** `todos/TODO.md` — read it first.\n"
        "- [Report taste](user_taste.md) — before designing a page\n"
        "- [Decision pages](feedback_pages.md) — when a run waits for decisions\n"
        "- [Tests](testing_conventions.md) — before running the tests\n"
        "- feedback_ok.md — When feedback_ok\n",
    )
    june = datetime.datetime(2025, 6, 1, 12).timestamp()
    os.utime(auto / "user_taste.md", (june, june))
    sources = {"sources": [{"path": str(auto), "kind": "loose", "target": "personal"}], "groups": ["1:personal"]}

    imported = call(client, trial, "import", sources).json()["groups"][0]

    origins_file = trial_root(settings) / "state/memory-origins.json"
    origins = json.loads(origins_file.read_text()) if origins_file.exists() else {}
    assert origins.get("personal/user_taste.md", {}).get("last") == "2025-06-01"
    root = trial_root(settings) / "memory/personal"
    assert imported["copied"] == [
        "personal/feedback_ok.md",
        "personal/feedback_pages.md",
        "personal/project_testing_conventions.md",
        "personal/user_taste.md",
    ]
    assert (root / "user_taste.md").read_text() == (
        "---\nname: user_taste\ndescription: before designing a page\ntype: user\n---\n"
        "Visual taste\n\nCards. See [[feedback_pages]].\n"
    )
    assert (root / "feedback_pages.md").read_text() == (
        "---\nname: feedback_pages\ndescription: when a run waits for decisions\ntype: feedback\n---\nPages\n\n"
        "Decide there. [[user_taste]]\n"
    )
    assert (
        (root / "project_testing_conventions.md")
        .read_text()
        .startswith(
            "---\nname: project_testing_conventions\ndescription: before running the tests\ntype: project\n---\n"
        )
    )
    assert (root / "feedback_ok.md").read_bytes() == (auto / "feedback_ok.md").read_bytes()
    own_lines = [line for line in (root / "MEMORY.md").read_text().splitlines(keepends=True) if "core/" not in line]
    assert "".join(own_lines) == (
        "- user_taste.md — before designing a page\n- feedback_pages.md — when a run waits for decisions\n"
        "- project_testing_conventions.md — before running the tests\n- feedback_ok.md — When feedback_ok\n"
    )
    assert imported["dropped"] == ["- **Open TODOs:** `todos/TODO.md` — read it first."]
    notes = {c["file"]: c["notes"] for c in imported["converted"]}
    assert "personal/feedback_ok.md" not in notes
    assert notes["personal/user_taste.md"][0].startswith("type user outside the core")
    sections = client.post(
        "/api/v1/memory/recall/index", json={"task": "design a page", "cwd": "/x", "session": "s"}, headers=trial
    ).json()["sections"]
    personal = next(s for s in sections if s["label"] == "personal")
    assert {"file": "personal:user_taste.md", "trigger": "before designing a page"} in personal["entries"]


def test_a_source_inside_an_identity_folder_is_refused(
    client: TestClient, settings: Settings, trial: dict[str, str]
) -> None:
    archive = settings.identities["second"]
    write(archive / "memory/feedback_x.md", memory("feedback_x"))

    response = call(client, trial, "groups", {"sources": [{"path": str(archive / "memory"), "kind": "store"}]})

    assert response.status_code == 422
    assert "identity's folder" in response.json()["detail"]


def test_the_source_dates_and_outcomes_come_along_so_validity_does_not_restart_at_the_import(
    client: TestClient, settings: Settings, trial: dict[str, str], store: Path, tmp_path: Path
) -> None:
    source_state = tmp_path / "source-state"
    write(
        source_state / "memory-outcomes.log",
        f"2025-04-01\tmisled\t{store}/feedback_b.md\ts1\n2025-02-01\tmisled\t{store}/feedback_b.md\ts0\n"
        f"2025-04-02\theld\t{store}/acme/feedback_g.md\ts1\n",
    )
    body = {"sources": [{"path": str(store), "kind": "store"}], "groups": ["1:."], "state": str(source_state)}

    imported = call(client, trial, "import", body).json()

    state = trial_root(settings) / "state"
    scores = json.loads((state / "memory-validity.json").read_text())["memories"]
    assert (imported["origins"], imported["outcomes"]) == (2, 2)
    assert scores["feedback_a.md"]["anchors"] == {"first_commit": "2025-01-10"}
    assert scores["feedback_b.md"]["anchors"] == {"first_commit": "2025-01-10"}
    assert scores["feedback_b.md"]["outcomes"] == {"misled": 1}
    assert "acme/feedback_g.md" not in scores


def test_d1_moves_the_personal_memory_into_personal_keeping_history_and_then_the_import_may_write_the_root(
    client: TestClient, settings: Settings, isolated_git: None, store: Path
) -> None:
    archive = settings.identities["claude"]
    write(archive / "memory/core/claude_self.md", memory("claude_self"))
    write(archive / "memory/MEMORY.md", "- core/claude_self.md — Who I am\n- feedback_mine.md — When mine\n")
    git(archive, "init", "--quiet")
    git(archive, "add", "memory/core/claude_self.md", "memory/MEMORY.md")
    git(archive, "commit", "--quiet", "-m", "core")
    write(archive / "memory/feedback_mine.md", memory("feedback_mine"))
    sources = {"sources": [{"path": str(store), "kind": "store"}], "groups": ["1:."]}

    refused = call(client, CLAUDE, "import", sources)
    moved = call(client, CLAUDE, "move-personal", {}).json()
    imported = call(client, CLAUDE, "import", sources).json()

    assert refused.status_code == 409
    assert moved["moved"] == ["personal/MEMORY.md", "personal/core/claude_self.md", "personal/feedback_mine.md"]
    root = archive / "memory"
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) == [
        "MEMORY.md",
        "feedback_a.md",
        "feedback_b.md",
        "personal/.private",
        "personal/MEMORY.md",
        "personal/core/claude_self.md",
        "personal/core/user_profile.md",
        "personal/core/user_working_relationship.md",
        "personal/core/watch_list.md",
        "personal/feedback_mine.md",
    ]
    assert git(archive, "log", "--follow", "--format=%s", "--", "memory/personal/core/claude_self.md").splitlines() == [
        "memory: link the core files to each other",
        "memory: move the personal memory into personal/",
        "core",
    ]
    assert imported["groups"][0]["copied"] == ["feedback_a.md", "feedback_b.md"]
    assert git(archive, "status", "--porcelain", "--", "memory") == ""


def test_a_plan_is_chosen_on_the_page_and_imported_as_chosen(
    client: TestClient, settings: Settings, trial: dict[str, str], store: Path, tmp_path: Path
) -> None:
    auto = tmp_path / "projects/-x/memory"
    write(auto / "feedback_ok.md", memory("feedback_ok"))
    write(auto / "MEMORY.md", "- feedback_ok.md — When feedback_ok\n")
    sources = [{"path": str(store), "kind": "store"}, {"path": str(auto), "kind": "loose", "target": "personal"}]

    created = client.post(
        "/api/v1/memory/migration/plans", json={"sources": sources, "session": "abcd1234"}, headers=trial
    )
    plan_id = created.json()["plan"]["id"]
    view = client.get(f"/api/v1/memory/migration/plans/{plan_id}?identity=trial", headers=ADMIN).json()
    other = client.post("/api/v1/identities", json={"id": "other"}, headers=ADMIN).json()["token"]
    hidden = client.get(
        f"/api/v1/memory/migration/plans/{plan_id}?identity=trial", headers={"Authorization": f"Bearer {other}"}
    )
    early = client.post(f"/api/v1/memory/migration/plans/{plan_id}/import", headers=trial)
    wrong_target = client.post(
        f"/api/v1/memory/migration/plans/{plan_id}/decisions",
        json={"identity": "trial", "targets": {"1": "acme"}, "groups": ["1:acme"]},
        headers=ADMIN,
    )
    sent = client.post(
        f"/api/v1/memory/migration/plans/{plan_id}/decisions",
        json={"identity": "trial", "targets": {"2": "acme/shop"}, "groups": ["1:.", "2:acme/shop"]},
        headers=ADMIN,
    ).json()
    imported = client.post(f"/api/v1/memory/migration/plans/{plan_id}/import", headers=trial).json()
    again = client.post(
        f"/api/v1/memory/migration/plans/{plan_id}/decisions",
        json={"identity": "trial", "groups": ["1:."]},
        headers=ADMIN,
    )

    assert created.status_code == 201
    assert (view["plan"]["identity"], view["plan"]["groups"], view["instance"]) == ("trial", None, "live")
    assert view["url"].endswith(f"/ui/settings/identities/trial/migrate?plan={plan_id}")
    assert [g["id"] for g in view["listing"]["groups"]] == ["1:.", "1:acme", "1:acme/shop", "1:acme/web", "2:personal"]
    assert hidden.status_code == 404
    assert early.status_code == 409
    assert wrong_target.status_code == 422
    assert (sent["typed"], sent["command"]) == (False, f"/whaat:memory-migrate import plan={plan_id}")
    assert [g["id"] for g in imported["groups"]] == ["1:.", "2:acme/shop"]
    root = trial_root(settings) / "memory"
    personal_files = [p for p in (root / "personal").glob("*.md") if p.name != "MEMORY.md"]
    assert (root / "acme/shop/feedback_ok.md").exists() and not personal_files
    assert not (root / "acme/feedback_g.md").exists()
    stored = client.get(f"/api/v1/memory/migration/plans/{plan_id}", headers=trial).json()["plan"]
    assert stored["imported_at"] and stored["result"]["groups"][1]["copied"] == ["acme/shop/feedback_ok.md"]
    assert again.status_code == 409


def test_a_decision_naming_an_unknown_group_changes_nothing(
    client: TestClient, trial: dict[str, str], store: Path
) -> None:
    plan_id = client.post(
        "/api/v1/memory/migration/plans", json={"sources": [{"path": str(store), "kind": "store"}]}, headers=trial
    ).json()["plan"]["id"]

    refused = client.post(
        f"/api/v1/memory/migration/plans/{plan_id}/decisions",
        json={"identity": "trial", "groups": ["1:nope"]},
        headers=ADMIN,
    )

    assert refused.status_code == 422
    assert client.get(f"/api/v1/memory/migration/plans/{plan_id}", headers=trial).json()["plan"]["groups"] is None


def test_the_summary_counts_every_list_so_the_agent_counts_nothing(
    client: TestClient, trial: dict[str, str], store: Path
) -> None:
    from whaat.memory import migration_summary

    view = client.post(
        "/api/v1/memory/migration/plans", json={"sources": [{"path": str(store), "kind": "store"}]}, headers=trial
    ).json()

    lines = migration_summary.plan(view).splitlines()

    assert lines[0] == f"plan: {view['plan']['id']}"
    assert [line.split()[:3] for line in lines[4:8]] == [
        ["1:.", "2", "2"],
        ["1:acme", "1", "1"],
        ["1:acme/shop", "1", "1"],
        ["1:acme/web", "1", "1"],
    ]
    assert "total: 5 files in 4 groups" in lines


def test_an_import_adds_the_default_core_files_the_core_lacks_and_keeps_the_ones_it_brings(
    client: TestClient, settings: Settings, trial: dict[str, str], store: Path, tmp_path: Path
) -> None:
    personal = tmp_path / "archive" / "memory"
    write(personal / "core/user_profile.md", memory("user-profile", "Their own profile."))
    write(personal / "MEMORY.md", "")
    sources = [{"path": str(store), "kind": "store"}, {"path": str(personal), "kind": "personal"}]

    imported = call(client, trial, "import", {"sources": sources, "groups": ["1:.", "2:personal"]}).json()

    core = trial_root(settings) / "memory" / "personal" / "core"
    assert imported["core_defaults"] == [
        "personal/core/agent_self.md",
        "personal/core/user_working_relationship.md",
        "personal/core/watch_list.md",
    ]
    assert (core / "user_profile.md").read_text() == memory("user-profile", "Their own profile.") + (
        "\nRelated: [[agent-self]], [[user-working-relationship]], [[watch-list]]\n"
    )
    names = {"agent_self": "agent-self", "user_profile": "user-profile"}
    names |= {"user_working_relationship": "user-working-relationship", "watch_list": "watch-list"}
    for stem, name in names.items():
        others = {f"[[{n}]]" for n in names.values() if n != name}
        assert others <= set(re.findall(r"\[\[[^\]]+\]\]", (core / f"{stem}.md").read_text())), stem
    assert sorted(imported["core_linked"]) == [f"personal/core/{stem}.md" for stem in sorted(names)]
    index = core.parent / "MEMORY.md"
    assert index.is_file()
    assert index.read_text().splitlines() == [
        "- core/agent_self.md — Who the agent is and who it wants to be in this work; read at the start of every"
        " session",
        "- core/user_working_relationship.md — How the user and the agent work together; read at the start of every"
        " session",
        "- core/watch_list.md — The mistakes that keep coming back; every agent reads it, subagents too",
    ]
    assert "reach: every-agent" in (core / "watch_list.md").read_text()
    assert git(trial_root(settings), "log", "-2", "--format=%s").splitlines() == [
        "memory: link the core files to each other",
        "memory: add the default core files agent_self.md, user_working_relationship.md, watch_list.md",
    ]
    assert git(trial_root(settings), "status", "--porcelain") == ""
    again = call(client, trial, "import", {"sources": sources, "groups": ["1:."]}).json()
    assert again["core_defaults"] == [] and again["core_linked"] == []


def test_an_import_names_the_brought_memories_that_link_to_none_and_none_to_them(
    client: TestClient, trial: dict[str, str], tmp_path: Path
) -> None:
    source = tmp_path / "linked"
    write(source / "feedback_links.md", memory("feedback_links", "See [[feedback_linked]]."))
    write(source / "feedback_linked.md", memory("feedback_linked"))
    write(source / "feedback_alone.md", memory("feedback_alone"))
    write(source / "MEMORY.md", "".join(f"- feedback_{n}.md — When {n}\n" for n in ("links", "linked", "alone")))

    imported = call(client, trial, "import", {"sources": [{"path": str(source), "kind": "store"}], "groups": ["1:."]})

    assert imported.json()["unlinked"] == ["feedback_alone.md"]


def test_a_memory_edited_here_since_its_import_is_edited_not_a_conflict(
    client: TestClient, settings: Settings, trial: dict[str, str], store: Path
) -> None:
    sources = {"sources": [{"path": str(store), "kind": "store"}], "groups": ["1:.", "1:acme"]}
    call(client, trial, "import", sources)
    root = trial_root(settings) / "memory"
    (root / "feedback_a.md").write_text(memory("feedback_a", "Do it. See [[feedback_b]]."))
    write(store / "acme/feedback_h.md", memory("feedback_h"))
    write(root / "acme/feedback_h.md", memory("feedback_h", "Put here by hand."))

    listed = call(client, trial, "groups", {"sources": sources["sources"]}).json()
    again = call(client, trial, "import", sources).json()

    by_id = {g["id"]: g for g in listed["groups"]}
    assert by_id["1:."]["edited"] == ["feedback_a.md"] and by_id["1:."]["conflicts"] == []
    assert by_id["1:acme"]["conflicts"] == ["acme/feedback_h.md"] and by_id["1:acme"]["edited"] == []
    assert again["groups"][0]["edited"] == ["feedback_a.md"] and again["groups"][0]["conflicts"] == []
    assert (root / "feedback_a.md").read_text() == memory("feedback_a", "Do it. See [[feedback_b]].")
