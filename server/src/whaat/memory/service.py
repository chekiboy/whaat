import os
import re
import threading
from pathlib import Path

from whaat.git import GitCommitError, GitCommitter
from whaat.identities.registry import STATE_DIR_NAME, IdentityRegistry
from whaat.memory import recall, validity
from whaat.memory.exceptions import InvalidMemoryPathError, MemoryNotFoundError
from whaat.memory.schemas import (
    CardValidity,
    GraphEdge,
    GraphNode,
    IdentityMemory,
    MemoryCard,
    MemoryGraph,
    MemoryLayerView,
    MemoryRoots,
    MemorySave,
    SavedMemory,
)

MEMORY_DIR = "memory"
INDEX_NAME = "MEMORY.md"
PERSONAL_DIR = "personal"
CORE_DIR = "core"
DIR_MODE = 0o700
FILE_MODE = 0o600


def index_of(root: Path, path: Path) -> tuple[Path, str]:
    """The index that lists this memory and the name it is listed under: a core file is `core/<name>.md` in the
    personal index."""
    if path.parent == root / PERSONAL_DIR / CORE_DIR:
        return root / PERSONAL_DIR / INDEX_NAME, f"{CORE_DIR}/{path.name}"
    return path.parent / INDEX_NAME, path.name


LINK = re.compile(r"\[\[([^\]\n]+)\]\]")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)


def layer_of(rel: Path) -> str:
    parts = rel.parent.parts
    if parts[:2] == (PERSONAL_DIR, CORE_DIR):
        return "core"
    if parts[:1] == (PERSONAL_DIR,):
        return "personal"
    return {0: "global", 1: "project"}.get(len(parts), "repo")


def card_of(root: Path, path: Path) -> MemoryCard:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(text)
    head, body = (match.group(1), match.group(2)) if match else ("", text)
    fields = dict(line.split(":", 1) for line in head.splitlines() if ":" in line)
    index, name = index_of(root, path)
    indexed = index.exists() and any(names(line, name) for line in index.read_text(encoding="utf-8").splitlines())
    return MemoryCard(
        path=path.relative_to(root).as_posix(),
        frontmatter={key.strip(): value.strip() for key, value in fields.items()},
        body=body.strip(),
        indexed=indexed,
    )


def names(line: str, name: str) -> bool:
    """The same match memory-recall uses to find a memory's index line."""
    return re.match(rf"\s*-\s*\[?{re.escape(name)}\b", line) is not None


