"""memory-validity and memory-outcome on one identity's memory: scores, read and outcome logs, the Read hook's note.

A score starts at the `source` weight and loses 0.2 per 120 days since the latest of `confirmed`, the last `held`
outcome and the file's first commit. A superseded file without an index line is history and is not scored. The logs
(memory-reads.log, memory-outcomes.log: one tab-separated line per event) and memory-validity.json sit in the
identity's state dir. The personal dir is left out everywhere: it is not scored,
its reads are not logged, and its outcomes are not recorded.
"""

import datetime
import json
import os
import re
import subprocess
import tempfile

from whaat.memory.recall import DIR_MODE, LOG_NAME, Roots

SOURCE_BASE: dict[str | None, float] = {"measured": 1.0, "user-decision": 1.0, "inference": 0.75, None: 0.9}
DECAY_PER_DAY = 0.2 / 120
LEVELS = ((0.8, "certain"), (0.6, "likely"), (0.4, "uncertain"), (0.0, "stale"))
UNQUOTED_FIELDS = ("source", "confirmed", "supersedes")
SCORES_FILE = "memory-validity.json"
READS_LOG = "memory-reads.log"
OUTCOMES_LOG = "memory-outcomes.log"
OUTCOMES = ("held", "misled", "irrelevant")
MEMORY_MAP = "memory-map.md"
ORIGINS_FILE = "memory-origins.json"
STATE_DIR = "state"
PERSONAL_DIR = "personal"
WEAK_TRUTH = "⚠ Weak truthness: {why}."


class OutcomeError(ValueError):
    """A call memory-outcome would refuse, with its message."""


def _personal(rel: str) -> bool:
    return rel == PERSONAL_DIR or rel.startswith(PERSONAL_DIR + os.sep)


def git(directory: str, *args: str) -> str | None:
    try:
        result = subprocess.run(["git", "-C", directory, *args], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def parse(path: str) -> tuple[dict[str, str] | None, str]:
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
    if not m:
        return None, text
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"\s*(\w+):\s*(.*)", line)
        if kv:
            value = kv.group(2).strip()
            fm.setdefault(kv.group(1), value.strip("\"'") if kv.group(1) in UNQUOTED_FIELDS else value)
    return fm, m.group(2)


def index_entries(idx: str) -> dict[str, str]:
    entries = {}
    if os.path.exists(idx):
        with open(idx, encoding="utf-8") as handle:
            for line in handle:
                m = re.match(r"\s*-\s*\[?([\w.-]+\.md)\]?(?:\([^)]*\))?\s*[—-]+\s*(.*)", line)
                if m:
                    entries[m.group(1)] = m.group(2).strip()
    return entries


def load_origins(store: str) -> dict[str, dict[str, str]]:
    """The source dates a migration carried in (state/memory-origins.json beside the memory dir): per path as it was
    imported, the source's first and last commit day and the import day."""
    try:
        with open(os.path.join(os.path.dirname(store), STATE_DIR, ORIGINS_FILE), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def commit_dates(store: str) -> tuple[dict[str, str], dict[str, str]]:
    """Per current path: the day it was first added (followed across renames and moves) and the day it last changed.
    `--relative` limits the log to the memory dir and names paths from it, as in a store that is its own repo. A file a
    migration brought in keeps its source's days: the import commit counts as neither its first nor its last change."""
    origins = load_origins(store)
    changes: list[tuple[str, list[str]]] = []
    current = None
    out = git(store, "log", "--relative", "-M", "--format=%x00%cs", "--name-status") or ""
    for line in out.splitlines():
        if line.startswith("\0"):
            current = line[1:]
        elif line and current:
            changes.append((current, line.split("\t")))
    added: dict[str, str] = {}
    last: dict[str, str] = {}
    for day, parts in reversed(changes):
        status, path = parts[0], parts[-1]
        if status.startswith("R") and len(parts) == 3:
            added[path] = added.pop(parts[1], day)
            last.pop(parts[1], None)
        elif status.startswith("D"):
            added.pop(path, None)
            last.pop(path, None)
            continue
        elif path not in added and (origin := origins.get(path)) and origin.get("imported") == day:
            added[path] = origin.get("added") or day
            last[path] = origin.get("last") or day
            continue
        else:
            added.setdefault(path, day)
        last[path] = day
    return added, last


def recall_outcomes(state: str, changed: dict[str, str]) -> tuple[dict[str, str], dict[str, dict[str, int]]]:
    """From the outcome log: last `held` day per memory name, and outcome counts since the memory last changed."""
    path = os.path.join(state, OUTCOMES_LOG)
    held: dict[str, str] = {}
    counts: dict[str, dict[str, int]] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) != 4:
                    continue
                day, outcome, rel = parts[0], parts[1], parts[2]
                stem = os.path.basename(rel)[:-3]
                if stem not in changed:
                    continue
                if day > changed[stem]:
                    counts.setdefault(stem, {}).setdefault(outcome, 0)
                    counts[stem][outcome] += 1
                if outcome == "held":
                    held[stem] = max(day, held.get(stem, day))
    return held, counts


