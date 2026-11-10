from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class Labelled(BaseModel):
    label: str
    color: str


class DistilledNode(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    label: str
    detail: str = ""
    date: str = ""
    mem: str | None = None


class DistilledEdge(BaseModel):
    source: str
    target: str
    kind: str


class HeatRow(BaseModel):
    id: str
    label: str
    ep: list[int] = Field(description="The batches (1-based) with a named case.")
    mention: list[int] = Field(description="The batches where it is only mentioned.")
    verdict: str
    note: str


class Phase(BaseModel):
    span: str
    title: str
    me: str
    user: str = Field(validation_alias=AliasChoices("user", "robi"))  # older data names the user `robi`


class LadderStep(BaseModel):
    date: str
    text: str


class ChangedView(BaseModel):
    date: str
    old: str
    new: str


class HubSession(BaseModel):
    id: str
    date: str
    n: str
    text: str


class DistilledGraph(BaseModel):
    """distilled/graph/graph.json as build_graph.py wrote it: the nodes and edges, and the analysis sets."""

    model_config = ConfigDict(extra="allow")

    types: dict[str, Labelled]
    kinds: dict[str, Labelled]
    nodes: list[DistilledNode]
    edges: list[DistilledEdge]
    batches: list[str] = []
    heat: list[HeatRow] = []
    phases: list[Phase] = []
    ladder: list[LadderStep] = []
    changed: list[ChangedView] = []
    hubs: list[HubSession] = []


class ReadingParagraph(BaseModel):
    lead: str
    text: str


class Reading(BaseModel):
    """My reading of the distillate (graph_template.html's last section), kept as data in graph/reading.json."""

    title: str
    paragraphs: list[ReadingParagraph]
    caveats: list[str]


class DistilledAnalysis(BaseModel):
    """The distillate's analysis sets for the memory page's Elemzés: what the Emlékgráf showed under its graph."""

    first: str = Field(description="The first transcript batch's start, as the Emlékgráf names its span.")
    last: str = Field(description="The latest node date, the span's end.")
    batches: list[str]
    heat: list[HeatRow]
    phases: list[Phase]
    ladder: list[LadderStep]
    changed: list[ChangedView]
    hubs: list[HubSession]
    reading: Reading | None
