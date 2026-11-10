"""What the curation report page draws besides the report itself: which memory files a row names, the memory map with
its before and after counts, and per row the data of its small diagram (merge target, move destination, size against
budget, the index line now and after). The memory is the identity's, without the personal dir."""

import os
import re
from collections.abc import Callable

from pydantic import BaseModel, Field

from whaat.memory.validity import PERSONAL_DIR, is_memory_file
from whaat.reports.types.memory_curation import CurationRow

ACTIONS = ["delete", "merge", "move", "split", "trim", "retrigger", "verify", "fix"]
BUDGET = {"reference": 2500}
DEFAULT_BUDGET = 1200
NAME = re.compile(r"(?:[\w.-]+/)*(?:feedback|project|reference)_[\w.-]+?(?:\.md)?(?=[^\w.-]|$)|(?:[\w.-]+/)*MEMORY\.md")
LEVELS = ("global", "project", "repo")

File = tuple[str, str]


class MapCell(BaseModel):
    file: str = Field(description="dir/stem, or the stem for the global dir.")
    action: str | None = Field(
        description="The first action of the first row that names the file; null when none does."
    )


class MapDir(BaseModel):
    dir: str = Field(description='The dir below the memory root; "" is the global one.')
    level: str
    before: int
    after_lo: int
    after_hi: int
    cells: list[MapCell]


class MemoryMap(BaseModel):
    dirs: list[MapDir]
    total_before: int
    total_lo: int
    total_hi: int


class RowFigure(BaseModel):
    n: int
    files: list[str] = Field(description="The memory files the row names, as dir/stem.")
    name: str = Field(description="The first file's stem, else the File cell as plain text.")
    into: str | None = Field(description="merge: the target memory's stem; null when none is named.")
    from_dir: str | None = Field(description="move: the first file's dir; null when the file is not found.")
    dest: str | None = Field(description='move: the destination dir ("" for global); null when unknown.')
    size: int | None = Field(description="trim and split: the body's characters; null when the file is not found.")
    budget: int | None
    now: str | None = Field(description="retrigger: the file's index line now; null when it has none.")
    after: str | None = Field(description="retrigger: the new index line, from the row's Target.")


class CurationView(BaseModel):
    map: MemoryMap | None = Field(description="Null when the identity has no memory.")
    rows: list[RowFigure]


def plain(text: str) -> str:
    return re.sub(r"[`*]", "", text)


def level_of(rel: str) -> str:
    if not rel:
        return "global"
    return "project" if rel.count("/") == 0 else "repo"


def _personal(rel: str) -> bool:
    return rel == PERSONAL_DIR or rel.startswith(PERSONAL_DIR + os.sep)


def scan_store(store: str) -> dict[str, dict[str, int]]:
    """{rel_dir: {stem: body_chars}} for every dir holding memories."""
    dirs: dict[str, dict[str, int]] = {}
    if not os.path.isdir(store):
        return dirs
    for d, sub, names in os.walk(store):
        rel = os.path.relpath(d, store)
        rel = "" if rel == "." else rel
        sub[:] = sorted(x for x in sub if not x.startswith(".") and not _personal(os.path.join(rel, x)))
        for n in sorted(names):
            if is_memory_file(d, n, store):
                with open(os.path.join(d, n), encoding="utf-8") as handle:
                    text = handle.read()
                m = re.match(r"---\n.*?\n---\n?(.*)", text, re.S)
                dirs.setdefault(rel, {})[n[:-3]] = len(m.group(1) if m else text)
    return dirs


def scan_index(store: str) -> dict[File, str]:
    """{(rel_dir, stem): trigger} from each dir's MEMORY.md, the line that decides when a memory is opened."""
    index: dict[File, str] = {}
    if not os.path.isdir(store):
        return index
    for d, sub, names in os.walk(store):
        rel = os.path.relpath(d, store)
        rel = "" if rel == "." else rel
        sub[:] = sorted(x for x in sub if not x.startswith(".") and not _personal(os.path.join(rel, x)))
        if "MEMORY.md" not in names:
            continue
        with open(os.path.join(d, "MEMORY.md"), encoding="utf-8") as handle:
            for line in handle:
                m = re.match(r"^- ([\w.-]+)\.md\s+—\s+(.*\S)", line)
                if m:
                    index[(rel, m.group(1))] = m.group(2)
    return index


