"""Bring an agent's existing memory into an identity, group by group.

The connector names the sources and, for a loose dir, its layer; this reads only those dirs, never writes into them,
and refuses one that lies inside an identity's folder. A file already in place with the same bytes is skipped, one with
other bytes is a conflict and stays as it is. Each group is one commit. A file's index line comes from its source's
MEMORY.md as it is; a line in Claude Code's auto-memory form `- [Title](f.md) — hook` becomes `- f.md — hook`, so that
recall finds it. When the source is under git, each copied file's first and last commit day go to
state/memory-origins.json, and validity counts from them instead of the import day.

Claude Code's own memory (the auto-memory, a subagent's memory) is written in another form: the type nested under
`metadata:`, a `name` that is not the file name, a `description` that says what the file holds. A loose group's files
are brought into whaat's form on the way: `name` is the file name (prefixed with the type when it lacks it), `type` at
the top, `description` is the file's index trigger, the harness's bookkeeping fields go, and `[[links]]` to a renamed
memory follow it. A file already in whaat's form is copied as it is. What needs judgement (`when`, `source`, a `user`
type outside the core) is left out or reported, never guessed. A source without git gives its files' own dates.

`move_personal` is for a folder whose personal memory still sits at the memory root: it
moves it into personal/ (tracked files with `git mv`) before anything is imported next to it.
"""

import datetime
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from whaat.git import GitCommitError, GitCommitter
from whaat.identities.registry import STATE_DIR_NAME
from whaat.memory import validity
from whaat.memory.schemas import (
    ConvertedFile,
    MigratedGroup,
    MigrationCall,
    MigrationGroup,
    MigrationImported,
    MigrationListed,
    PersonalMoved,
)
from whaat.memory.service import (
    CORE_DIR,
    DIR_MODE,
    FILE_MODE,
    INDEX_NAME,
    MEMORY_DIR,
    PERSONAL_DIR,
    card_of,
    index_of,
    set_index_line,
)

PRIVATE_MARK = ".private"
SKIPPED_FILES = {INDEX_NAME, validity.MEMORY_MAP}
AUTO_LINE = re.compile(r"^\s*-\s*\[[^\]]*\]\(([^)\s]+\.md)\)\s*(?:\u2014|\u2013|-)+\s*(.*?)\s*$")
PLAIN_LINE = re.compile(r"^\s*-\s*\[?([\w./-]+\.md)\b")
LINK = re.compile(r"\[\[([^\]\n]+)\]\]")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)
ALL_TYPES = ("feedback", "project", "reference", "user")
HARNESS_FIELDS = ("node_type", "originSessionId", "modified")
KEPT_FIELDS = ("when", "source", "confirmed", "supersedes", "reach")
PRE_D1 = (
    "the personal memory still sits at the memory root (memory/core/); move it into personal/ first"
    " (whaat memory move-personal)"
)


class MigrationSourceError(ValueError):
    """A source the import cannot take: missing, not a dir, inside an identity's folder, or a wrong target."""


class MigrationLayoutError(RuntimeError):
    """The identity's memory is in a layout the import must not write into."""


Kind = Literal["store", "personal", "loose"]


@dataclass
class Group:
    id: str
    kind: Kind
    base: Path  # the source as the connector named it; paths in `files` and the git dates are relative to it
    source: Path
    target: str
    files: dict[str, tuple[Path, str]] = field(default_factory=dict)  # target path -> (source file, path in source)
    lines: dict[str, str] = field(default_factory=dict)  # target path -> index line to write
    rewritten: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    content: dict[str, bytes] = field(default_factory=dict)  # target path -> the bytes written, converted or as is
    converted: list[ConvertedFile] = field(default_factory=list)


