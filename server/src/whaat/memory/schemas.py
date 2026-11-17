from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from whaat.reports.types.base import Strict

MemoryPath = Annotated[str, StringConstraints(pattern=r"^[^\n]+\.md$")]
Line = Annotated[str, StringConstraints(min_length=1, pattern=r"^[^\n]+$")]


class MemorySave(Strict):
    path: MemoryPath = Field(
        description="Where it goes below the identity's memory root, as the agent chose it, e.g."
        " acme/shop/feedback_x.md or personal/core/claude_self.md."
    )
    content: Annotated[str, StringConstraints(min_length=1)] = Field(
        description="The whole file, frontmatter included, written exactly as given."
    )
    trigger: Line = Field(description="The index line's text after the name: when to open the file.")
    unindex: list[MemoryPath] = Field(
        default_factory=list, description="Memories this one supersedes: their index lines go, their files stay."
    )


class SavedMemory(BaseModel):
    path: str
    created: bool
    commit: str | None
    warnings: list[str]


class MemoryRoots(BaseModel):
    memory: str
    personal: str
    state: str = Field(description="The identity's local logs (memory-recall.log), kept out of git.")
    project: str | None = Field(default=None, description="The project's memory dir, when a key was given.")
    repo: str | None = Field(default=None, description="The repo's memory dir, when a key was given.")


class RecallCall(Strict):
    """What the CLI sends from its own process: the session and the cwd."""

    session: str = Field(description="The first 8 characters of the session id; empty outside Claude Code.")


class RecallIndex(RecallCall):
    task: str
    cwd: str = Field(description="The path= argument, else the caller's cwd; logged as given.")
    repo: str | None = Field(default=None, description="The repo= argument (group or group/repo), as given.")
    key: list[str] | None = Field(
        default=None, min_length=2, max_length=2, description="(project, repo) the caller resolved from cwd."
    )
    known: str | None = Field(
        default=None, description="The digest of an index the caller read every part of and still holds, if any."
    )
    part: int = Field(default=1, ge=1, description="Which part of the index to return, from 1.")


class RecallOpen(RecallCall):
    file: str
    because: str = ""
    purpose: str | None = None


class RecallDump(RecallCall):
    dir: str
    because: str = ""
    purpose: str | None = None


class IndexEntry(BaseModel):
    file: str
    trigger: str


class IndexSection(BaseModel):
    label: str
    prefix: str
    entries: list[IndexEntry] | None = Field(description="None when the dir has no MEMORY.md.")


class RecallIndexed(BaseModel):
    store: str
    digest: str = Field(
        description="Of the whole index; pass it back as `known` while every part stays in the context."
    )
    part: int = Field(description="The part this answer carries.")
    parts: int = Field(description="How many parts the index has.")
    sections: list[IndexSection] | None = Field(
        description="None when `known` matched an index this session got since its last compaction."
    )
    unchanged_since: str | None = Field(description="When this session got that same index; None with sections.")
    missing: list[int] = Field(
        default_factory=list, description="On the last part: the parts this session has not read since its compaction."
    )
    text: str = Field(description="The part, or the unchanged line, as memory-recall prints it.")
    footer: str = Field(description="memory-recall's last line: the next part, the parts still missing, or the end.")


class RecallOpened(BaseModel):
    file: str
    path: str
    trigger: str | None
    purpose: str
    text: str | None = Field(description="None for recall and load: the hook puts the memory in, not the output.")


class DumpedFile(BaseModel):
    file: str
    text: str


class RecallDumped(BaseModel):
    files: list[DumpedFile]


class CardValidity(BaseModel):
    """A memory's entry in memory-validity.json: a score, level and age, or the memory that superseded it."""

    level: str | None = None
    score: float | None = None
    age_days: int | None = None
    history: str | None = None
    source: str | None = None
    outcomes: dict[str, int] = Field(default_factory=dict)