def resolver(dirs: dict[str, dict[str, int]]) -> Callable[[str], File | None]:
    by_path = {(f"{d}/{s}" if d else s): (d, s) for d, files in dirs.items() for s in files}
    by_stem: dict[str, list[File]] = {}
    for d, files in dirs.items():
        for s in files:
            by_stem.setdefault(s, []).append((d, s))

    def resolve(token: str) -> File | None:
        t = token.strip("`").rstrip(".").removesuffix(".md")
        if t in by_path:
            return by_path[t]
        hits = by_stem.get(t.rsplit("/", 1)[-1], [])
        return hits[0] if len(hits) == 1 else None

    return resolve


def _path(file: File) -> str:
    return f"{file[0]}/{file[1]}" if file[0] else file[1]


def row_files(row: CurationRow, resolve: Callable[[str], File | None]) -> tuple[list[File], File | None, str | None]:
    """The files a row names (its File cell, else its Target when the File cell names none), and for a merge its
    target, for a move its destination dir."""
    file_cell, target = row.file, row.target or ""
    files = [x for x in (resolve(t) for t in NAME.findall(file_cell)) if x]
    if not files and not NAME.search(file_cell):
        files = [x for x in (resolve(t) for t in NAME.findall(target)) if x]
    into = None
    if "merge" in row.actions:
        others = [x for x in (resolve(t) for t in NAME.findall(target)) if x and x not in files]
        into = others[0] if others else None
    dest = None
    if "move" in row.actions:
        m = re.search(r"`([\w.-]+(?:/[\w.-]+)*)/?`", target)
        if m:
            dest = m.group(1).strip("/")
        elif re.search(r"\bglobal\b|<store>", target, re.I):
            dest = ""
    return files, into, dest


def figure(
    row: CurationRow,
    files: list[File],
    into: File | None,
    dest: str | None,
    dirs: dict[str, dict[str, int]],
    index: dict[File, str],
) -> RowFigure:
    first = files[0] if files else None
    name = first[1] if first else plain(row.file)
    size = budget = None
    if first and ("trim" in row.actions or "split" in row.actions):
        size = dirs.get(first[0], {}).get(first[1])
        if size:
            budget = BUDGET.get(first[1].split("_", 1)[0], DEFAULT_BUDGET)
    now = after = None
    if "retrigger" in row.actions:
        now = index.get(first) if first else None
        quoted = re.findall(r'["“]([^"”]+)["”]', plain(row.target or ""))
        after = quoted[-1] if quoted else plain(row.target or "").strip(' "“”')
    return RowFigure(
        n=row.n,
        files=[_path(f) for f in files],
        name=name,
        into=into[1] if into else None,
        from_dir=first[0] if first and "move" in row.actions else None,
        dest=dest,
        size=size or None,
        budget=budget,
        now=now,
        after=after,
    )


def memory_map(
    rows: list[CurationRow],
    parsed: dict[int, tuple[list[File], File | None, str | None]],
    dirs: dict[str, dict[str, int]],
) -> MemoryMap | None:
    if not dirs:
        return None
    act: dict[File, str] = {}
    for row in rows:
        for f in parsed[row.n][0]:
            act.setdefault(f, row.actions[0])
    moved_in: dict[str, int] = {}
    for row in rows:
        named, _, dest = parsed[row.n]
        if "move" in row.actions and dest is not None:
            moved_in[dest] = moved_in.get(dest, 0) + len(named)
    total_before = total_lo = total_hi = 0
    out = []
    for d in sorted(dirs, key=lambda name: (LEVELS.index(level_of(name)), name)):  # the page's level columns
        files = dirs[d]
        a = [act.get((d, s)) for s in files]
        before = len(files)
        hi = before - a.count("delete") - a.count("move") + a.count("split") + moved_in.get(d, 0)
        lo = hi - a.count("merge")
        total_before, total_lo, total_hi = total_before + before, total_lo + lo, total_hi + hi
        cells = [MapCell(file=_path((d, s)), action=act.get((d, s))) for s in files]
        out.append(MapDir(dir=d, level=level_of(d), before=before, after_lo=lo, after_hi=hi, cells=cells))
    return MemoryMap(dirs=out, total_before=total_before, total_lo=total_lo, total_hi=total_hi)


def view(memory_dir: str, rows: list[CurationRow]) -> CurationView:
    dirs = scan_store(memory_dir)
    index = scan_index(memory_dir)
    resolve = resolver(dirs)
    parsed = {row.n: row_files(row, resolve) for row in rows}
    figures = [figure(row, *parsed[row.n], dirs, index) for row in rows]
    return CurationView(map=memory_map(rows, parsed, dirs), rows=figures)
