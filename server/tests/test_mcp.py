import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp.client import Client
from mcp.server.mcpserver.exceptions import ToolError

from tests.conftest import TOKEN, write
from tests.journal.samples import BLOCK
from tests.journal.samples import REPORT as SESSION_REPORT
from whaat.config import Settings
from whaat.mcp_server import IDENTITY_FIRST, INSTRUCTIONS, INSTRUCTIONS_BUDGET, build

ADMIN = {"Authorization": f"Bearer {TOKEN}"}
SESSION = "0123abcd"
ENV = {"CLAUDE_CODE_SESSION_ID": SESSION + "-4567-89ab-cdef-0123456789ab"}
CONTENT = "---\nname: feedback_x\ndescription: When x\ntype: feedback\n---\nDo x.\n"
SKILL_CALLS = {
    "identity_load": ("POST", "/api/v1/memory/recall/start"),
    "journal_discarded": ("GET", "/api/v1/curation/discarded"),
    "journal_save": ("POST", "/api/v1/journal/entries"),
    "journal_save_applied": ("POST", "/api/v1/journal/curation-reports/applied"),
    "journal_save_curation": ("POST", "/api/v1/journal/curation-reports"),
    "journal_save_report": ("POST", "/api/v1/journal/session-reports"),
    "memory_curation_brief": ("POST", "/api/v1/memory/curation-brief"),
    "memory_curation_refute_brief": ("POST", "/api/v1/memory/curation-refute-brief"),
    "memory_delete": ("DELETE", "/api/v1/memory/memories/{path}"),
    "memory_dump": ("POST", "/api/v1/memory/recall/dump"),
    "memory_fidelity": ("POST", "/api/v1/memory/fidelity"),
    "memory_import": ("POST", "/api/v1/memory/migration/import"),
    "memory_index": ("POST", "/api/v1/memory/recall/index"),
    "memory_lint": ("POST", "/api/v1/memory/lint"),
    "memory_migration_plan": ("POST", "/api/v1/memory/migration/plans"),
    "memory_move_personal": ("POST", "/api/v1/memory/migration/move-personal"),
    "memory_open": ("POST", "/api/v1/memory/recall/open"),
    "memory_reads": ("POST", "/api/v1/memory/outcome/reads"),
    "memory_record": ("POST", "/api/v1/memory/outcome/record"),
    "memory_revert": ("POST", "/api/v1/memory/revert"),
    "memory_save": ("POST", "/api/v1/memory/memories"),
    "memory_where": ("GET", "/api/v1/memory/where"),
    "report_open": ("POST", "/api/v1/reports/{report_id}/open"),
}

SECOND_ROUTES = {("POST", "/api/v1/memory/recall/frame"), ("POST", "/api/v1/memory/migration/plans/{plan_id}/import")}


@pytest.fixture
def token(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(write(tmp_path / "gitconfig", "[user]\n\tname = T\n\temail = t@x\n")))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    return str(client.post("/api/v1/identities", json={"id": "trial"}, headers=ADMIN).json()["token"])


def calls(
    client: TestClient, settings: Settings, token: str, *steps: tuple[str, dict[str, Any]], env: dict[str, str] = ENV
) -> list[Any]:
    """Run tool calls through an in-memory MCP client; the server's HTTP goes to the test app."""

    send = direct(client)

    async def run() -> list[Any]:
        async with Client(build(settings, token, env, send)) as mcp:
            return [await mcp.call_tool(name, args) for name, args in steps]

    return anyio.run(run)


def test_the_tools_are_the_skills_calls_and_each_route_exists(client: TestClient, settings: Settings) -> None:
    async def names() -> list[str]:
        async with Client(build(settings, "unused", ENV, lambda *_: (401, b'{"detail": "no token"}'))) as mcp:
            return [tool.name for tool in (await mcp.list_tools()).tools]

    routes = {(m.upper(), p) for p, ops in client.app.openapi()["paths"].items() for m in ops}  # type: ignore[attr-defined]

    assert sorted(anyio.run(names)) == sorted(SKILL_CALLS)
    assert {name: route for name, route in SKILL_CALLS.items() if route not in routes} == {}
    assert routes >= SECOND_ROUTES