class MemoryCard(BaseModel):
    path: str
    frontmatter: dict[str, str]
    body: str
    indexed: bool = Field(description="False when no index line names it: history, or not indexed.")
    validity: CardValidity | None = Field(
        default=None, description="None for a personal memory, which is not scored, or a file not scored yet."
    )


class MemoryLayerView(BaseModel):
    layer: str = Field(description="global, project, repo, personal or core.")
    dir: str
    memories: list[MemoryCard]


class IdentityMemory(BaseModel):
    identity: str
    layers: list[MemoryLayerView]


class OpenedLine(BaseModel):
    file: str
    path: str


class FrameCall(Strict):
    """A memory-frame PostToolUse call: the `opened:` lines a recall or load printed, and who ran it."""

    session: str
    agent: str = Field(default="", description="The hook event's agent_id; empty in the main session.")
    opened: list[OpenedLine]
    force: bool = False
    uncapped: bool = Field(
        default=False, description="Put every block in, past the hook's size cap; for a caller without that cap."
    )


class SeenCall(Strict):
    """A memory-frame PostToolUse call for an index answer a Bash call printed, and the agent that ran it."""

    session: str
    agent: str = Field(default="", description="The hook event's agent_id; empty in the main session.")
    digest: str
    part: int | None = Field(
        default=None, ge=1, le=1000, description="The part the answer carried; None for an unchanged answer."
    )
    parts: int = Field(ge=1, le=1000, description="How many parts the index has.")
    unchanged: bool = False


class Seen(BaseModel):
    note: str | None = Field(description="A line correcting the answer for this agent; None when it holds.")


class Framed(BaseModel):
    context: str | None = Field(description="The hook's additionalContext; None when no line names a memory.")


class GuardCall(Strict):
    """A recall-guard PreToolUse check: the absolute paths a Read or a reader command would read."""

    session: str
    paths: list[str]
    must_exist: bool = Field(description="True for a reader command (only existing files count), False for a Read.")


class Guarded(BaseModel):
    file: str | None = Field(description="The first memory not yet opened this session, as index names it; else None.")


class StartCall(Strict):
    """One SessionStart hook: which level and part, the hook event's session and source, the repo key from its cwd."""

    level: Literal["global", "map", "project", "repo", "personal"]
    part: int = Field(ge=1)
    parts: int = Field(ge=1)
    session: str = ""
    source: str = ""
    key: list[str] | None = Field(default=None, min_length=2, max_length=2)
    cli: str = Field(description="The plugin's whaat CLI path, for the open commands of a core over the hooks.")
    outline: bool = Field(
        default=False,
        description="Personal level only: one line per core file (its description and first sentence), nothing logged;"
        " for a client whose instructions cannot hold the whole core.",
    )


class Started(BaseModel):
    text: str | None = Field(description="What the hook prints; None when this part has nothing.")
    additional_context: bool = Field(description="True: print as SessionStart additionalContext JSON (the core).")


class SubagentCore(BaseModel):
    text: str | None = Field(
        description="What a subagent gets as context at its start: the global index, the every-agent core files when"
        " one is marked, then the memory map."
    )


class ReadCall(Strict):
    """A memory-outcome Read hook call: the absolute path the Read tool read."""

    session: str
    path: str


class ReadsCall(Strict):
    session: str


class RecordCall(Strict):
    session: str
    outcome: str
    paths: list[str]


class LevelCall(Strict):
    paths: list[str]


class RevertCall(Strict):
    commits: list[str] = Field(min_length=1, description="The commits to undo, as an Applied cell names them.")


class Reverted(BaseModel):
    commits: list[str] = Field(description="The new revert commits, oldest first.")


class LintCall(Strict):
    dup_threshold: float = Field(default=0.4, description="Name+description word overlap that marks a duplicate.")


DumpVia = Annotated[
    Literal["cli", "mcp"],
    Field(description="How the brief tells its agent to read the dir: the CLI command, or the MCP tool call."),
]


