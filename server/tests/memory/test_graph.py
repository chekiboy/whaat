import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TOKEN, write
from whaat.config import Settings
from whaat.memory import brain, rings

ADMIN = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def fresh_pages() -> None:
    brain._cache.clear()
    rings._cache.clear()


@pytest.fixture
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = write(tmp_path / "gitconfig", "[user]\n\tname = Test\n\temail = test@example.com\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def trial(client: TestClient, settings: Settings, isolated_git: None) -> dict[str, str]:
    token = client.post("/api/v1/identities", json={"id": "trial"}, headers=ADMIN).json()["token"]
    memory = settings.state_dir / "identities" / "trial" / "memory"
    write(memory / "acme/shop/MEMORY.md", "- feedback_a.md — When a\n- feedback_b.md — When b\n")
    write(
        memory / "acme/shop/feedback_a.md",
        "---\nname: feedback-a\ndescription: When a\ntype: feedback\nwhen: [push, review]\n---\n"
        "A. See [[feedback-b]], [[feedback-b]] and [[gone]].\n",
    )
    write(
        memory / "acme/shop/feedback_b.md",
        "---\nname: feedback-b\ndescription: When b\ntype: feedback\n"
        "supersedes: feedback_old\nconfirmed: 2026-10-01\n---\nB.\n",
    )
    write(memory / "acme/shop/feedback_old.md", "---\nname: feedback-old\ndescription: When old\n---\nOld.\n")
    write(memory / "personal/user_x.md", "---\nname: user-x\ntype: user\n---\nX, see [[feedback-a]].\n")
    return {"Authorization": f"Bearer {token}"}


def test_the_graph_has_a_node_per_memory_an_edge_per_link_and_supersedes_and_a_ghost_per_dangling_link(
    client: TestClient, trial: dict[str, str]
) -> None:
    graph = client.get("/api/v1/memory/graph", headers=trial).json()
    nodes = {node["id"]: node for node in graph["nodes"]}

    assert graph["identity"] == "trial"
    assert sorted(nodes) == ["feedback-a", "feedback-b", "feedback-old", "gone", "user-x"]
    a = nodes["feedback-a"]
    assert (a["path"], a["layer"], a["dir"], a["type"], a["trigger"], a["when"], a["indexed"]) == (
        "acme/shop/feedback_a.md",
        "repo",
        "acme/shop",
        "feedback",
        "When a",
        ["push", "review"],
        True,
    )
    assert (a["validity"]["level"], nodes["feedback-b"]["validity"]["level"]) == (None, "certain")
    assert (nodes["feedback-old"]["indexed"], nodes["feedback-old"]["validity"]["history"]) == (
        False,
        "acme/shop/feedback_b.md",
    )
    assert (nodes["user-x"]["layer"], nodes["user-x"]["validity"]) == ("personal", None)
    assert (nodes["gone"]["ghost"], nodes["gone"]["path"]) == (True, None)
    assert sorted((e["source"], e["target"], e["kind"]) for e in graph["edges"]) == [
        ("feedback-a", "feedback-b", "link"),
        ("feedback-a", "gone", "link"),
        ("feedback-b", "feedback-old", "supersedes"),
        ("user-x", "feedback-a", "link"),
    ]


def test_a_token_reads_only_its_own_graph_and_the_admin_names_one(client: TestClient, trial: dict[str, str]) -> None:
    other = client.get("/api/v1/memory/graph", params={"identity": "someone"}, headers=trial)
    unnamed = client.get("/api/v1/memory/graph", headers=ADMIN)
    named = client.get("/api/v1/memory/graph", params={"identity": "trial"}, headers=ADMIN)
    unknown = client.get("/api/v1/memory/graph", params={"identity": "nobody"}, headers=ADMIN)

    assert other.json()["identity"] == "trial"
    assert unnamed.status_code == 422
    assert len(named.json()["nodes"]) == 5
    assert unknown.status_code == 404


def test_the_brain_page_carries_the_graph_the_core_on_the_midline_history_and_ghosts_in_the_cerebellum(
    client: TestClient, settings: Settings, trial: dict[str, str]
) -> None:
    write(
        settings.state_dir / "identities/trial/memory/personal/core/user_me.md",
        "---\nname: user-me\ntype: user\n---\nMe.\n",
    )
    page = client.get("/api/v1/memory/brain", headers=trial)
    data = json.loads(page.text.split("const D = ", 1)[1].split(";\n", 1)[0])
    nodes = {node["id"]: node for node in data["nodes"]}

    assert page.headers["content-type"].startswith("text/html")
    assert data["kicker"].startswith("Memory · trial · 6 memories")
    assert data["types"]["other"]["label"] == "No type"
    hu_page = client.get("/api/v1/memory/brain", params={"lang": "hu"}, headers=trial)
    hu = json.loads(hu_page.text.split("const D = ", 1)[1].split(";\n", 1)[0])
    assert hu["kicker"].startswith("Memória · trial · 6 memória")
    assert (hu["types"]["other"]["label"], hu["lobes"]["core"]) == ("Típus nélkül", "középvonal (mediális kéreg)")
    assert (nodes["user-me"]["lobe"], nodes["user-me"]["p"][0]) == ("core", 0.0)
    assert (nodes["feedback-a"]["lobe"], nodes["user-x"]["lobe"]) == ("feedback", "user")
    assert all(abs(nodes[name]["p"][0]) > 0.4 for name in ("feedback-a", "user-x"))
    assert (nodes["feedback-old"]["type"], nodes["gone"]["type"]) == ("old", "old")
    assert all(nodes[name]["p"][1] < -0.4 for name in ("feedback-old", "gone"))
    assert client.get("/api/v1/memory/brain", headers=ADMIN).status_code == 422


def test_the_rings_page_puts_the_memory_dirs_as_themes_in_layer_order_and_levels_from_validity(
    client: TestClient, trial: dict[str, str]
) -> None:
    page = client.get("/api/v1/memory/rings", headers=trial)
    data = json.loads(page.text.split("const D = ", 1)[1].split(";\n", 1)[0])
    cards = {card["id"]: card for card in data["cards"]}

    assert list(data["themes"].values()) == ["Personal · personal", "Repo · acme/shop"]
    assert (cards["feedback-b"]["level"], cards["feedback-a"]["level"], cards["user-x"]["level"]) == (
        "certain",
        "unscored",
        "unscored",
    )
    assert (cards["feedback-old"]["kind"], cards["feedback-old"]["superseded_by"]) == ("old", "feedback-b")
    assert cards["feedback-a"]["when"] == ["push", "review"]
    assert data["kicker"].startswith("Memory · trial · 3 memories · 2 themes")
    assert (data["levelLabels"]["certain"], data["coreLabel"]) == ("certain", "Core")

    hu_page = client.get("/api/v1/memory/rings", params={"lang": "hu"}, headers=trial)
    hu = json.loads(hu_page.text.split("const D = ", 1)[1].split(";\n", 1)[0])
    assert list(hu["themes"].values()) == ["Személyes · personal", "Repó · acme/shop"]
    assert hu["kicker"].startswith("Memória · trial · 3 memória · 2 téma")
    assert (hu["levelLabels"]["certain"], hu["levelLabels"]["unscored"], hu["coreLabel"]) == (
        "biztos",
        "nincs pontozva",
        "Mag",
    )
    assert {card["id"]: card["level"] for card in hu["cards"]}["feedback-b"] == "certain"


def test_the_brain_draws_a_kept_distillate_linked_to_the_live_memory(
    client: TestClient, settings: Settings, trial: dict[str, str]
) -> None:
    graph = {
        "types": {"value": {"label": "Érték", "color": "#f2c230"}},
        "kinds": {},
        "nodes": [{"id": "v1", "type": "value", "label": "Átláthatóság", "mem": "feedback_a"}],
        "edges": [],
    }
    write(settings.state_dir / "identities/trial/distilled/graph/graph.json", json.dumps(graph))
    page = client.get("/api/v1/memory/brain", headers=trial)
    data = json.loads(page.text.split("const D = ", 1)[1].split(";\n", 1)[0])

    assert data["distilled"] is not None
    assert ("d:v1", "feedback-a", "d:store") in {(e["source"], e["target"], e["kind"]) for e in data["edges"]}


def test_the_analysis_serves_the_kept_distillate_sets_and_my_reading_and_needs_a_distillate(
    client: TestClient, settings: Settings, trial: dict[str, str]
) -> None:
    sets = {
        "batches": ["09-02→09-22", "09-23→10-01"],
        "heat": [{"id": "f1", "label": "Kihagyott kapu", "ep": [1], "mention": [2], "verdict": "MARAD", "note": "n"}],
        "phases": [{"span": "09-02 → 09-23", "title": "Határok", "me": "m", "robi": "r"}],
        "ladder": [{"date": "09-17", "text": "Push csak kérésre."}],
        "changed": [{"date": "09-17", "old": "Soha ne pusholj", "new": "Push csak kifejezett kérésre"}],
        "hubs": [{"id": "9be49ccb", "date": "10-15", "n": "21", "text": "Identitás."}],
    }
    graph = {
        "types": {"failure": {"label": "Visszatérő hiba", "color": "#e0442b"}},
        "kinds": {},
        "nodes": [
            {"id": "f0", "type": "failure", "label": "Korábbi", "date": "2026-10-01"},
            {"id": "f1", "type": "failure", "label": "Kihagyott kapu", "date": "2026-10-16"},
        ],
        "edges": [],
    } | sets
    reading = {"title": "Merre mutat", "paragraphs": [{"lead": "A te íved:", "text": "t"}], "caveats": ["c"]}
    folder = settings.state_dir / "identities/trial/distilled/graph"
    missing = client.get("/api/v1/memory/analysis", headers=trial)
    write(folder / "graph.json", json.dumps(graph))
    unread = client.get("/api/v1/memory/analysis", headers=trial).json()
    write(folder / "reading.json", json.dumps(reading))
    analysis = client.get("/api/v1/memory/analysis", headers=trial).json()

    assert missing.status_code == 404
    assert unread["reading"] is None
    phases = [{"span": "09-02 → 09-23", "title": "Határok", "me": "m", "user": "r"}]
    assert {key: analysis[key] for key in sets} == sets | {"phases": phases}
    assert (analysis["first"], analysis["last"], analysis["reading"]) == ("2026-09-02", "2026-10-16", reading)
