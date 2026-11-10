"""The distillate of 2026-10-16, static data in an identity's private folder: `distilled/` holds `layers/`,
`graph/`, `pilot/` and `notes/`, as the archive's distilled/ did, sorted by kind."""

from pathlib import Path

from whaat.distilled.schemas import DistilledAnalysis, DistilledGraph, Reading

DISTILLED_DIR = "distilled"
GRAPH_FILE = Path("graph") / "graph.json"
READING_FILE = Path("graph") / "reading.json"
FIRST_BATCH = "2026-09-02"  # graph_template.html's span start, the first transcript batch


def load_graph(folder: Path) -> DistilledGraph | None:
    """The identity's distillate graph, or None when it has none."""
    path = folder / DISTILLED_DIR / GRAPH_FILE
    if not path.is_file():
        return None
    return DistilledGraph.model_validate_json(path.read_text(encoding="utf-8"))


def load_analysis(folder: Path) -> DistilledAnalysis | None:
    """The analysis sets of the identity's distillate and my reading of them, or None when it keeps no distillate."""
    graph = load_graph(folder)
    if graph is None:
        return None
    reading = folder / DISTILLED_DIR / READING_FILE
    return DistilledAnalysis(
        first=FIRST_BATCH,
        last=max((n.date for n in graph.nodes if n.date), default=""),
        batches=graph.batches,
        heat=graph.heat,
        phases=graph.phases,
        ladder=graph.ladder,
        changed=graph.changed,
        hubs=graph.hubs,
        reading=Reading.model_validate_json(reading.read_text(encoding="utf-8")) if reading.is_file() else None,
    )