class CurationBriefCall(Strict):
    dir: str = Field(description='The memory dir to judge, below the memory root; "" or "." is the global one.')
    dump: DumpVia = "cli"


class CurationRefuteCall(Strict):
    dir: str = Field(description='The memory dir the rows are from; "" or "." is the global one.')
    rows: list[dict[str, Any]] = Field(description="The judge's rows for that dir, as the judge returned them.")
    dump: DumpVia = "cli"


class FidelityCall(Strict):
    file: str = Field(description="The memory as it was, below the memory root.")
    rev: str = Field(default="HEAD", description="The commit holding it as it was.")
    new: list[str] = Field(min_length=1, description="The memories its text now lives in, below the memory root.")


class Text(BaseModel):
    text: str | None = Field(description="The text to print; None when there is nothing to print.")


class GraphNode(BaseModel):
    id: str = Field(description="The memory's frontmatter name, which [[links]] use; the file stem when it has none.")
    path: str | None = Field(default=None, description="Below the memory root; None for a ghost.")
    layer: str | None = Field(default=None, description="core, personal, global, project or repo; None for a ghost.")
    dir: str | None = None
    type: str | None = Field(default=None, description="feedback, project, reference or user, from the frontmatter.")
    trigger: str | None = Field(default=None, description="The frontmatter description: when to recall it.")
    when: list[str] = Field(default_factory=list)
    indexed: bool = True
    validity: CardValidity | None = None
    ghost: bool = Field(default=False, description="A [[link]] target that is no memory of this identity.")


class GraphEdge(BaseModel):
    source: str
    target: str
    kind: Literal["link", "supersedes"]


class MemoryGraph(BaseModel):
    identity: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


MigrationTarget = Annotated[
    str, StringConstraints(pattern=r"^(\.|personal|[A-Za-z0-9_-][A-Za-z0-9._-]*(/[A-Za-z0-9_-][A-Za-z0-9._-]*)?)$")
]


class MigrationSource(Strict):
    path: Line = Field(description="An existing memory dir on this machine, read only, never written.")
    kind: Literal["store", "personal", "loose"] = Field(
        description="store: a layered store (root files, <group>/, <group>/<repo>/), one group each; personal: a"
        " personal dir with its core/, one group into personal/; loose: one flat dir (e.g. Claude Code's auto-memory"
        " or a subagent's memory) into the layer named by `target`."
    )
    target: MigrationTarget | None = Field(
        default=None,
        description="Only for loose: the layer it goes to: . (global), personal, <group> or <group>/<repo>.",
    )


class MigrationCall(Strict):
    sources: list[MigrationSource] = Field(min_length=1)
    groups: list[str] = Field(
        default_factory=list, description="For the import: the ids of the groups to bring in, as the listing gave them."
    )
    state: Line | None = Field(
        default=None,
        description="For the import: the source's state dir; its memory-outcomes.log lines for the imported files are"
        " carried over, so their held, misled and irrelevant counts stay.",
    )


class ConvertedFile(BaseModel):
    file: str = Field(description="Its path below the identity's memory root, after any rename.")
    source: str = Field(description="Its path in the source.")
    changes: list[str] = Field(description="What was changed to bring it into whaat's form.")
    notes: list[str] = Field(description="What still needs a decision; nothing was guessed for it.")