def test_a_saved_memory_is_indexed_and_every_recall_open_returns_its_text_under_the_clients_session(
    client: TestClient, settings: Settings, token: str
) -> None:
    save = {"path": "acme/shop/feedback_x.md", "content": CONTENT, "trigger": "When x"}
    opening = {"file": "acme/shop/feedback_x.md", "because": "x is what the task does"}

    saved, index, first, again = calls(
        client,
        settings,
        token,
        ("memory_save", save),
        ("memory_index", {"task": "doing x in the shop", "repo": "acme/shop"}),
        ("memory_open", opening),
        ("memory_open", opening),
    )

    assert not saved.is_error
    listing = index.content[0].text
    assert "## repo: acme/shop/\n- acme/shop/feedback_x.md — When x\n" in listing
    assert "Open a memory only through the memory_open tool" in listing
    assert "whaat memory open" not in listing
    assert listing.endswith("That was the last part (1 of 1).\n")
    assert first.content[0].text.startswith("Memory: acme/shop/feedback_x.md")
    assert "Do x." in first.content[0].text
    assert again.content[0].text == first.content[0].text
    log = settings.state_dir / "identities" / "trial" / "state" / "memory-recall.log"
    ops = [(e["op"], e.get("session")) for e in map(json.loads, log.read_text().splitlines())]
    assert ops == [("index", SESSION), ("open", SESSION), ("inject", SESSION), ("open", SESSION), ("inject", SESSION)]


def test_a_refusal_comes_back_as_a_tool_error_in_the_servers_words(
    client: TestClient, settings: Settings, token: str
) -> None:
    (deleted,) = calls(client, settings, token, ("memory_delete", {"path": "acme/shop/none.md"}))

    detail = client.delete("/api/v1/memory/memories/acme/shop/none.md", headers={"Authorization": f"Bearer {token}"})
    assert deleted.is_error
    assert deleted.content[0].text == f"Error executing tool memory_delete: {detail.json()['detail']}"


