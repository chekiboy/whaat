"""memory-recall's index, open and dump on one identity's memory, with the same memory-recall.log lines.

The identity's personal dir sits inside its memory root; it is reached only as `personal:…`, so a `personal/…` path
is no memory of the store here either.
"""

import datetime
import hashlib
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

PURPOSES = ("recall", "save", "curate", "review", "load")
DUMP_PURPOSES = ("save", "curate", "review")
PERSONAL = "personal:"
LOG_NAME = "memory-recall.log"
MEMORY_MAP = "memory-map.md"
DIR_MODE = 0o700
PART_BUDGET = 8000


class RecallError(ValueError):
    """A call memory-recall would refuse, with its message."""


class Roots:
    def __init__(self, memory: Path, personal: Path, state: Path) -> None:
        self.store = os.path.realpath(memory)
        self.personal = os.path.realpath(personal)
        self.state = state

    def root_of(self, rel: str) -> tuple[str, str, str]:
        """(root dir, path inside it, prefix) for a store path or a `personal:` one."""
        if rel.startswith(PERSONAL):
            return self.personal, rel[len(PERSONAL) :], PERSONAL
        return self.store, rel, ""

    def inside(self, root: str, path: str) -> bool:
        """Under root; the store's own copy of the personal dir counts as outside it."""
        if root == self.store and (path == self.personal or path.startswith(self.personal + os.sep)):
            return False
        return path == root or path.startswith(root + os.sep)