class MigrationGroup(BaseModel):
    id: str = Field(description="<source number>:<target layer>, to name it in the import.")
    kind: Literal["store", "personal", "loose"]
    source: str = Field(description="The dir the group's files come from.")
    target: str = Field(description="The layer below the identity's memory root: . for global.")
    files: list[str] = Field(description="Its memory files, by their path below the identity's memory root.")
    new: list[str] = Field(description="Files not yet in place.")
    same: list[str] = Field(description="Files already in place with the same content: skipped.")
    edited: list[str] = Field(
        default_factory=list,
        description="Files an earlier import brought from this source and changed here since: kept, not a conflict.",
    )
    conflicts: list[str] = Field(description="Files in place with other content: left as they are, never overwritten.")
    unindexed: list[str] = Field(description="Files the source's MEMORY.md has no line for: they come as history.")
    rewritten: list[str] = Field(
        description="Index lines in Claude Code's auto-memory form `- [Title](f.md) — hook`, as they will be written:"
        " `- f.md — hook`."
    )
    dropped: list[str] = Field(description="Source index lines that name no file of the group: not carried.")
    converted: list[ConvertedFile] = Field(
        description="Files of a loose group (Claude Code's own memory) brought into whaat's form on the way."
    )


class MigrationListed(BaseModel):
    groups: list[MigrationGroup]
    warnings: list[str]


class MigratedGroup(BaseModel):
    id: str
    copied: list[str]
    same: list[str]
    edited: list[str] = Field(default_factory=list)
    conflicts: list[str]
    rewritten: list[str]
    dropped: list[str]
    converted: list[ConvertedFile]
    commit: str | None


class MigrationImported(BaseModel):
    groups: list[MigratedGroup]
    origins: int = Field(description="Files whose first and last commit day came from the source's git.")
    outcomes: int = Field(description="memory-outcomes.log lines carried over.")
    core_defaults: list[str] = Field(
        default_factory=list, description="whaat's default core files added because the core had none of that name."
    )
    core_linked: list[str] = Field(
        default_factory=list, description="Core files that got a Related line, so every core file links the others."
    )
    unlinked: list[str] = Field(
        default_factory=list, description="Brought memories with no [[link]] to or from another memory."
    )
    warnings: list[str]


class PersonalMoved(BaseModel):
    moved: list[str] = Field(description="The files moved from the memory root into personal/, by their new path.")
    commit: str | None
    warnings: list[str]


class MigrationPlanCall(Strict):
    sources: list[MigrationSource] = Field(
        min_length=1, description="The sources found, a loose dir with the proposed target."
    )
    state: Line | None = Field(default=None, description="The source's state dir, whose outcome lines come along.")
    session: str = Field(default="", description="The first 8 characters of the session that made the plan.")


class MigrationDecisions(Strict):
    identity: str = Field(description="Whose plan; the page names it, so a plan is never decided for someone else.")
    targets: dict[str, MigrationTarget] = Field(
        default_factory=dict, description="A loose source's number → the layer the user chose for it."
    )
    groups: list[str] = Field(description="The ids of the groups to bring in, with the targets above applied.")


class MigrationPlan(BaseModel):
    id: str
    identity: str
    created_at: str
    session: str
    sources: list[MigrationSource]
    state: str | None
    groups: list[str] | None = Field(description="The groups the user chose; null until they decide on the page.")
    decided_at: str | None = None
    sent_at: str | None = None
    result: MigrationImported | None = None
    imported_at: str | None = None


class MigrationPlanView(BaseModel):
    plan: MigrationPlan
    folder: str = Field(description="The identity's folder, where the memory goes.")
    instance: str = Field(description="The whaat instance that holds it: live, dev or a trial.")
    layers_now: dict[str, int] = Field(description="The identity's memories per layer before the import.")
    listing: MigrationListed = Field(description="The groups as they stand against the identity's memory now.")
    url: str = Field(description="Where the page shows it.")


class MigrationPlanSummary(BaseModel):
    id: str
    created_at: str
    groups: int | None
    imported_at: str | None


class MigrationSent(BaseModel):
    command: str = Field(description="The call that imports the chosen groups; typed into the session when it runs.")
    session: str | None
    typed: bool
    detail: str | None = Field(description="Why it was not typed: no running migration session, or the readback.")


class MigrationStart(Strict):
    identity: str = Field(description="Whose memory to fill; its own agent config runs the session.")
    cwd: str | None = Field(default=None, description="The folder the session starts in; else its agent config's.")