def test_the_journal_is_kept_under_the_clients_session_and_where_reads_its_project_dir(
    client: TestClient, settings: Settings, token: str, tmp_path: Path
) -> None:
    repo = tmp_path / "shop"
    repo.mkdir()
    for args in (["init", "-q"], ["remote", "add", "origin", "git@example.com:acme/shop.git"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True)

    saved, where = calls(
        client,
        settings,
        token,
        ("journal_save", {"block": BLOCK}),
        ("memory_where", {}),
        env={**ENV, "CLAUDE_PROJECT_DIR": str(repo)},
    )

    assert json.loads(saved.content[0].text)["report_id"].endswith(f"_{SESSION}.json")
    assert json.loads(where.content[0].text)["repo"].endswith("/memory/acme/shop")


def test_without_a_client_session_a_process_keeps_one_of_its_own(
    client: TestClient, settings: Settings, token: str
) -> None:
    first, second = calls(
        client,
        settings,
        token,
        ("memory_index", {"task": "doing x in the shop"}),
        ("memory_index", {"task": "doing y in the shop"}),
        env={},
    )

    assert not first.is_error, first.content[0].text
    assert not second.is_error
    log = settings.state_dir / "identities" / "trial" / "state" / "memory-recall.log"
    sessions = {json.loads(line)["session"] for line in log.read_text().splitlines()}
    assert len(sessions) == 1 and sessions != {SESSION} and len(sessions.pop()) == 8


def test_every_other_tool_reaches_its_route_with_a_body_the_route_accepts(
    client: TestClient, settings: Settings, token: str, tmp_path: Path
) -> None:
    client.app.state.open_url = lambda url, browser: None  # type: ignore[attr-defined]
    recipe = "---\nname: reference_old_recipe\ndescription: d\ntype: reference\n---\nB.\n"
    source = write(tmp_path / "loose/feedback_y.md", CONTENT.replace("feedback_x", "feedback_y")).parent
    row = {
        "n": 1,
        "file": "acme/shop/reference_old_recipe.md",
        "actions": ["verify"],
        "target": None,
        "reason": "stale at 0.35",
        "evidence": None,
    }
    saved, saved_curation = calls(
        client,
        settings,
        token,
        ("memory_save", {"path": "acme/shop/reference_old_recipe.md", "content": recipe, "trigger": "When x"}),
        ("journal_save_curation", {"report": {"lint_summary": "1 index", "rows": [row], "unchecked": "None."}}),
    )
    assert not saved_curation.is_error, saved_curation.content[0].text
    curation = calls(client, settings, token, ("journal_discarded", {}))[0]
    session_report = calls(
        client, settings, token, ("journal_save_report", {"slug": "probe", "report": SESSION_REPORT})
    )[0]
    report_id = json.loads(session_report.content[0].text)["report_id"]
    curation_id = next(
        r["id"]
        for r in client.get("/api/v1/reports", headers={"Authorization": f"Bearer {token}"}).json()
        if r["envelope"]["kind"] == "memory-curation"
    )
    sources = [{"path": str(source), "kind": "loose", "target": "acme/shop"}]
    plan = json.loads(
        calls(client, settings, token, ("memory_migration_plan", {"sources": sources}))[0].content[0].text
    )
    groups = [group["id"] for group in plan["listing"]["groups"]]
    results = calls(
        client,
        settings,
        token,
        ("memory_dump", {"dir": "acme/shop", "purpose": "review", "because": "checking the dump tool"}),
        ("memory_reads", {}),
        ("memory_lint", {}),
        ("memory_curation_brief", {"dir": "acme/shop"}),
        ("memory_curation_refute_brief", {"dir": "acme/shop", "rows": [row]}),
        (
            "memory_fidelity",
            {"file": "acme/shop/reference_old_recipe.md", "new": ["acme/shop/reference_old_recipe.md"]},
        ),
        ("journal_save_applied", {"report_id": curation_id, "rows": [{"n": 1, "applied": None}]}),
        ("report_open", {"report_id": report_id}),
        ("memory_import", {"sources": sources, "groups": groups}),
        ("memory_move_personal", {}),
        ("memory_revert", {"commits": [json.loads(saved.content[0].text)["commit"]]}),
    )

    assert not saved.is_error and not curation.is_error and not session_report.is_error
    assert groups
    assert [r.content[0].text[:120] for r in results if r.is_error] == []


def test_a_memory_past_the_hooks_size_cap_comes_back_whole(client: TestClient, settings: Settings, token: str) -> None:
    long = CONTENT + "Long line of the recipe.\n" * 500
    opening = {"file": "acme/shop/feedback_x.md", "because": "x is what the task does"}

    _, opened = calls(
        client,
        settings,
        token,
        ("memory_save", {"path": "acme/shop/feedback_x.md", "content": long, "trigger": "When x"}),
        ("memory_open", opening),
    )
    hook = client.post(
        "/api/v1/memory/recall/frame",
        json={"session": "feedc0de", "opened": [json.loads(opened_line(settings))]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert len(long) > 9500
    assert opened.content[0].text.rstrip().endswith("Long line of the recipe.")
    assert "not put in" in hook.json()["context"]


def opened_line(settings: Settings) -> str:
    path = settings.state_dir / "identities" / "trial" / "memory" / "acme" / "shop" / "feedback_x.md"
    return json.dumps({"file": "acme/shop/feedback_x.md", "path": str(path)})


def test_the_instructions_say_when_each_tool_is_for() -> None:
    assert [name for name in SKILL_CALLS if name not in IDENTITY_FIRST + INSTRUCTIONS] == []


def test_an_outcome_counts_when_it_came_after_the_last_change_even_on_the_same_day(
    client: TestClient, settings: Settings, token: str
) -> None:
    import datetime

    save = {"path": "acme/shop/feedback_x.md", "content": CONTENT, "trigger": "When x"}
    opening = {"file": "acme/shop/feedback_x.md", "because": "x is what the task does"}
    calls(client, settings, token, ("memory_save", save))
    now = datetime.datetime.now().astimezone()
    log = settings.state_dir / "identities" / "trial" / "state" / "memory-outcomes.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        f"{now.date().isoformat()}\tmisled\tacme/shop/feedback_x.md\told-day-line\n"
        f"{(now - datetime.timedelta(hours=1)).isoformat(timespec='seconds')}\tmisled\tacme/shop/feedback_x.md\tb4\n"
    )

    _, opened = calls(
        client,
        settings,
        token,
        ("memory_record", {"outcome": "held", "paths": ["acme/shop/feedback_x.md"]}),
        ("memory_open", opening),
    )

    assert "since its last change held 1, misled 0, irrelevant 0" in opened.content[0].text


def test_a_curation_brief_over_mcp_tells_its_agent_to_read_the_dir_with_the_mcp_tool(
    client: TestClient, settings: Settings, token: str
) -> None:
    save = {"path": "acme/shop/feedback_x.md", "content": CONTENT, "trigger": "When x"}
    _, judge, refuter = calls(
        client,
        settings,
        token,
        ("memory_save", save),
        ("memory_curation_brief", {"dir": "acme/shop"}),
        ("memory_curation_refute_brief", {"dir": "acme/shop", "rows": []}),
    )
    cli = client.post(
        "/api/v1/memory/curation-brief", json={"dir": "acme/shop"}, headers={"Authorization": f"Bearer {token}"}
    )

    for brief in (judge.content[0].text, refuter.content[0].text):
        assert 'memory_dump(dir="acme/shop", purpose="curate"' in brief
        assert "scripts/whaat" not in brief
    assert "scripts/whaat memory dump dir=acme/shop" in cli.json()["text"]


def test_the_token_alone_decides_whose_core_is_loaded(client: TestClient, settings: Settings, token: str) -> None:
    other = str(client.post("/api/v1/identities", json={"id": "other"}, headers=ADMIN).json()["token"])

    def core(who: str) -> dict[str, str]:
        content = f"---\nname: self\ndescription: Who I am\ntype: feedback\n---\nI am {who}.\n"
        return {"path": "personal/core/self.md", "content": content, "trigger": "Who I am"}

    calls(client, settings, token, ("memory_save", core("the trial identity")))
    calls(client, settings, other, ("memory_save", core("the other identity")))

    send = direct(client)

    async def connect(as_token: str) -> tuple[str, str]:
        async with Client(build(settings, as_token, ENV, send)) as mcp:
            loaded = await mcp.call_tool("identity_load", {})
            return mcp.instructions or "", loaded.content[0].text

    seen = {
        name: anyio.run(connect, as_token)
        for name, as_token in [("trial", token), ("other", other), ("admin", TOKEN), ("wrong", "nope")]
    }

    assert all("I am the trial identity." in text and "other identity" not in text for text in seen["trial"])
    assert all("I am the other identity." in text and "trial identity" not in text for text in seen["other"])
    for refused in ("admin", "wrong"):
        assert not any("I am the" in text for text in seen[refused]), refused
    assert "the admin token names no identity" in seen["admin"][0]


def direct(client: TestClient) -> Any:
    """The MCP server's HTTP, sent to the test app instead of a running server."""

    def send(method: str, url: str, data: bytes | None, headers: dict[str, str]) -> tuple[int, bytes]:
        parts = urlsplit(url)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        response = client.request(method, path, content=data, headers=headers)
        return response.status_code, response.content

    return send


def connect(settings: Settings, token: str, send: Any) -> tuple[str, str]:
    async def run() -> tuple[str, str]:
        async with Client(build(settings, token, ENV, send)) as mcp:
            loaded = await mcp.call_tool("identity_load", {})
            return mcp.instructions or "", loaded.content[0].text

    return anyio.run(run)


def core_file(name: str, body: str) -> dict[str, str]:
    content = f"---\nname: {name}\ndescription: About {name}\ntype: feedback\n---\n{body}"
    return {"path": f"personal/core/{name}.md", "content": content, "trigger": f"About {name}"}


def test_the_instructions_ask_for_identity_load_first_and_carry_only_the_cores_outline(
    client: TestClient, settings: Settings, token: str
) -> None:
    body = "I am the trial identity. I like long walks through the code.\n**Why:** a test.\n"
    calls(client, settings, token, ("memory_save", core_file("claude_self", body)))

    instructions, loaded = connect(settings, token, direct(client))

    assert instructions.startswith(IDENTITY_FIRST)
    assert "- personal:core/claude_self.md — About claude_self: I am the trial identity.\n" in instructions
    assert "long walks" not in instructions and "long walks" in loaded
    log = settings.state_dir / "identities" / "trial" / "state" / "memory-recall.log"
    loads = [e for e in map(json.loads, log.read_text().splitlines()) if e.get("purpose") == "load"]
    assert [(e["file"], e["session"]) for e in loads] == [("personal:core/claude_self.md", SESSION)]


def test_a_core_past_the_hooks_cap_comes_whole_through_identity_load_and_the_outline_stays_in_budget(
    client: TestClient, settings: Settings, token: str
) -> None:
    steps = [
        ("memory_save", core_file(f"feedback_{n:02}", f"Core file {n}. " + "A line.\n" * 300 + f"END {n}\n"))
        for n in range(40)
    ]
    calls(client, settings, token, *steps)

    instructions, loaded = connect(settings, token, direct(client))

    assert len(instructions) <= INSTRUCTIONS_BUDGET
    assert instructions.endswith(INSTRUCTIONS)
    assert "- … (the rest in identity_load)" in instructions
    assert all(f"END {n}" in loaded for n in range(40))
    assert "memory open file=" not in loaded


def test_without_a_core_or_a_server_the_instructions_say_so_and_nothing_breaks(
    client: TestClient, settings: Settings, token: str
) -> None:
    def down(*_: Any) -> tuple[int, bytes]:
        raise ToolError("whaat does not answer")

    async def instructions(send: Any) -> str:
        async with Client(build(settings, token, ENV, send)) as mcp:
            return mcp.instructions or ""

    assert "(this identity keeps no personal core yet)" in anyio.run(instructions, direct(client))
    assert "could not be read at connect: whaat does not answer" in anyio.run(instructions, down)


def test_the_purposes_the_tools_take_are_the_ones_recall_knows() -> None:
    import typing

    from whaat.mcp_server import DumpPurpose, Purpose
    from whaat.memory.recall import DUMP_PURPOSES, PURPOSES

    assert set(typing.get_args(Purpose)) == set(PURPOSES) - {"load"}
    assert set(typing.get_args(DumpPurpose)) == set(DUMP_PURPOSES)
