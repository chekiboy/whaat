"""The Emlékagy (distilled/build_brain.py and brain_template.html) on an identity's live memory: the graph's nodes as
neurons in a fibre brain, rotatable in 3D, rendered here so the page is the template's own, not a rewrite.

Laid out as memory systems sit in a brain: the core on the midline, where self-related memory is
(medial prefrontal and posterior cingulate cortex); a region per type, in both hemispheres; a side per memory leaning
as the brain lateralizes, language left, spatial attention, faces and the melody of speech right, read from its name
and trigger by keyword. Superseded memories and ghosts sit faded where the cerebellum is. Positions are computed
here, deterministically, as build_brain.py computes them.
"""

import hashlib
import json
import math
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from whaat.distilled.schemas import DistilledGraph
from whaat.memory.labels import Language, label
from whaat.memory.schemas import GraphNode, MemoryGraph

TEMPLATE = Path(__file__).parent / "views" / "brain_template.html"
TYPE_COLOUR = {
    "feedback": "#f08a24",
    "project": "#3aa58c",
    "reference": "#2e78c2",
    "user": "#e0442b",
    "other": "#9a8f7a",
    "old": "#b0a28a",
}
KIND_COLOUR = {"link": "#8a7f6a", "supersedes": "#b0a28a"}
LATERAL = {  # p(left) by what a memory is about
    "language": (
        0.8,
        re.compile(
            r"\b(writing|written|prose|text|comments?|docblocks?|docs?|documents?|documentation|confluence|jira"
            r"|description|quote|sentences?|words?|wording|naming|language|hungarian|english|spec|brief|message)\b"
        ),
    ),
    "spatial": (
        0.2,
        re.compile(
            r"\b(ui|frontend|render\w*|screen|layout|css|diagram|svg|visual\w*|browser|playwright|chart|view"
            r"|styl(e|ing)|webgl|three\.js|brain|rings|graph|colou?r)\b"
        ),
    ),
    "faces": (0.2, re.compile(r"\b(who|person|people|teammates?|colleagues?)\b")),
    "prosody": (0.2, re.compile(r"\b(tone|voice|mood|emoji|feelings?|conversation|talk\w*|humou?r)\b")),
}
LOBE = {  # direction in hemisphere-local unit coords: x outward (sign by hemisphere), y up, z front
    "feedback": (0.30, 0.55, 0.78),
    "user": (0.62, 0.15, 0.77),
    "project": (0.86, -0.38, 0.05),
    "other": (0.42, 0.12, -0.90),
}
DEEP = (0.32, -0.05, 0.12)  # reference: the basal ganglia, inside each hemisphere (|x|, y, z of the centre)
LOBES = ["feedback", "user", "reference", "project", "other", "core", "old"]
CX, A, B, C = 0.43, 0.42, 0.58, 1.0

D = "d:"  # the distillate's types, kinds and node ids, apart from the memory's
D_STORE_COLOUR = "#6f8fc9"
# my mapping (2026-11-02): who I am on the medial wall front to back, words in the left temporal lobe (language),
# rules in front, gotchas deep with the recipes
D_MEDIAL = {"value": 0.55, "identity": 0.25, "strength": -0.15, "failure": -0.45}
D_SURFACE = {"lexicon": (0.80, -0.10, -0.35), "rule": (0.42, 0.68, 0.60)}
D_DEEP = {"gotcha": (0.30, -0.14, -0.10)}
D_LOBES = ["medial", "lexicon", "rule", "gotcha", "old"]


def kind_of(node: GraphNode) -> str:
    if node.ghost or (node.validity and node.validity.history):
        return "old"
    return node.type if node.type in ("feedback", "project", "reference", "user") else "other"


def region_of(node: GraphNode) -> str:
    kind = kind_of(node)
    return "core" if kind != "old" and node.layer == "core" else kind


def lean_left(node: GraphNode) -> float:
    """p(left): the mean of the matching groups' leanings, 0.5 when none matches."""
    text = f"{label_of(node.id)} {node.trigger or ''}".lower()
    leans = [p for key, (p, rx) in LATERAL.items() if rx.search(text) or (key == "faces" and node.type == "user")]
    return sum(leans) / len(leans) if leans else 0.5


