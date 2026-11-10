"""memory-where's SessionStart blocks on one identity's memory: index parts, the personal core, the load log lines.

The live system puts the global index, the `reach: every-agent` core files and the memory map in through CLAUDE.md
imports; whaat has none, so the global index and the map are SessionStart levels of their own, the every-agent files
stay in the core block of the main session, and a subagent gets the global index, them and the map from a
SubagentStart hook (subagent_core). Measured 2026-11-04 on Claude Code 2.1.318: a subagent and an in-process teammate
run SubagentStart and no SessionStart, a teammate in its own tmux pane runs SessionStart and no SubagentStart, so
each agent gets the text once. Each hook's output is capped
at 10,000 characters, so an index or the core is split across several hook commands (part N of M).
"""

import datetime
import json
import os
import re

from whaat.memory.recall import CORE_LOAD_BECAUSE, DIR_MODE, LOG_NAME, PERSONAL, Roots

CAP = 9500
LEVELS = ("global", "map", "project", "repo", "personal")
SUBAGENT_CORE = "subagent-core.md"
EVERY_AGENT = re.compile(r"\A---\n(?:.*\n)*?reach:\s*every-agent\s*\n(?:.*\n)*?---\n", re.M)


def _append(roots: Roots, lines: list[dict[str, object]]) -> None:
    roots.state.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    with (roots.state / LOG_NAME).open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def index_block(label: str, directory: str, part: int, parts: int) -> str:
    """Part `part` of `parts` of the index; empty when the index needs fewer parts."""
    index = os.path.join(directory, "MEMORY.md")
    head = f"[memory] {label} dir {directory}"
    if not os.path.isfile(index):
        return head + " — no memories yet" if part == 1 else ""
    chunks, current = [], ""
    with open(index, encoding="utf-8") as handle:
        lines = handle.read().strip().splitlines(keepends=True)
    for line in lines:
        if current and len(current) + len(line) > CAP - len(head) - 40:
            chunks.append(current)
            current = ""
        current += line
    chunks.append(current)
    if part > len(chunks):
        return ""
    text = f"{head} — index part {part}/{len(chunks)}:\n{chunks[part - 1].rstrip()}"
    if part == parts and len(chunks) > parts:
        shown = sum(chunk.count("\n") for chunk in chunks[:parts])
        text += (
            f"\n[memory] index continues beyond the hooks (line {shown + 1} on): run memory-recall"
            f' index task="<what you are doing>" path=<repo>'
        )
    return text


def memory_dirs(roots: Roots) -> list[tuple[str, int]]:
    """memory-where's memory_dirs on this identity's memory: every dir below the root that holds an index, with its
    memory count, sorted; the personal dir inside the root is left out."""
    store, personal = os.path.realpath(roots.store), os.path.realpath(roots.personal)
    found = []
    for root, dirs, files in os.walk(store):
        dirs[:] = sorted(
            d for d in dirs if not d.startswith(".") and os.path.realpath(os.path.join(root, d)) != personal
        )
        if root != store and "MEMORY.md" in files:
            with open(os.path.join(root, "MEMORY.md"), encoding="utf-8") as handle:
                count = sum(1 for line in handle if line.lstrip().startswith("- "))
            found.append((os.path.relpath(root, store), count))
    return found


def memory_map(roots: Roots) -> str:
    """The text of memory-where's memory-map.md, which ~/.claude/CLAUDE.md imports; whaat builds it at session start
    instead of keeping a file, so only its first sentence differs."""
    rows = [f"- `{rel}` ({count})" for rel, count in memory_dirs(roots)]
    return (
        "## Memory map\n"
        "Built by whaat when a session or a subagent starts; there is no file to edit."
        " Kinds: the global index (the store root, imported above) holds cross-project practice;"
        " `<group>/` holds what is true for every repo of a group; `<group>/<repo>/` holds one codebase's facts;"
        " the personal dir (paths `personal:…`) holds the user and working together."
        " Types: feedback (how to work), project (a fact about a codebase or domain),"
        " reference (a recipe or pointer).\n"
        "Memory dirs below the root (memory count):\n" + "\n".join(rows) + "\n"
        "For a task in another repo than the current one, read its index with memory-recall index"
        ' task="<what you are doing>" repo=<dir>.\n'
    )


def reaches_every_agent(path: str) -> bool:
    """A core file whose frontmatter says `reach: every-agent` goes to subagents too, not only to the main session."""
    with open(path, encoding="utf-8") as handle:
        return bool(EVERY_AGENT.match(handle.read()))


SUBAGENT_CORE_HEAD = "## Personal core for every agent\n"


