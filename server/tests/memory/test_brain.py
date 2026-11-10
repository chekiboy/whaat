import json

from whaat.distilled.schemas import DistilledGraph
from whaat.memory import brain
from whaat.memory.schemas import GraphNode, MemoryGraph


def node(name: str, trigger: str = "", type_: str = "feedback", path: str | None = None) -> GraphNode:
    return GraphNode(id=name, path=path or f"acme/shop/{name}.md", layer="repo", type=type_, trigger=trigger)


def left_share(nodes: list[GraphNode]) -> float:
    return sum(brain.side_of(n) == -1 for n in nodes) / len(nodes)


def test_language_leans_left_space_faces_and_tone_lean_right_and_a_mix_or_nothing_sits_in_between() -> None:
    assert brain.lean_left(node("feedback_minimal_comments", "Before adding a code comment")) == 0.8
    assert brain.lean_left(node("reference_render_harness", "Reviewing a frontend change")) == 0.2
    assert brain.lean_left(node("user_profile", "Who the user is", type_="user")) == 0.2
    assert brain.lean_left(node("feedback_tone", "When the conversation turns personal")) == 0.2
    assert brain.lean_left(node("feedback_docs_in_the_ui", "Writing text shown on a screen")) == 0.5
    assert brain.lean_left(node("project_sql_traps", "When a walkback query writes rows to docker")) == 0.5


def test_a_side_is_drawn_by_the_leaning_and_kept_for_the_same_path() -> None:
    language = [node(f"feedback_writing_{i}") for i in range(400)]
    spatial = [node(f"reference_chart_{i}") for i in range(400)]
    neutral = [node(f"project_queue_{i}") for i in range(400)]

    assert 0.74 < left_share(language) < 0.86
    assert 0.14 < left_share(spatial) < 0.26
    assert 0.43 < left_share(neutral) < 0.57
    assert [brain.side_of(n) for n in language] == [brain.side_of(n) for n in language]


def test_reference_sits_deep_in_its_hemisphere_and_the_cortex_types_on_the_surface() -> None:
    nodes = [node(f"reference_r{i}", type_="reference") for i in range(60)]
    nodes += [node(f"project_p{i}", type_="project") for i in range(60)]
    pos, _ = brain.positions(MemoryGraph(identity="t", nodes=nodes, edges=[]))

    for n in nodes:
        x, y, z = pos[n.id]
        inside = ((abs(x) - brain.CX) / brain.A) ** 2 + (y / brain.B) ** 2 + (z / brain.C) ** 2
        assert x * brain.side_of(n) > 0
        assert inside < 0.5 if n.type == "reference" else inside > 0.85


def distilled_graph() -> DistilledGraph:
    return DistilledGraph.model_validate(
        {
            "types": {t: {"label": t.title(), "color": "#fff"} for t in ("value", "lexicon", "rule", "gotcha", "old")},
            "kinds": {"grounds": {"label": "megalapoz", "color": "#f2c230"}},
            "nodes": [
                {"id": "v1", "type": "value", "label": "Átláthatóság", "mem": "feedback_a"},
                {"id": "l1", "type": "lexicon", "label": "Iránytű", "mem": "gone_memory"},
                {"id": "r1", "type": "rule", "label": "Push csak kérésre"},
                {"id": "g1", "type": "gotcha", "label": "zsh"},
                {"id": "o1", "type": "old", "label": "Soha ne pusholj"},
            ],
            "edges": [{"source": "v1", "target": "r1", "kind": "grounds"}],
        }
    )


def payload(html: str) -> dict:
    return json.loads(html.split("const D = ", 1)[1].split(";\n", 1)[0])


def test_the_distillate_joins_the_brain_linked_to_the_live_memory_it_names() -> None:
    live = MemoryGraph(identity="t", nodes=[node("feedback-a", path="acme/shop/feedback_a.md")], edges=[])
    data = payload(brain.render(live, distilled=distilled_graph()))
    nodes = {n["id"]: n for n in data["nodes"]}
    edges = {(e["source"], e["target"], e["kind"]) for e in data["edges"]}

    assert {"d:value", "d:lexicon", "feedback"} <= set(data["types"])
    assert edges == {("d:v1", "d:r1", "d:grounds"), ("d:v1", "feedback-a", "d:store")}
    assert (nodes["d:v1"]["linked"], nodes["d:l1"]["linked"]) == (True, False)
    assert abs(nodes["d:v1"]["p"][0]) < 0.05
    assert nodes["d:l1"]["p"][0] < -0.4
    assert nodes["d:o1"]["p"][1] < -0.4
    assert data["lobes"][nodes["d:l1"]["lobe"]].startswith("left temporal lobe")
    assert data["types"]["d:value"]["label"] == "Distillate · Value"
    hu = payload(brain.render(live, distilled=distilled_graph(), lang="hu"))
    assert hu["lobes"][nodes["d:l1"]["lobe"]].startswith("bal halántéklebeny")
    assert hu["types"]["d:value"]["label"] == "Desztillátum · Érték"


def test_without_a_distillate_the_brain_carries_only_the_live_memory() -> None:
    data = payload(brain.render(MemoryGraph(identity="t", nodes=[node("feedback-a")], edges=[])))

    assert data["distilled"] is None
    assert not [key for key in data["types"] if key.startswith("d:")]