def log(roots: Roots, session: str, event: dict[str, object]) -> None:
    roots.state.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    line = {"at": datetime.datetime.now().isoformat(timespec="seconds"), "session": session[:8], **event}
    with (roots.state / LOG_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def index_line(store: str, rel: str) -> str | None:
    """The line naming rel in its own dir's index, else in the root index by its relative path (personal core/)."""
    for idx, name in (
        (os.path.join(store, os.path.dirname(rel), "MEMORY.md"), os.path.basename(rel)),
        (os.path.join(store, "MEMORY.md"), rel),
    ):
        if os.path.exists(idx):
            for line in Path(idx).read_text(encoding="utf-8").splitlines(keepends=True):
                if re.match(rf"\s*-\s*\[?{re.escape(name)}\b", line):
                    return line.strip()
    return None


def reason(because: str, what: str) -> str:
    because = because.strip()
    hint = "which words of its trigger match the task" if what == "open" else "why"
    if len(because) < 10:
        raise RecallError(f'memory-recall {what}: because="<{hint}>" is required')
    return because


def purpose_of(purpose: str | None, allowed: tuple[str, ...]) -> str:
    purpose = allowed[0] if purpose is None else purpose
    if purpose not in allowed:
        raise RecallError(f"memory-recall: purpose must be one of {', '.join(allowed)}")
    return purpose


def index(
    roots: Roots,
    session: str,
    task: str,
    cwd: str,
    repo: str | None,
    key: list[str] | None,
    known: str | None = None,
    part: int = 1,
) -> dict[str, object]:
    """The global, project, repo and personal indexes; key is the (project, repo) the caller resolved from cwd.

    The index comes in parts of about PART_BUDGET characters, so a tool result never outgrows what a client shows in
    full; each answer carries one part and the digest of the whole index. When `known` is that digest and this session
    got every part of it since its last compaction, the sections are left out: the caller still holds them."""
    task = task.strip()
    if len(task) < 10:
        raise RecallError('memory-recall index: task="<what you are doing>" is required: the log ties each open to it')
    store = roots.store
    found: tuple[str, ...] | None
    project_only = None
    if repo:
        parts = tuple(p for p in repo.strip("/").split("/") if p)
        directory = os.path.realpath(os.path.join(store, *parts)) if parts else store
        if not parts or not os.path.isdir(directory) or not roots.inside(store, directory):
            raise RecallError(
                f"memory-recall index: repo={repo!r} is no memory dir in the store; the memory map in"
                " CLAUDE.md lists them"
            )
        found = parts if len(parts) == 2 else None
        project_only = parts[0] if len(parts) == 1 else None
    else:
        found = tuple(key) if key else None
    dirs = [("global", store, "")]
    if found:
        dirs += [
            ("project", os.path.join(store, found[0]), found[0] + "/"),
            ("repo", os.path.join(store, *found), "/".join(found) + "/"),
        ]
    elif project_only:
        dirs.append(("project", os.path.join(store, project_only), project_only + "/"))
    dirs.append(("personal", roots.personal, PERSONAL))
    sections = []
    for label, directory, prefix in dirs:
        idx = os.path.join(directory, "MEMORY.md")
        entries = None
        if os.path.exists(idx):
            entries = []
            for line in Path(idx).read_text(encoding="utf-8").splitlines(keepends=True):
                m = re.match(r"\s*-\s*\[?([\w.-]+(?:/[\w.-]+)*\.md)", line)
                if m:
                    trigger = line.split("—", 1)[-1].strip() if "—" in line else line.strip()
                    entries.append({"file": prefix + m.group(1), "trigger": trigger})
        sections.append({"label": label, "prefix": prefix, "entries": entries})
    digest = hashlib.sha256(json.dumps(sections, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    pages = in_parts(sections)
    if not 1 <= part <= len(pages):
        raise RecallError(f"memory-recall index: part={part} is out of range; this index has {len(pages)} part(s)")
    every = set(range(1, len(pages) + 1))
    got, first = parts_given(roots, session, digest, len(pages))
    since = first if known == digest and got >= every else None
    event = {"op": "index", "task": task, "cwd": cwd, "repo": repo, "digest": digest}
    log(roots, session, {**event, "part": part, "parts": len(pages), "unchanged": bool(since)})
    answer = {"store": store, "digest": digest, "part": part, "parts": len(pages)}
    if since:
        text = (
            f"index {digest} unchanged since {since[11:16]} ({len(pages)} parts): it is above in your context, open"
            " from it. If it is no longer there, run index again without known=.\n"
        )
        return {**answer, "sections": None, "unchanged_since": since, "missing": [], "text": text, "footer": ""}
    missing = sorted(every - got - {part}) if part == len(pages) else []
    text = part_text(store, digest, part, len(pages), pages[part - 1])
    footer = index_footer(part, len(pages), missing)
    return {
        **answer,
        "sections": pages[part - 1],
        "unchanged_since": None,
        "missing": missing,
        "text": text,
        "footer": footer,
    }


OPEN_LINE = 'Open a memory only through: whaat memory open file=<path below> because="<trigger words that match>"'


def part_text(store: str, digest: str, part: int, parts: int, sections: list[dict[str, Any]]) -> str:
    lines = [
        f"store {store}",
        f"index {digest} part {part}/{parts} (once you have read every part, pass known={digest} next time)",
        OPEN_LINE,
        "",
    ]
    for section in sections:
        lines.append(f"## {section['label']}: {section['prefix'] or '(store root)'}")
        if section["entries"] is None:
            lines.append("(no index)")
        else:
            lines += [f"- {entry['file']} — {entry['trigger']}" for entry in section["entries"]]
        lines.append("")
    return "\n".join(lines) + "\n"


def index_footer(part: int, parts: int, missing: list[int]) -> str:
    if part < parts:
        return f"Part {part} of {parts}: run index again with part={part + 1} for the next part.\n"
    if missing:
        gaps = ", ".join(str(n) for n in missing)
        return (
            f"Not complete yet: this session has not read part {gaps}. Run index again with part={missing[0]},"
            " then each other part named here.\n"
        )
    return f"That was the last part ({parts} of {parts}).\n"


def in_parts(sections: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """The sections split into parts of about PART_BUDGET characters of index lines; a long section continues in the
    next part under the same label."""
    parts: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 0
    for section in sections:
        entries = section["entries"]
        head = {**section, "entries": None if entries is None else []}
        current.append(head)
        header = len(str(section["label"])) + len(str(section["prefix"])) + 8
        size += header
        for entry in entries if isinstance(entries, list) else []:
            line = len(entry["file"]) + len(entry["trigger"]) + 5
            held = head["entries"]
            if size + line > PART_BUDGET and (held or len(current) > 1):
                if not held:
                    current.pop()
                parts.append(current)
                head = {**section, "entries": []}
                current = [head]
                size = header
            head["entries"].append(entry)
            size += line
    parts.append(current)
    return parts


def record_seen(
    roots: Roots, session: str, agent: str, digest: str, part: int | None, parts: int, unchanged: bool
) -> str | None:
    """memory-frame's check of an index answer against what this agent itself read, since the CLI counts parts per
    session and a subagent runs under its main agent's session: the part logged for this agent, and a correcting
    line where the answer counted parts it did not read."""
    session = session[:8]
    if not unchanged and part is not None:
        log(roots, session, {"op": "seen", "agent": agent, "digest": digest, "part": part, "parts": parts})
    events = _events(roots)
    mine = parts_seen(events, session, agent, digest)
    every = set(range(1, parts + 1))
    if unchanged and not mine >= every:
        return (
            f"[memory] this agent has not read every part of index {digest} itself (it shares its session with"
            " other agents): run index again without known=."
        )
    if not unchanged and part == parts:
        missing = sorted(every - mine)
        if missing and missing != sorted(every - parts_given(roots, session, digest, parts, events)[0]):
            gaps = ", ".join(str(n) for n in missing)
            return (
                f"[memory] this agent has not read part {gaps} of index {digest} itself: run index again with"
                f" part={missing[0]}, then each other part named here."
            )
    return None


def parts_seen(events: list[dict[str, object]], session: str, agent: str, digest: str) -> set[int]:
    """The parts of the index with this digest that this agent got, as memory-frame logged them, since this agent's
    last compaction; only the main agent has one."""
    got: set[int] = set()
    for event in events:
        if event.get("session") != session:
            continue
        if event.get("op") == "compact" and not agent:
            got = set()
        elif (
            event.get("op") == "seen"
            and (event.get("agent") or "") == agent
            and event.get("digest") == digest
            and isinstance(seen_part := event.get("part"), int)
        ):
            got.add(seen_part)
    return got


LINK = re.compile(r"\[\[([\w.-]+)\]\]")


def memory_names(roots: Roots) -> dict[str, str]:
    """Each memory's name (its file name without .md) and its path as index names it, personal ones as personal:…."""
    names: dict[str, str] = {}
    for root, prefix in ((roots.store, ""), (roots.personal, PERSONAL)):
        for directory, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and roots.inside(root, os.path.join(directory, d))]
            for name in files:
                if name.endswith(".md") and name not in ("MEMORY.md", MEMORY_MAP):
                    rel = os.path.relpath(os.path.join(directory, name), root)
                    names.setdefault(name[:-3], prefix + rel)
    return names


def trust_and_links(
    roots: Roots, names: Callable[[], dict[str, str]], rel: str, text: str, head: str, describe: Callable[[str], str]
) -> list[str]:
    """This memory's own trust, then the memories it links to, each by its index line and how far it can be trusted,
    not by its text, so they can be weighed side by side."""
    own = os.path.basename(rel)[:-3]
    wanted = [name for name in dict.fromkeys(LINK.findall(text)) if name != own]
    if not wanted:
        return []
    lines = []
    for name in wanted:
        found = names().get(name)
        if found is None:
            lines.append(f"- [[{name}]]: no memory of that name")
            continue
        root, inner, _ = roots.root_of(found)
        line = index_line(root, inner)
        trigger = line.split("—", 1)[-1].strip() if line and "—" in line else "(no index line)"
        trust = " · ".join(part for part in describe(found).splitlines() if part)
        lines.append(f"- {found} — {trigger}\n  {trust}" if trust else f"- {found} — {trigger}")
    own_trust = " · ".join(part for part in head.splitlines() if part)
    intro = (
        "Related, by its links (index lines and trust only, not their text; open one with `whaat memory open` when"
        " its trigger fits the task):"
    )
    return ([f"This memory: {own_trust}"] if own_trust else []) + [intro, *lines]


def parts_given(
    roots: Roots, session: str, digest: str, parts: int, events: list[dict[str, object]] | None = None
) -> tuple[set[int], str | None]:
    """The parts of the index with this digest this session got since its last compaction, and when it got the
    first of them. A logged index line without a part counts as the whole index."""
    got: set[int] = set()
    since = None
    for event in _events(roots) if events is None else events:
        if event.get("session") != session[:8]:
            continue
        if event.get("op") == "compact":
            got, since = set(), None
        elif event.get("op") == "index" and event.get("digest") == digest and not event.get("unchanged"):
            got |= {given} if isinstance(given := event.get("part"), int) else set(range(1, parts + 1))
            at = event.get("at")
            since = since or (at if isinstance(at, str) else None)
    return got, since


def open_memory(roots: Roots, session: str, file: str, because: str, purpose: str | None) -> dict[str, object]:
    store, rel, prefix = roots.root_of(file)
    path = os.path.realpath(os.path.join(store, rel))
    if not rel.endswith(".md") or not roots.inside(store, path) or not os.path.isfile(path):
        raise RecallError(f"memory-recall open: {file!r} is not a memory in the store; use a path that `index` printed")
    because, purpose = reason(because, "open"), purpose_of(purpose, PURPOSES)
    rel = os.path.relpath(path, store)
    trigger = index_line(store, rel)
    text = None if purpose in ("recall", "load") else Path(path).read_text(encoding="utf-8")
    log(
        roots,
        session,
        {"op": "open", "file": prefix + rel, "trigger": trigger, "because": because, "purpose": purpose},
    )
    return {"file": prefix + rel, "path": path, "trigger": trigger, "purpose": purpose, "text": text}


def dump(roots: Roots, session: str, dir: str, because: str, purpose: str | None) -> dict[str, object]:
    store, rel, prefix = roots.root_of(dir)
    directory = os.path.realpath(os.path.join(store, rel))
    if not roots.inside(store, directory) or not os.path.isdir(directory):
        raise RecallError(f"memory-recall dump: {dir!r} is not a dir of the store")
    if purpose is None:
        raise RecallError("memory-recall dump: purpose=curate|review|save is required: a whole dir is never a recall")
    purpose, because = purpose_of(purpose, DUMP_PURPOSES), reason(because, "dump")
    names = sorted(
        n for n in os.listdir(directory) if n.endswith(".md") and not (n == MEMORY_MAP and directory == store)
    )
    rels = [prefix + os.path.relpath(os.path.join(directory, n), store) for n in names]
    files = [
        {"file": shown, "text": Path(directory, name).read_text(encoding="utf-8")}
        for shown, name in zip(rels, names, strict=True)
    ]
    log(
        roots,
        session,
        {
            "op": "dump",
            "dir": prefix + os.path.relpath(directory, store),
            "files": rels,
            "because": because,
            "purpose": purpose,
        },
    )
    return {"files": files}


CORE_LOAD_BECAUSE = "session start: core (hook)"
FRAME_CAP = 9500


def _events(roots: Roots) -> list[dict[str, object]]:
    try:
        lines = (roots.state / LOG_NAME).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events = []
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def already_in(roots: Roots, session: str, agent: str, rel: str) -> str | None:
    """When this agent's context already holds rel, the time it got there, else None. The session start's core load
    and a compaction concern the main agent only; a subagent starts empty and has its own agent id."""
    at = None
    for event in _events(roots):
        if event.get("session") != session:
            continue
        mine = (event.get("agent") or "") == agent
        injected = event.get("op") == "inject" and mine
        core_load = not agent and event.get("op") == "open" and event.get("because") == CORE_LOAD_BECAUSE
        if event.get("op") == "compact" and not agent:
            at = None
        elif (injected or core_load) and event.get("file") == rel:
            at = event.get("at")
    return at if isinstance(at, str) else None


def with_room(lines: list[str], room: int | None) -> str:
    """The lines that fit into room characters, in order, and a line naming how many did not."""
    out, used = "", 0
    for n, line in enumerate(lines):
        rest = len(lines) - n
        tail = f"({rest} related line(s) left out: over the size limit)\n"
        fits = used + len(line) + 1 <= (room if rest == 1 else room - len(tail)) if room is not None else True
        if not fits:
            return out + tail
        out += line + "\n"
        used += len(line) + 1
    return out


def frame(
    roots: Roots,
    session: str,
    agent: str,
    opened: list[tuple[str, str]],
    force: bool,
    describe: Callable[[str], str] = lambda rel: "",
    uncapped: bool = False,
) -> str | None:
    """memory-frame's PostToolUse note for the `opened: <rel> -> <path>` lines of a recall or load: each memory once
    per agent, headed by what `describe` says of it (its truthness and validity, beyond the live
    note), the summed blocks under the hook cap; None when no line names a memory of this identity."""
    session = session[:8]
    hits = [
        (rel, path)
        for rel, path in opened
        if any(os.path.realpath(path).startswith(root + os.sep) for root in (roots.store, roots.personal))
    ]
    if not hits:
        return None
    blocks: list[str] = []
    left_out: list[str] = []
    put_in: list[str] = []
    known_names: dict[str, str] = {}

    def names() -> dict[str, str]:
        if not known_names:
            known_names.update(memory_names(roots))
        return known_names

    for rel, path in hits:
        at = None if force else already_in(roots, session, agent, rel)
        if at:
            blocks.append(
                f"[memory] {rel} is already in your context (put in at {at[11:16]}); not repeated. "
                "If it is no longer there, open it again with force=1."
            )
            continue
        try:
            text = Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            left_out.append(rel)
            continue
        head = describe(rel)
        block = f"Memory: {rel}\n{head + chr(10) if head else ''}\n{text}\n"
        room = FRAME_CAP - sum(map(len, blocks)) - len(block)
        if not uncapped and room < 0:
            left_out.append(rel)
            continue
        links = trust_and_links(roots, names, rel, text, head, describe)
        block += with_room(links, None if uncapped else room)
        blocks.append(block)
        put_in.append(rel)
    if put_in:
        roots.state.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        at = datetime.datetime.now().isoformat(timespec="seconds")
        with (roots.state / LOG_NAME).open("a", encoding="utf-8") as handle:
            for rel in put_in:
                line = {"at": at, "session": session, "agent": agent, "op": "inject", "file": rel}
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    if left_out:
        blocks.append(
            "[memory] not put in (over the hook's size limit or unreadable); open each again with force=1, "
            "one per call: " + ", ".join(left_out)
        )
    return "\n".join(blocks)


def guard(roots: Roots, session: str, paths: list[str], must_exist: bool) -> str | None:
    """recall-guard's check: the first of these absolute paths that is a memory this session has not opened or dumped
    through recall, as `index` names it; None when the read may go. A Read is checked as it is, a reader command only
    on files that exist."""
    session = session[:8]
    events = [e for e in _events(roots) if e.get("session") == session]
    for path in paths:
        real = os.path.realpath(os.path.expanduser(path))
        if not real.endswith(".md"):
            continue
        for root, prefix in ((roots.personal, PERSONAL), (roots.store, "")):
            if real.startswith(root + os.sep):
                rel = prefix + os.path.relpath(real, root)
                break
        else:
            continue
        if must_exist and not os.path.isfile(real):
            continue
        opened = any(
            (e.get("op") == "open" and e.get("file") == rel)
            or (e.get("op") == "dump" and isinstance(files := e.get("files"), list) and rel in files)
            for e in events
        )
        if not opened:
            return rel
    return None