def every_agent_text(core: str, names: list[str]) -> str:
    """The core files marked `reach: every-agent`, frontmatter dropped."""
    parts = []
    for name in names:
        path = os.path.join(core, name)
        if reaches_every_agent(path):
            with open(path, encoding="utf-8") as handle:
                body = EVERY_AGENT.sub("", handle.read(), count=1).strip()
            parts.append(f"(personal:core/{name})\n{body}")
    return SUBAGENT_CORE_HEAD + ("\n\n".join(parts) if parts else "(no core file has reach: every-agent)") + "\n"


def export_subagent_core(roots: Roots, core: str, names: list[str]) -> None:
    """Write every_agent_text to <state>/subagent-core.md; written on every start, also when nothing is marked, so a
    reader never sees a stale file."""
    roots.state.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    (roots.state / SUBAGENT_CORE).write_text(every_agent_text(core, names), encoding="utf-8")


def subagent_core(roots: Roots) -> str:
    """What a subagent's prompt gets in front, in this order: the global
    index, the every-agent core files when one is marked, then the memory map; the SubagentStart hook splits it
    under the cap."""
    parts = []
    index = os.path.join(roots.store, "MEMORY.md")
    if os.path.isfile(index):
        with open(index, encoding="utf-8") as handle:
            parts.append(handle.read().strip() + "\n")
    core = os.path.join(roots.personal, "core")
    names = sorted(n for n in os.listdir(core) if n.endswith(".md")) if os.path.isdir(core) else []
    marked = [n for n in names if reaches_every_agent(os.path.join(core, n))]
    if marked:
        parts.append(every_agent_text(core, marked))
    parts.append(memory_map(roots))
    return "\n".join(parts)


def personal_start(roots: Roots, source: str, part: int, parts: int, session: str, cli: str) -> str | None:
    """Part `part` of `parts` of the personal core, whole files packed under the cap. Each file put in is logged like
    a recall open (purpose=load); a compaction is logged first, so memory-frame puts a memory in again."""
    personal, session = roots.personal, session[:8]
    core = os.path.join(personal, "core")
    names = sorted(n for n in os.listdir(core) if n.endswith(".md")) if os.path.isdir(core) else []
    if part == 1 and source == "compact":
        _append(roots, [{"at": _now(), "session": session, "op": "compact"}])
    if part == 1 and names:
        export_subagent_core(roots, core, names)
    if not names:
        return None
    when = "The context was just compacted; your" if source == "compact" else "Your"
    head = (
        f"[memory] personal dir {personal}\n{when} core, read at every session start"
        ' (other personal memories are listed by memory-recall index under "personal"):'
    )
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    for name in names:
        with open(os.path.join(core, name), encoding="utf-8") as handle:
            text = f"# personal:core/{name}\n{handle.read().strip()}\n"
        if current and sum(len(t) for _, t in current) + len(text) > CAP - len(head) - 400:
            chunks.append(current)
            current = []
        current.append((name, text))
    chunks.append(current)
    if part > len(chunks) or part > parts:
        return None
    shown = chunks[part - 1]
    body = "\n".join(text for _, text in shown)
    if part == parts and len(chunks) > parts:
        rest = [name for chunk in chunks[parts:] for name, _ in chunk]
        body += "\n[memory] core continues beyond the hooks; before your first reply, open:\n" + "\n".join(
            f'  "{cli}" memory open file={PERSONAL}core/{name} because="session start: core" purpose=load'
            for name in rest
        )
    at = _now()
    _append(
        roots,
        [
            {
                "at": at,
                "session": session,
                "op": "open",
                "file": f"{PERSONAL}core/{name}",
                "trigger": None,
                "because": CORE_LOAD_BECAUSE,
                "purpose": "load",
            }
            for name, _ in shown
        ],
    )
    return (head + "\n" if part == 1 else f"[memory] personal core, part {part}:\n") + body


def session_start(
    roots: Roots, level: str, part: int, parts: int, session: str, source: str, key: list[str] | None, cli: str
) -> dict[str, object]:
    """What one SessionStart hook prints: plain text for an index level, additionalContext for the personal core."""
    if level == "personal":
        text = personal_start(roots, source, part, parts, session, cli)
        return {"text": text, "additional_context": True}
    if level == "global":
        return {"text": index_block("global", roots.store, part, parts) or None, "additional_context": False}
    if level == "map":
        return {"text": memory_map(roots) if part == 1 else None, "additional_context": False}
    lines = []
    if level == "project" and part == 1:
        lines.append(
            f"[memory] store {roots.store} — global index via the global SessionStart hook;"
            " save/update/delete → whaat:memory skill"
        )
        if not key:
            lines.append("[memory] not in a git repo — no project/repo memory")
    if key:
        if level == "project":
            block = index_block(f"project {key[0]}", os.path.join(roots.store, key[0]), part, parts)
        else:
            block = index_block(f"repo {key[0]}/{key[1]}", os.path.join(roots.store, *key), part, parts)
        if block:
            lines.append(block)
    return {"text": "\n".join(lines) or None, "additional_context": False}