class MemoryService:
    """Deterministic saving: the agent decides what, where, the file and its trigger; this writes them as given."""

    def __init__(self, registry: IdentityRegistry, committer: GitCommitter) -> None:
        self._registry = registry
        self._committer = committer
        self._lock = threading.Lock()

    @property
    def lock(self) -> threading.Lock:
        """Held by every write of a memory or an index, the migration's included."""
        return self._lock

    @property
    def committer(self) -> GitCommitter:
        return self._committer

    def folder_of(self, identity: str) -> Path:
        return self._registry.folder_of(identity)

    def identity_folders(self) -> list[Path]:
        return list(self._registry.folders().values())

    def where(self, identity: str) -> MemoryRoots:
        folder = self._registry.folder_of(identity)
        root = folder / MEMORY_DIR
        return MemoryRoots(memory=str(root), personal=str(root / PERSONAL_DIR), state=str(folder / STATE_DIR_NAME))

    def roots(self, identity: str) -> recall.Roots:
        """The identity's memory, personal and state dirs, for memory-recall's index, open and dump."""
        folder = self._registry.folder_of(identity)
        return recall.Roots(folder / MEMORY_DIR, folder / MEMORY_DIR / PERSONAL_DIR, folder / STATE_DIR_NAME)

    def browse(self, identities: list[str]) -> list[IdentityMemory]:
        """Every memory of these identities, layer by layer, with its score, for reading in the UI; nothing is logged,
        but the scores are refreshed first when they are from an earlier day."""
        result = []
        for identity in identities:
            root = self._registry.folder_of(identity) / MEMORY_DIR
            scores = validity.load(self.roots(identity)) if root.is_dir() else {}
            memories = scores.get("memories")
            scored = memories if isinstance(memories, dict) else {}
            layers: dict[tuple[str, str], list[MemoryCard]] = {}
            for path in sorted(root.rglob("*.md")) if root.is_dir() else []:
                if path.name == INDEX_NAME or path.name.startswith("."):
                    continue
                rel = path.relative_to(root)
                card = card_of(root, path)
                entry = scored.get(rel.as_posix())
                if isinstance(entry, dict):
                    card.validity = CardValidity.model_validate(entry, strict=False)
                layers.setdefault((layer_of(rel), rel.parent.as_posix()), []).append(card)
            result.append(
                IdentityMemory(
                    identity=identity,
                    layers=[
                        MemoryLayerView(layer=layer, dir=d, memories=cards) for (layer, d), cards in layers.items()
                    ],
                )
            )
        return result

    def graph(self, identity: str) -> MemoryGraph:
        """The identity's memories as a graph: a node per memory file, an edge per [[link]] (to the memory whose
        frontmatter name it names) and per `supersedes`; a link target with no memory becomes a ghost node."""
        root = self._registry.folder_of(identity) / MEMORY_DIR
        cards = (
            [card for layer in self.browse([identity])[0].layers for card in layer.memories] if root.is_dir() else []
        )
        nodes: dict[str, GraphNode] = {}
        for card in cards:
            rel = Path(card.path)
            name = card.frontmatter.get("name") or rel.stem
            nodes[name] = GraphNode(
                id=name,
                path=card.path,
                layer=layer_of(rel),
                dir=rel.parent.as_posix(),
                type=card.frontmatter.get("type"),
                trigger=card.frontmatter.get("description"),
                when=[w.strip() for w in card.frontmatter.get("when", "").strip("[]").split(",") if w.strip()],
                indexed=card.indexed,
                validity=card.validity,
            )
        by_stem = {Path(card.path).stem: card.frontmatter.get("name") or Path(card.path).stem for card in cards}
        edges: list[GraphEdge] = []
        for card in cards:
            source = card.frontmatter.get("name") or Path(card.path).stem
            for target in dict.fromkeys(LINK.findall(card.body)):
                edges.append(GraphEdge(source=source, target=target, kind="link"))
            if card.frontmatter.get("supersedes"):
                edges.append(GraphEdge(source=source, target=card.frontmatter["supersedes"], kind="supersedes"))
        for edge in edges:
            if edge.target not in nodes and edge.target in by_stem:
                edge.target = by_stem[edge.target]  # a supersedes or link naming the file, not the frontmatter name
            if edge.target not in nodes:
                nodes[edge.target] = GraphNode(id=edge.target, ghost=True, indexed=False)
        return MemoryGraph(identity=identity, nodes=list(nodes.values()), edges=edges)

    def save(self, identity: str, memory: MemorySave) -> SavedMemory:
        folder = self._registry.folder_of(identity)
        root = folder / MEMORY_DIR
        path = self._inside(root, memory.path)
        superseded = [self._inside(root, rel) for rel in memory.unindex]
        warnings: list[str] = []
        with self._lock:
            created = not path.exists()
            _write(folder, path, memory.content)
            index, name = index_of(root, path)
            changed = {path, set_index_line(folder, index, name, f"- {name} — {memory.trigger}")}
            for old in superseded:
                old_index, old_name = index_of(root, old)
                changed.add(set_index_line(folder, old_index, old_name, None))
            rel = path.relative_to(root).as_posix()
            commit = self._commit(folder, sorted(changed), f"memory: {'add' if created else 'update'} {rel}", warnings)
        return SavedMemory(path=rel, created=created, commit=commit, warnings=warnings)

    def delete(self, identity: str, rel_path: str) -> SavedMemory:
        folder = self._registry.folder_of(identity)
        root = folder / MEMORY_DIR
        path = self._inside(root, rel_path)
        warnings: list[str] = []
        with self._lock:
            if not path.exists():
                raise MemoryNotFoundError(rel_path)
            path.unlink()
            index, name = index_of(root, path)
            changed = [path, set_index_line(folder, index, name, None)]
            rel = path.relative_to(root).as_posix()
            commit = self._commit(folder, changed, f"memory: delete {rel}", warnings)
        return SavedMemory(path=rel, created=False, commit=commit, warnings=warnings)

    def revert(self, identity: str, commits: list[str]) -> list[str]:
        """revert-applied-rows: undo these commits of the identity's memory, newest first; GitCommitError refuses or
        reports an aborted run, which changes nothing."""
        folder = self._registry.folder_of(identity)
        with self._lock:
            return self._committer.revert(folder, commits, MEMORY_DIR)

    @staticmethod
    def _inside(root: Path, rel_path: str) -> Path:
        path = (root / rel_path).resolve()  # an absolute path inside the root is taken as it is
        if not path.is_relative_to(root.resolve()) or path.suffix != ".md" or path.name == INDEX_NAME:
            raise InvalidMemoryPathError(rel_path)
        return root / path.relative_to(root.resolve())

    def _commit(self, folder: Path, paths: list[Path], message: str, warnings: list[str]) -> str | None:
        if not self._committer.is_repository(folder):
            warnings.append("the identity's folder is not a git repository; it is not committed")
            return None
        try:
            return self._committer.commit(folder, paths, message)
        except GitCommitError as err:
            warnings.append(f"saved but not committed: {err}")
            return None


def set_index_line(folder: Path, index: Path, name: str, line: str | None) -> Path:
    """Replace the memory's index line in place or add it at the end; None removes it. Other lines stay."""
    lines = index.read_text(encoding="utf-8").splitlines(keepends=True) if index.exists() else []
    kept = [existing for existing in lines if not names(existing, name)]
    at = next((i for i, existing in enumerate(lines) if names(existing, name)), None)
    if line is not None:
        if kept and not kept[-1].endswith("\n"):
            kept[-1] += "\n"
        kept.insert(at if at is not None else len(kept), line + "\n")
    _write(folder, index, "".join(kept))
    return index


def _write(folder: Path, path: Path, text: str) -> None:
    directory = folder
    for part in path.parent.relative_to(folder).parts:
        directory = directory / part
        directory.mkdir(mode=DIR_MODE, exist_ok=True)
    partial = path.with_name(f".{path.name}.partial")
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(text)
    partial.replace(path)