def groups_of(call: MigrationCall, identity_folders: list[Path]) -> list[Group]:
    groups: list[Group] = []
    for number, source in enumerate(call.sources, start=1):
        base = Path(source.path).expanduser()
        if not base.is_dir():
            raise MigrationSourceError(f"{source.path} is not a dir")
        resolved = base.resolve()
        for folder in identity_folders:
            owner = folder.expanduser().resolve()
            if resolved.is_relative_to(owner) or owner.is_relative_to(resolved):
                raise MigrationSourceError(f"{source.path} overlaps an identity's folder ({owner}); not read")
        if (source.kind == "loose") != (source.target is not None):
            raise MigrationSourceError(f"{source.path}: a target is given for a loose dir, and only for one")
        if source.kind == "store":
            for rel in _store_dirs(base):
                target = "." if rel == "." else rel
                groups.append(_group(f"{number}:{target}", "store", base, base / rel, target, recursive=False))
        elif source.kind == "personal":
            groups.append(_group(f"{number}:{PERSONAL_DIR}", "personal", base, base, PERSONAL_DIR, recursive=True))
        else:
            target = source.target or "."
            groups.append(_group(f"{number}:{target}", "loose", base, base, target, recursive=False))
    groups = [group for group in groups if group.files]
    _convert_loose([group for group in groups if group.kind == "loose"])
    for group in groups:
        for rel, (src, _) in group.files.items():
            group.content.setdefault(rel, src.read_bytes())
    return groups


def listing(root: Path, call: MigrationCall, identity_folders: list[Path]) -> MigrationListed:
    groups = groups_of(call, identity_folders)
    earlier = _brought_from(root.parent)
    return MigrationListed(groups=[_view(root, group, earlier) for group in groups], warnings=_layout_warnings(root))