def side_of(node: GraphNode) -> int:
    """-1 left, 1 right, drawn by the path's hash against lean_left, so a memory keeps its side between renders."""
    draw = int(hashlib.sha1((node.path or node.id).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return -1 if draw < lean_left(node) else 1


def label_of(node_id: str) -> str:
    return re.sub(r"[_-]+", " ", re.sub(r"^(feedback|project|reference|user)[_-]", "", node_id))


def _norm(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(x * x for x in v)) or 1.0
    return (v[0] / length, v[1] / length, v[2] / length)


def _basis(d: tuple[float, float, float]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    up = (0.0, 1.0, 0.0) if abs(d[1]) < 0.9 else (1.0, 0.0, 0.0)
    u = _norm((up[1] * d[2] - up[2] * d[1], up[2] * d[0] - up[0] * d[2], up[0] * d[1] - up[1] * d[0]))
    w = (d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0])
    return u, w


def positions(graph: MemoryGraph) -> tuple[dict[str, tuple[float, float, float]], dict[str, int]]:
    """build_brain.py's layout: each (region, side) group spread on a sunflower around its lobe direction, best
    connected first; the core along the midline, reference in a ball deep in each hemisphere, superseded memories
    and ghosts on the cerebellum."""
    degree = {n.id: 0 for n in graph.nodes}
    for e in graph.edges:
        degree[e.source] = degree.get(e.source, 0) + 1
        degree[e.target] = degree.get(e.target, 0) + 1
    groups: dict[tuple[str, int], list[GraphNode]] = {}
    for n in graph.nodes:
        region = region_of(n)
        side = 0 if region in ("old", "core") else side_of(n)
        groups.setdefault((region, side), []).append(n)
    pos: dict[str, tuple[float, float, float]] = {}
    for (region, side), members in groups.items():
        members.sort(key=lambda n: (-degree[n.id], n.id))
        count = len(members)
        for k, n in enumerate(members):
            if region == "old":
                pos[n.id] = _cerebellum(k, count)
            elif region == "core":  # front to back along the cingulate arc, in the fissure
                t = (k + 0.5) / count
                pos[n.id] = (0.0, B * (0.10 + 0.40 * math.sin(math.pi * t)), C * (0.60 - 0.95 * t))
            elif region == "reference":  # a Fibonacci ball, best connected nearest its centre
                pos[n.id] = _ball(k, count, side, DEEP)
            else:
                pos[n.id] = _surface(k, count, side, LOBE[region])
    return pos, degree


def _hash_side(key: str) -> int:
    return -1 if int(hashlib.sha1(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < 0.5 else 1


def _cerebellum(k: int, count: int) -> tuple[float, float, float]:
    t, phi = (k + 0.5) / count, k * 2.39996
    x = 0.42 * math.sqrt(t) * math.cos(phi)
    return (0.8 * x, -0.50 + 0.07 * math.sin(phi), -0.70 + 0.12 * math.sqrt(t) * math.sin(phi))


def _ball(k: int, count: int, side: int, centre: tuple[float, float, float]) -> tuple[float, float, float]:
    radius = 0.06 + 0.012 * math.sqrt(count)
    phi = k * 2.39996
    y = 1 - 2 * ((k * 0.618034) % 1)
    rr = radius * ((k + 0.5) / count) ** (1 / 3)
    ring = math.sqrt(max(0.0, 1 - y * y))
    return (side * (centre[0] + rr * ring * math.cos(phi)), centre[1] + rr * y, centre[2] + rr * ring * math.sin(phi))


def _surface(k: int, count: int, side: int, lobe: tuple[float, float, float]) -> tuple[float, float, float]:
    d = _norm(lobe)
    u, w = _basis(d)
    t, phi = (k + 0.5) / count, k * 2.39996
    theta = (0.28 + 0.065 * math.sqrt(count)) * math.sqrt(t)
    s = _norm(
        tuple(  # type: ignore[arg-type]
            math.cos(theta) * d[i] + math.sin(theta) * (math.cos(phi) * u[i] + math.sin(phi) * w[i]) for i in range(3)
        )
    )
    s = _norm((max(s[0], 0.12), s[1], s[2]))
    return (side * (CX + A * s[0] * 0.97), B * s[1] * 0.97, C * s[2] * 0.97)


def distilled_positions(distilled: DistilledGraph) -> dict[str, tuple[float, float, float]]:
    """Where each distillate node sits: value, identity, strength and failure on the medial wall front to back,
    lexicon in the left temporal lobe (language), rules in the frontal lobe, gotchas deep with the recipes,
    superseded views on the cerebellum; a side by the node's hash where the brain has two."""
    groups: dict[tuple[str, int], list[str]] = {}
    for n in distilled.nodes:
        known = n.type in D_MEDIAL or n.type in D_SURFACE or n.type in D_DEEP
        side = 0 if not known else -1 if n.type == "lexicon" else _hash_side(D + n.id)
        groups.setdefault((n.type, side), []).append(n.id)
    pos: dict[str, tuple[float, float, float]] = {}
    for (typ, side), ids in groups.items():
        ids.sort()
        count = len(ids)
        for k, node_id in enumerate(ids):
            if typ in D_MEDIAL:
                t, phi = (k + 0.5) / count, k * 2.39996
                rr = 0.16 * math.sqrt(t)
                pos[node_id] = (side * 0.035, B * (0.15 + rr * math.cos(phi)), C * (D_MEDIAL[typ] + rr * math.sin(phi)))
            elif typ in D_SURFACE:
                pos[node_id] = _surface(k, count, side, D_SURFACE[typ])
            elif typ in D_DEEP:
                pos[node_id] = _ball(k, count, side, D_DEEP[typ])
            else:
                pos[node_id] = _cerebellum(k, count)
    return pos


def _distilled_payload(graph: MemoryGraph, distilled: DistilledGraph, lang: Language) -> dict[str, Any]:
    live = {n.id: n.id for n in graph.nodes if not n.ghost}
    live |= {Path(n.path).stem: n.id for n in graph.nodes if n.path and Path(n.path).stem not in live}
    pos = distilled_positions(distilled)
    edges: list[dict[str, str]] = [
        {"source": D + e.source, "target": D + e.target, "kind": D + e.kind} for e in distilled.edges
    ]
    edges += [
        {"source": D + n.id, "target": live[n.mem], "kind": D + "store"} for n in distilled.nodes if n.mem in live
    ]
    degree: dict[str, int] = {}
    for e in edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
    nodes = [
        {
            "id": D + n.id,
            "type": D + n.type,
            "label": n.label,
            "detail": n.detail,
            "date": n.date,
            "mem": n.mem or "",
            "linked": n.mem in live,
            "lobe": D
            + ("medial" if n.type in D_MEDIAL else n.type if n.type in D_SURFACE or n.type in D_DEEP else "old"),
            "p": [round(x, 4) for x in pos[n.id]],
            "deg": degree.get(D + n.id, 0),
        }
        for n in distilled.nodes
    ]
    return {
        "types": {
            D + k: {"label": label(lang, "distillate", label=label(lang, f"dtype.{k}", t.label)), "color": t.color}
            for k, t in distilled.types.items()
        },
        "kinds": {
            D + k: {"label": label(lang, f"dkind.{k}", t.label), "color": t.color} for k, t in distilled.kinds.items()
        }
        | {D + "store": {"label": label(lang, "dkind.store"), "color": D_STORE_COLOUR}},
        "lobes": {D + k: label(lang, f"dlobe.{k}") for k in D_LOBES},
        "nodes": nodes,
        "edges": edges,
    }


def render(
    graph: MemoryGraph,
    embed: bool = False,
    distilled: DistilledGraph | None = None,
    lang: Language = "en",
) -> str:
    """The template with this identity's graph as its data slot, its words in the given language."""
    types = {k: {"label": label(lang, f"type.{k}"), "color": c} for k, c in TYPE_COLOUR.items()}
    kinds = {k: {"label": label(lang, f"kind.{k}"), "color": c} for k, c in KIND_COLOUR.items()}
    lobes = {k: label(lang, f"lobe.{k}") for k in LOBES}
    pos, degree = positions(graph)
    nodes = []
    for n in graph.nodes:
        kind = kind_of(n)
        level = (
            label(lang, "brain.ghost")
            if n.ghost
            else (
                f"history → {n.validity.history}"
                if n.validity and n.validity.history
                else (n.validity.level if n.validity and n.validity.level else "unscored")
            )
        )
        nodes.append(
            {
                "id": n.id,
                "type": kind,
                "label": label_of(n.id),
                "detail": n.trigger or n.id,
                "date": level,
                "mem": n.path or "",
                "lobe": region_of(n),
                "p": [round(x, 4) for x in pos[n.id]],
                "deg": degree.get(n.id, 0),
            }
        )
    payload: dict[str, Any] = {
        "kicker": label(
            lang, "brain.kicker", identity=graph.identity, memories=len(graph.nodes), edges=len(graph.edges)
        ),
        "types": types,
        "kinds": kinds,
        "lobes": lobes,
        "nodes": nodes,
        "edges": [e.model_dump() for e in graph.edges],
        "embed": embed,
        "shape": {"cx": CX, "a": A, "b": B, "c": C},
        "distilled": None,
    }
    if distilled is not None:
        layer = _distilled_payload(graph, distilled, lang)
        payload["types"] = types | layer.pop("types")
        payload["kinds"] = kinds | layer.pop("kinds")
        payload["lobes"] = lobes | layer.pop("lobes")
        payload["nodes"] = nodes + layer.pop("nodes")
        payload["edges"] = payload["edges"] + layer.pop("edges")
        payload["distilled"] = layer
    html = TEMPLATE.read_text(encoding="utf-8")
    return html.replace("/*DATA*/null", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))


CACHE_SECONDS = 3600
_cache: dict[str, tuple[float, str]] = {}


def cached(key: str, build: Callable[[], str]) -> str:
    """The page built at most once an hour per identity; a new memory shows within the hour."""
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    html = build()
    _cache[key] = (time.monotonic(), html)
    return html