def as_date(value: object) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def validity(fm: dict[str, str], anchors: list[str | None], today: datetime.date) -> tuple[float, str, int] | None:
    days = [d for d in map(as_date, anchors) if d]
    if not days:
        return None
    age = (today - max(days)).days
    base = SOURCE_BASE.get(fm.get("source"), SOURCE_BASE[None])
    score = max(0.0, base - DECAY_PER_DAY * age)
    return score, next(name for floor, name in LEVELS if score >= floor), age


def is_memory_file(directory: str, name: str, store: str) -> bool:
    if not name.endswith(".md") or name == "MEMORY.md":
        return False
    return name != MEMORY_MAP or os.path.realpath(directory) != os.path.realpath(store)


def score_store(store: str, state: str, today: datetime.date) -> dict[str, dict[str, object]]:
    """{rel path: entry} for every memory file outside the personal dir; history files carry `history`."""
    files: dict[str, tuple[dict[str, str], bool]] = {}
    for d, dirs, names in os.walk(store):
        dirs[:] = sorted(x for x in dirs if not x.startswith(".") and not (d == store and x == PERSONAL_DIR))
        index = index_entries(os.path.join(d, "MEMORY.md"))
        for n in sorted(x for x in names if is_memory_file(d, x, store)):
            rel = os.path.relpath(os.path.join(d, n), store)
            fm, _ = parse(os.path.join(d, n))
            files[rel] = (fm or {}, n in index)
    superseded = {fm["supersedes"]: rel for rel, (fm, _) in sorted(files.items()) if fm.get("supersedes")}
    added, last = commit_dates(store)
    held, counts = recall_outcomes(state, {os.path.basename(p)[:-3]: last.get(p, "") for p in files})
    entries: dict[str, dict[str, object]] = {}
    for rel, (fm, indexed) in sorted(files.items()):
        stem = os.path.basename(rel)[:-3]
        anchors = {"confirmed": fm.get("confirmed"), "held": held.get(stem), "first_commit": added.get(rel)}
        entry: dict[str, object] = {
            "description": fm.get("description", "").strip("\"'"),
            "source": fm.get("source"),
            "anchors": {k: v for k, v in anchors.items() if as_date(v)},
        }
        if counts.get(stem):
            entry["outcomes"] = counts[stem]
        if stem in superseded and not indexed:
            entry["history"] = superseded[stem]
        else:
            v = validity(fm, list(anchors.values()), today)
            if v:
                entry.update(score=round(v[0], 3), level=v[1], age_days=v[2])
        entries[rel] = entry
    return entries


def refresh(roots: Roots) -> dict[str, object]:
    store, state, today = roots.store, str(roots.state), datetime.date.today()
    data: dict[str, object] = {
        "generated": today.isoformat(),
        "store": store,
        "rule": "source weight ("
        + ", ".join(f"{k or 'unset'} {v}" for k, v in SOURCE_BASE.items())
        + ") minus 0.2 per 120 days since the latest anchor",
        "levels": {name: floor for floor, name in LEVELS},
        "memories": score_store(store, state, today),
    }
    roots.state.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=state, prefix=".memory-validity.")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp, os.path.join(state, SCORES_FILE))
    return data


def load(roots: Roots, fresh: bool = True) -> dict[str, object]:
    """The stored scores; rescored first when the file is missing, from an earlier day, or of another store."""
    path = roots.state / SCORES_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    stale = not data or data.get("generated") != datetime.date.today().isoformat() or data.get("store") != roots.store
    if fresh and stale:
        data = refresh(roots)
    return data or {}


def entry_of(path: str, data: dict[str, object]) -> tuple[str, dict[str, object] | None]:
    store = str(data["store"])
    absolute = os.path.realpath(path if os.path.isabs(path) else os.path.join(store, path))
    rel = os.path.relpath(absolute, store)
    memories = data["memories"]
    return rel, memories.get(rel) if isinstance(memories, dict) else None


def refresh_summary(roots: Roots) -> str:
    data = refresh(roots)
    tally: dict[str, int] = {}
    memories = data["memories"]
    for entry in memories.values() if isinstance(memories, dict) else []:
        key = "history" if "history" in entry else entry.get("level", "undated")
        tally[key] = tally.get(key, 0) + 1
    return f"{roots.state / SCORES_FILE}: {', '.join(f'{k} {v}' for k, v in sorted(tally.items()))}"


def levels(roots: Roots, paths: list[str]) -> str:
    data = load(roots)
    lines = []
    for path in paths:
        rel, entry = entry_of(path, data)
        if entry is None:
            lines.append(f"{rel}: not a memory in the store")
        elif "history" in entry:
            lines.append(f"{rel}: history, superseded by {entry['history']}")
        elif "level" not in entry:
            lines.append(f"{rel}: undated")
        else:
            source = entry["source"] or "unset"
            lines.append(f"{rel}: {entry['level']} {entry['score']:.2f} ({entry['age_days']} days, source {source})")
    return "\n".join(lines)


def _append(roots: Roots, name: str, fields: list[str]) -> None:
    roots.state.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    with (roots.state / name).open("a", encoding="utf-8") as handle:
        handle.write("\t".join([datetime.date.today().isoformat(), *fields]) + "\n")