def _brought_from(folder: Path) -> dict[str, str]:
    """The source file each memory an earlier import brought came from, by its path below the memory root."""
    try:
        known = json.loads((folder / STATE_DIR_NAME / validity.ORIGINS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(known, dict):
        return {}
    return {rel: str(entry["from"]) for rel, entry in known.items() if isinstance(entry, dict) and "from" in entry}


def _in_place(dst: Path, rel: str, group: Group, earlier: dict[str, str]) -> Literal["same", "edited", "conflict"]:
    """A file already in place: the same bytes, one an earlier import brought from this very source file and that
    changed here since (edited), or other content (a conflict). Neither of the last two is ever overwritten."""
    if dst.read_bytes() == group.content[rel]:
        return "same"
    return "edited" if earlier.get(rel) == str(group.files[rel][0]) else "conflict"


def import_groups(
    folder: Path, committer: GitCommitter, call: MigrationCall, identity_folders: list[Path]
) -> MigrationImported:
    root = folder / MEMORY_DIR
    if _pre_d1(root):
        raise MigrationLayoutError(PRE_D1)
    groups = {group.id: group for group in groups_of(call, identity_folders)}
    unknown = [gid for gid in call.groups if gid not in groups]
    if unknown or not call.groups:
        raise MigrationSourceError(f"no such group: {', '.join(unknown)}" if unknown else "name the groups to import")
    today = datetime.date.today().isoformat()
    warnings: list[str] = []
    done: list[MigratedGroup] = []
    origins: dict[str, dict[str, str]] = {}
    earlier = _brought_from(folder)
    copied_stems: set[str] = set()
    for gid in dict.fromkeys(call.groups):
        group = groups[gid]
        copied: list[str] = []
        same: list[str] = []
        edited: list[str] = []
        conflicts: list[str] = []
        indexes: list[Path] = []
        for rel in group.files:
            dst = root / rel
            if dst.exists():
                {"same": same, "edited": edited, "conflict": conflicts}[_in_place(dst, rel, group, earlier)].append(rel)
                continue
            _write_bytes(folder, dst, group.content[rel])
            copied.append(rel)
            copied_stems.add(dst.stem)
        for rel, line in group.lines.items():  # in the source index's order
            if rel in copied:
                index, name = index_of(root, root / rel)
                indexes.append(set_index_line(folder, index, name, line))
        commit = None
        if copied:
            paths = sorted({root / rel for rel in copied} | set(indexes))
            message = f"memory: import {len(copied)} from {group.source} into {group.target}"
            commit = _commit(committer, folder, paths, message, warnings)
            origins.update(_origins(group, copied, today))
        done.append(
            MigratedGroup(
                id=gid,
                copied=copied,
                same=same,
                edited=edited,
                conflicts=conflicts,
                rewritten=group.rewritten,
                dropped=group.dropped,
                converted=[c for c in group.converted if c.file in copied],
                commit=commit,
            )
        )
    state = folder / STATE_DIR_NAME
    if origins:
        _merge_origins(state, origins)
    carried = _carry_outcomes(Path(call.state).expanduser(), state, copied_stems) if call.state else 0
    core = add_core_defaults(folder, committer, warnings)
    core_linked = link_core(folder, committer, warnings)
    brought = [rel for group in done for rel in group.copied]
    return MigrationImported(
        groups=done,
        origins=len(origins),
        outcomes=carried,
        core_defaults=core,
        core_linked=core_linked,
        unlinked=unlinked(root, brought),
        warnings=warnings,
    )


def link_core(folder: Path, committer: GitCommitter, warnings: list[str]) -> list[str]:
    """The core files belong together: each one that names not every other gets a `Related:` line with the missing
    [[links]], appended, in one commit. Returns the files that got one, below the memory root."""
    root = folder / MEMORY_DIR
    core = root / PERSONAL_DIR / CORE_DIR
    files = sorted(core.glob("*.md"))
    names = {path: card_of(root, path).frontmatter.get("name") or path.stem for path in files}
    changed = []
    for path in files:
        named = set(LINK.findall(card_of(root, path).body))
        missing = [names[other] for other in files if other != path and not {names[other], other.stem} & named]
        if missing:
            text = path.read_text(encoding="utf-8").rstrip("\n")
            related = ", ".join(f"[[{name}]]" for name in missing)
            _write_bytes(folder, path, f"{text}\n\nRelated: {related}\n".encode())
            changed.append(path)
    if changed:
        _commit(committer, folder, changed, "memory: link the core files to each other", warnings)
    return [path.relative_to(root).as_posix() for path in changed]


def unlinked(root: Path, brought: list[str]) -> list[str]:
    """The brought memories with no [[link]] to another memory and none from one, so the agent can propose some."""
    files = [
        path
        for path in root.rglob("*.md")
        if path.name not in SKIPPED_FILES and not any(part.startswith(".") for part in path.relative_to(root).parts)
    ]
    targets: set[str] = set()
    for path in files:
        targets.update(LINK.findall(card_of(root, path).body))
    alone = []
    for rel in brought:
        card = card_of(root, root / rel)
        named = {card.frontmatter.get("name") or "", Path(rel).stem} - {""}
        if not LINK.search(card.body) and not named & targets:
            alone.append(rel)
    return alone


CORE_TEMPLATES = Path(__file__).parent / "core_templates"
SELF_SUFFIX = "_self.md"


def _in_core(core: Path, template: Path) -> bool:
    """A core file of that name; for the self file any `<agent>_self.md`, since each agent names its own."""
    if template.name.endswith(SELF_SUFFIX):
        return any(core.glob(f"*{SELF_SUFFIX}"))
    return (core / template.name).exists()


def add_core_defaults(folder: Path, committer: GitCommitter, warnings: list[str]) -> list[str]:
    """whaat's default core files, copied in where the identity's core has none of them, each with its line in the
    personal index, in one commit; a file already there is never touched. Returns their paths below the memory root."""
    root = folder / MEMORY_DIR
    core = root / PERSONAL_DIR / CORE_DIR
    added = [t for t in sorted(CORE_TEMPLATES.glob("*.md")) if not _in_core(core, t)]
    if not added:
        return []
    index = root / PERSONAL_DIR / INDEX_NAME
    paths = [index]
    for template in added:
        _write_bytes(folder, core / template.name, template.read_bytes())
        paths.append(core / template.name)
        name = f"{CORE_DIR}/{template.name}"
        description = card_of(root, core / template.name).frontmatter.get("description", "")
        set_index_line(folder, index, name, f"- {name} — {description}")
    mark = root / PERSONAL_DIR / PRIVATE_MARK
    if not mark.exists():
        _write_bytes(folder, mark, b"")
        paths.append(mark)
    names = ", ".join(t.name for t in added)
    _commit(committer, folder, paths, f"memory: add the default core files {names}", warnings)
    return [f"{PERSONAL_DIR}/{CORE_DIR}/{t.name}" for t in added]


def move_personal(folder: Path, committer: GitCommitter) -> PersonalMoved:
    """Everything at the memory root into personal/, the personal index with it; refuses when personal/ already
    holds a file of the same path."""
    root = folder / MEMORY_DIR
    if not _pre_d1(root):
        return PersonalMoved(
            moved=[], commit=None, warnings=["nothing to move: memory/core/ is not at the memory root"]
        )
    personal = root / PERSONAL_DIR
    sources = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.relative_to(root).parts[0].startswith(".")
        and path.relative_to(root).parts[0] != PERSONAL_DIR
    )
    moves = [(path, personal / path.relative_to(root)) for path in sources]
    taken = [dst.relative_to(root).as_posix() for _, dst in moves if dst.exists()]
    if taken:
        raise MigrationLayoutError(f"personal/ already holds {', '.join(taken)}; nothing moved")
    for _, dst in moves:
        _make_dirs(folder, dst.parent)
    warnings: list[str] = []
    commit = None
    if committer.is_repository(folder):
        try:
            commit = committer.move(folder, moves, "memory: move the personal memory into personal/")
        except GitCommitError as err:
            warnings.append(f"moved but not committed: {err}")
    else:
        for src, dst in moves:
            src.rename(dst)
        warnings.append("the identity's folder is not a git repository; it is not committed")
    for directory in sorted({src.parent for src, _ in moves}, key=lambda p: len(p.parts), reverse=True):
        if directory != root and directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    mark = personal / PRIVATE_MARK
    if not mark.exists():
        _write_bytes(folder, mark, b"")
        if commit:
            _commit(committer, folder, [mark], "memory: personal/ is never shared", warnings)
    return PersonalMoved(moved=[dst.relative_to(root).as_posix() for _, dst in moves], commit=commit, warnings=warnings)


def _store_dirs(base: Path) -> list[str]:
    """The root, every <group>/ and every <group>/<repo>/; dot dirs and a personal/ inside the store are left out."""
    dirs = ["."]
    for group in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if group.name == PERSONAL_DIR:
            continue
        dirs.append(group.name)
        dirs += [f"{group.name}/{repo.name}" for repo in sorted(group.iterdir()) if _plain_dir(repo)]
    return dirs


def _plain_dir(path: Path) -> bool:
    return path.is_dir() and not path.name.startswith(".")


def _group(gid: str, kind: Kind, base: Path, directory: Path, target: str, *, recursive: bool) -> Group:
    group = Group(id=gid, kind=kind, base=base, source=directory, target=target)
    found = directory.rglob("*.md") if recursive else directory.glob("*.md")
    for path in sorted(found):
        inside = path.relative_to(directory)
        if not path.is_file() or path.name in SKIPPED_FILES or any(p.startswith(".") for p in inside.parts):
            continue
        target_rel = inside.as_posix() if target == "." else f"{target}/{inside.as_posix()}"
        group.files[target_rel] = (path, path.relative_to(base).as_posix())
    by_name = {path.relative_to(directory).as_posix(): rel for rel, (path, _) in group.files.items()}
    index = directory / INDEX_NAME
    for line in index.read_text(encoding="utf-8").splitlines() if index.is_file() else []:
        parsed = _parse_line(line)
        matched = by_name.get(parsed[0]) if parsed else None
        if parsed is None or matched is None or matched in group.lines:
            if line.strip():
                group.dropped.append(line)
            continue
        group.lines[matched] = parsed[1]
        if parsed[2]:
            group.rewritten.append(parsed[1])
    return group


def _parse_line(line: str) -> tuple[str, str, bool] | None:
    """(the file it names, the line to write, whether it was rewritten from the auto-memory form)."""
    auto = AUTO_LINE.match(line)
    if auto:
        return auto.group(1), f"- {auto.group(1)} — {auto.group(2)}", True
    plain = PLAIN_LINE.match(line)
    return (plain.group(1), line.rstrip(), False) if plain else None


def _view(root: Path, group: Group, earlier: dict[str, str]) -> MigrationGroup:
    new: list[str] = []
    same: list[str] = []
    edited: list[str] = []
    conflicts: list[str] = []
    for rel in group.files:
        dst = root / rel
        if not dst.exists():
            new.append(rel)
        else:
            {"same": same, "edited": edited, "conflict": conflicts}[_in_place(dst, rel, group, earlier)].append(rel)
    return MigrationGroup(
        id=group.id,
        kind=group.kind,
        source=str(group.source),
        target=group.target,
        files=list(group.files),
        new=new,
        same=same,
        edited=edited,
        conflicts=conflicts,
        unindexed=[rel for rel in group.files if rel not in group.lines],
        rewritten=group.rewritten,
        dropped=group.dropped,
        converted=group.converted,
    )


def _pre_d1(root: Path) -> bool:
    return (root / CORE_DIR).is_dir()


def _layout_warnings(root: Path) -> list[str]:
    return [PRE_D1] if _pre_d1(root) else []


def _origins(group: Group, copied: list[str], today: str) -> dict[str, dict[str, str]]:
    """The source's first and last commit day of each copied file; for a file git does not track, its own creation and
    change days."""
    if _git_top(group.base) is None:
        return {
            rel: {**_file_days(group.files[rel][0]), "imported": today, "from": str(group.files[rel][0])}
            for rel in copied
        }
    added, last = validity.commit_dates(str(group.base))
    result = {}
    for rel in copied:
        in_source = group.files[rel][1]
        if in_source in added:
            result[rel] = {"added": added[in_source], "last": last.get(in_source, added[in_source]), "imported": today}
        else:  # in a git repo, but never committed there
            result[rel] = {**_file_days(group.files[rel][0]), "imported": today}
        result[rel]["from"] = str(group.files[rel][0])
    return result


def _file_days(path: Path) -> dict[str, str]:
    stat = path.stat()
    born = getattr(stat, "st_birthtime", stat.st_mtime)
    day = datetime.date.fromtimestamp
    return {"added": day(born).isoformat(), "last": day(stat.st_mtime).isoformat()}


def _convert_loose(groups: list[Group]) -> None:
    """Bring Claude Code's memory files into whaat's form, then point every [[link]] to a renamed memory at its new
    name, in all these groups."""
    renamed: dict[str, str] = {}
    for group in groups:
        for rel in list(group.files):
            src, in_source = group.files[rel]
            line = group.lines.get(rel)
            trigger = line.split(" \u2014 ", 1)[1] if line and " \u2014 " in line else None
            text, stem, changes, notes = _convert(src.read_text(encoding="utf-8"), src.stem, trigger)
            if not changes and not notes:
                continue
            new_rel = rel if stem == src.stem else str(Path(rel).with_name(f"{stem}.md").as_posix())
            if new_rel != rel:
                group.files = {new_rel if k == rel else k: v for k, v in group.files.items()}
                if line is not None:
                    group.lines = {new_rel if k == rel else k: v for k, v in group.lines.items()}
                    group.lines[new_rel] = f"- {stem}.md \u2014 {trigger}"
                    group.rewritten = [f"- {stem}.md \u2014 {trigger}" if r == line else r for r in group.rewritten]
                for old in {src.stem, *_names(src.read_text(encoding="utf-8"))}:
                    renamed[old] = stem
            elif changes:
                for old in _names(src.read_text(encoding="utf-8")):
                    if old != stem:
                        renamed[old] = stem
            group.content[new_rel] = text.encode("utf-8")
            group.converted.append(ConvertedFile(file=new_rel, source=in_source, changes=changes, notes=notes))
    if not renamed:
        return
    for group in groups:
        for rel, data in list(group.content.items()):
            text = data.decode("utf-8")
            linked = LINK.sub(lambda m: f"[[{renamed.get(m.group(1), m.group(1))}]]", text)
            if linked != text:
                group.content[rel] = linked.encode("utf-8")
                done = next((c for c in group.converted if c.file == rel), None)
                note = "[[links]] to renamed memories follow them"
                if done is None:
                    group.converted.append(
                        ConvertedFile(file=rel, source=group.files[rel][1], changes=[note], notes=[])
                    )
                elif note not in done.changes:
                    done.changes.append(note)


def _names(text: str) -> list[str]:
    parsed = _frontmatter(text)
    name = parsed[0].get("name", "").strip("\"'") if parsed else ""
    return [name] if name else []


def _frontmatter(text: str) -> tuple[dict[str, str], str] | None:
    """The fields of a frontmatter, a nested block's keys (Claude Code's `metadata:`) read as top-level ones."""
    match = FRONTMATTER.match(text)
    if not match:
        return None
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        kv = re.match(r"\s*(\w+):\s*(.*)$", line)
        if kv and kv.group(2).strip():
            fields.setdefault(kv.group(1), kv.group(2).strip())
    return fields, match.group(2)


def _convert(text: str, stem: str, trigger: str | None) -> tuple[str, str, list[str], list[str]]:
    """(the text in whaat's form, its file stem, what changed, what still needs a decision); a file already in that
    form comes back as it is, with no changes."""
    parsed = _frontmatter(text)
    if parsed is None:
        return text, stem, [], ["no frontmatter: copied as it is; give it one through the whaat:memory skill"]
    fm, body = parsed
    head = FRONTMATTER.match(text).group(1)  # type: ignore[union-attr]
    kind = fm.get("type", "").strip("\"'")
    changes: list[str] = []
    notes: list[str] = []
    new_stem = stem
    if kind in ALL_TYPES and not stem.startswith(kind + "_"):
        new_stem = f"{kind}_{stem}"
        changes.append(f"renamed {stem}.md to {new_stem}.md: the name starts with the type")
    name = fm.get("name", "").strip("\"'")
    if name != new_stem:
        changes.append(f"name {name or '(none)'} is now {new_stem}, the file name")
    description = fm.get("description", "").strip("\"'")
    if trigger and trigger != description:
        changes.append("description is now the index line's trigger")
        if description and description not in body:
            body = f"{description}\n\n{body.lstrip(chr(10))}" if body.strip() else f"{description}\n"
            changes.append("the old description opens the body, so nothing it said is lost")
    nested = [key for key in HARNESS_FIELDS if key in fm] + (["metadata"] if re.search(r"(?m)^metadata:", head) else [])
    if nested:
        changes.append(f"harness fields dropped: {', '.join(nested)}; type moved to the top")
    if kind == "user":
        notes.append(
            "type user outside the core: the lint reports it; make it feedback, or a core file on the user's yes"
        )
    elif kind not in ALL_TYPES:
        notes.append(f"type {kind or '(none)'}: not feedback, project or reference; decide it")
    if not changes:
        return text, stem, [], notes
    lines = [f"name: {new_stem}", f"description: {trigger or description}", f"type: {kind}"]
    lines += [f"{key}: {fm[key]}" for key in KEPT_FIELDS if key in fm]
    return "---\n" + "\n".join(lines) + "\n---\n" + body, new_stem, changes, notes


def _git_top(directory: Path) -> str | None:
    run = subprocess.run(
        ["git", "-C", str(directory), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    return run.stdout.strip() if run.returncode == 0 else None


def _merge_origins(state: Path, origins: dict[str, dict[str, str]]) -> None:
    state.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    path = state / validity.ORIGINS_FILE
    try:
        known = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        known = {}
    known = {**(known if isinstance(known, dict) else {}), **origins}
    partial = path.with_name(f".{path.name}.partial")
    partial.write_text(json.dumps(known, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(path)


def _carry_outcomes(source_state: Path, state: Path, stems: set[str]) -> int:
    """memory-outcomes.log lines of the copied files (validity matches them by file name), not yet in the target log."""
    source = source_state / validity.OUTCOMES_LOG
    if not stems or not source.is_file():
        return 0
    target = state / validity.OUTCOMES_LOG
    known = set(target.read_text(encoding="utf-8").splitlines()) if target.is_file() else set()
    carried = []
    for line in source.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) == 4 and os.path.basename(parts[2])[:-3] in stems and line not in known:
            carried.append(line)
            known.add(line)
    if carried:
        state.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write("".join(line + "\n" for line in carried))
    return len(carried)


def _commit(committer: GitCommitter, folder: Path, paths: list[Path], message: str, warnings: list[str]) -> str | None:
    if not committer.is_repository(folder):
        warnings.append("the identity's folder is not a git repository; it is not committed")
        return None
    try:
        return committer.commit(folder, paths, message)
    except GitCommitError as err:
        warnings.append(f"copied but not committed: {err}")
        return None


def _make_dirs(folder: Path, directory: Path) -> None:
    current = folder
    for part in directory.relative_to(folder).parts:
        current = current / part
        current.mkdir(mode=DIR_MODE, exist_ok=True)


def _write_bytes(folder: Path, path: Path, data: bytes) -> None:
    _make_dirs(folder, path.parent)
    partial = path.with_name(f".{path.name}.partial")
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    with os.fdopen(descriptor, "wb") as file:
        file.write(data)
    partial.replace(path)