def read_note(roots: Roots, session: str, path: str) -> str | None:
    """memory-outcome --hook: log a Read of a memory (not an index, not personal) and name a history, uncertain or
    stale one; None when there is nothing to say."""
    rel = os.path.relpath(os.path.realpath(path), roots.store)
    if rel.startswith("..") or not rel.endswith(".md") or os.path.basename(rel) == "MEMORY.md" or _personal(rel):
        return None
    _append(roots, READS_LOG, ["read", rel, session[:8]])
    _, entry = entry_of(path, load(roots))
    if not entry:
        return None
    if "history" in entry:
        note = f"superseded by {entry['history']}: history, never act on it"
    elif entry.get("level") in ("uncertain", "stale"):
        note = (
            f"{entry['level']} ({entry['score']:.2f}, {entry['age_days']} days since it was last confirmed, "
            "held or added): check that it still holds before acting on it"
        )
    else:
        return None
    return f"Memory {rel} is {note}."


def reads(roots: Roots, session: str) -> str:
    seen: list[str] = []
    path = roots.state / READS_LOG
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) == 4 and parts[3] == session and parts[2] not in seen:
                seen.append(parts[2])
    recall = roots.state / LOG_NAME
    if recall.exists():
        for line in recall.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict) or event.get("session") != session:
                continue
            if event.get("op") == "open":
                files = [event.get("file")]
            elif event.get("op") == "dump":
                files = event.get("files") or []
            else:
                continue
            for rel in files:
                entry = f"{rel} — {event.get('purpose', 'recall')}, because: {event.get('because', '')}"
                seen = [s for s in seen if s != rel]
                if entry not in seen:
                    seen.append(entry)
    return "\n".join(seen) if seen else f"no store reads logged for session {session}"


def record(roots: Roots, session: str, outcome: str, paths: list[str]) -> str:
    if outcome not in OUTCOMES:
        raise OutcomeError(f"outcome must be one of {', '.join(OUTCOMES)}")
    session = session[:8]
    if not session:
        raise OutcomeError("no session id: pass <session8>, or run inside Claude Code")
    lines, done = [], 0
    for rel in paths:
        if not rel.endswith(".md") or _personal(rel) or not os.path.isfile(os.path.join(roots.store, rel)):
            lines.append(f"skipped {rel}: not a memory file in the store (use the path `reads` prints)")
            continue
        _append(roots, OUTCOMES_LOG, [outcome, rel, session])
        done += 1
    lines.append(f"recorded {outcome} for {done} memories")
    if outcome == "held" and done:
        refresh(roots)
    return "\n".join(lines)


def quality(roots: Roots, file: str) -> str:
    """Truthness and validity of a memory as `index` names it, for the note that brings it back: what backs it and how
    its recalls went since its last change, then its level, score and age (or history), and, when one of them is weak,
    a `⚠` line that names the state of that knowledge, not what to do: the skill leaves that to the situation. A
    personal memory is not scored; its truthness comes from its frontmatter alone."""
    if file.startswith("personal:"):
        fm, _ = parse(os.path.join(roots.personal, file[len("personal:") :]))
        source = (fm or {}).get("source")
        lines = [f"Truthness: source {source or 'unset'}", "Validity: not scored (personal memory)"]
        if source == "inference":
            lines.append(WEAK_TRUTH.format(why="it was inferred, not measured or decided by the user"))
        return "\n".join(lines)
    _, entry = entry_of(file, load(roots))
    if entry is None and os.path.isfile(os.path.join(roots.store, file)):
        _, entry = entry_of(file, refresh(roots))  # added after today's scores were written
    if entry is None:
        return "Truthness: unknown\nValidity: not scored"
    raw = entry.get("outcomes")
    outcomes: dict[str, int] = raw if isinstance(raw, dict) else {}
    tally = ", ".join(f"{name} {outcomes.get(name, 0)}" for name in OUTCOMES)
    lines = [f"Truthness: source {entry.get('source') or 'unset'}; since its last change {tally}"]
    if "history" in entry:
        lines.append(f"Validity: history, superseded by {entry['history']}")
        lines.append(f"⚠ History: {entry['history']} replaced it.")
        return "\n".join(lines)
    if "level" not in entry:
        lines.append("Validity: undated (no confirmed date, held outcome or commit)")
    else:
        lines.append(
            f"Validity: {entry['level']} {entry['score']:.2f} ({entry['age_days']} days since it was last confirmed,"
            " held or added)"
        )
        if entry["level"] in ("uncertain", "stale"):
            lines.append(
                f"⚠ {str(entry['level']).capitalize()}: nobody has confirmed it or relied on it for {entry['age_days']}"
                " days."
            )
    reasons = []
    if entry.get("source") == "inference":
        reasons.append("it was inferred, not measured or decided by the user")
    if outcomes.get("misled"):
        reasons.append(f"it misled {outcomes['misled']} time(s) since its last change")
    if reasons:
        lines.append(WEAK_TRUTH.format(why=" and ".join(reasons)))
    return "\n".join(lines)
