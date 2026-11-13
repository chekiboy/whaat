"""memory-curation's memory-lint on one identity's memory: mechanical checks, read-only, a markdown report.

Walks every dir holding .md files
below the memory root, so a new level needs no change here; the personal dir is left out of the checks and the
report, but its names count: a link to a personal or core memory resolves, and a personal file's `supersedes` makes
the store file it names history. A broken link whose name matches exactly one memory once case, `-`/`_` and the type
prefix are set aside (an older name form) gets that memory's name as a suggestion.
Stale candidates are checked against each repo's last-fetched origin default ref, never a working tree;
nothing is fetched. Repo roots come from MEMORY_REPO_ROOTS (colon-separated); without it, no path is checked.
Validity: a score starts at the `source` weight and loses 0.2 per 120 days since the latest of `confirmed`, the last
`held` outcome (the identity's memory-outcomes.log) and the file's first commit. A superseded file without an index
line is history: it stays out of the duplicate, stale and validity checks.
Size and index-drift are reported only for a memory unchanged for FRESH_DAYS (one still being shaped is left alone),
and size only when the body is over its budget by more than OVER_BUDGET_SLACK.
"""

import datetime
import itertools
import os
import re
from dataclasses import dataclass
from pathlib import Path

from whaat.memory.recall import Roots
from whaat.memory.validity import (
    DECAY_PER_DAY,
    LEVELS,
    PERSONAL_DIR,
    SOURCE_BASE,
    as_date,
    commit_dates,
    git,
    index_entries,
    is_memory_file,
    parse,
    recall_outcomes,
    validity,
)
from whaat.platform.repo_key import remote_path

TYPES = ("feedback", "project", "reference")
BUDGET = {"reference": 2500}
DEFAULT_BUDGET = 1200
OVER_BUDGET_SLACK = 1.25
FRESH_DAYS = 14
HOOK_PART = 9500
DUP_THRESHOLD = 0.4
STOP = set(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "when",
        "before",
        "after",
        "with",
        "is",
        "it",
        "its",
        "by",
        "as",
        "at",
        "be",
        "from",
        "into",
        "not",
        "this",
        "that",
        "use",
    ]
)
WHEN_FILE = Path(__file__).with_name("when.txt")

Problem = tuple[str, str, str]


def when_vocabulary() -> set[str] | None:
    if not WHEN_FILE.exists():
        return None
    lines = WHEN_FILE.read_text(encoding="utf-8").splitlines()
    return {line.split()[0] for line in lines if line.strip() and not line.startswith("#")}


def as_list(value: str) -> list[str]:
    return [v.strip().strip("\"'") for v in value.strip("[]").split(",") if v.strip()]


def when_problems(p: str, fm: dict[str, str], vocabulary: set[str] | None) -> list[Problem]:
    if "when" not in fm:
        return []
    value = fm["when"]
    if not (value.startswith("[") and value.endswith("]")):
        return [(p, "when", f"when: {value!r}; write the inline form [a, b]")]
    return [
        (p, "when", f"{item!r} is not in the when.txt vocabulary")
        for item in as_list(value)
        if vocabulary is not None and item not in vocabulary
    ]


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower().replace("_", " ")) if w not in STOP and len(w) > 2}


def repo_map(repo_roots: list[Path]) -> dict[str, str]:
    found: dict[str, str] = {}
    for root in repo_roots:
        root_dir = str(root.expanduser())
        if not os.path.isdir(root_dir):
            continue
        for name in sorted(os.listdir(root_dir)):
            path = os.path.join(root_dir, name)
            if not os.path.isdir(os.path.join(path, ".git")):
                continue
            url = git(path, "remote", "get-url", "origin")
            rp = remote_path(url.strip() if url else None, Path(path))
            if rp and rp not in found:
                found[rp] = path
    return found


def default_ref(repo: str) -> str | None:
    head = git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    candidates = [head.strip()] if head else []
    candidates += ["refs/remotes/origin/main", "refs/remotes/origin/develop", "refs/remotes/origin/master"]
    for ref in candidates:
        if git(repo, "rev-parse", "--verify", "--quiet", ref):
            return ref
    return None


def _personal(rel: str) -> bool:
    return rel == PERSONAL_DIR or rel.startswith(PERSONAL_DIR + os.sep)


def _personal_names(personal: str) -> tuple[set[str], dict[str, str]]:
    """The personal dir's memory names, core included, and what its files supersede ({old name: `personal:<name>`});
    read only for resolving links and history, never checked or reported."""
    stems: set[str] = set()
    superseded: dict[str, str] = {}
    for d, dirs, names in os.walk(personal):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        for n in sorted(names):
            if not is_memory_file(d, n, personal):
                continue
            stems.add(n[:-3])
            parsed, _ = parse(os.path.join(d, n))
            old = (parsed or {}).get("supersedes")
            if old:
                superseded.setdefault(old, f"personal:{n[:-3]}")
    return stems, superseded


def _name_key(name: str) -> str:
    key = name.strip().lower().replace("-", "_")
    for typ in (*TYPES, "user"):
        if key.startswith(typ + "_"):
            return key[len(typ) + 1 :]
    return key


def _suggestion(link: str, stems: set[str]) -> str:
    """` (now [[<name>]]?)` when exactly one memory's name matches the link in an older form, else nothing."""
    matches = sorted(stem for stem in stems if _name_key(stem) == _name_key(link))
    return f" (now [[{matches[0]}]]?)" if len(matches) == 1 else ""


@dataclass
class Scan:
    """What the checks found, before the report is written: the lint renders it, the curation brief picks from it."""

    store: str
    files: dict[str, tuple[dict[str, str], str, str]]
    listings: list[tuple[str, list[str], dict[str, str]]]
    problems: list[Problem]
    sizes: list[tuple[str, int, int]]
    vocabulary: set[str] | None
    dups: list[tuple[float, str, str]]
    levels: dict[str, int]
    history: dict[str, str]
    undated: int
    weak: list[tuple[float, str, str, int, str]]
    noisy: list[tuple[int, str]]
    misled: list[str]
    refs: dict[str, tuple[str | None, str, set[str]]]
    repos: dict[str, str]
    stale: list[tuple[str, str]]
    dup_threshold: float


def scan(
    roots: Roots, repo_roots: list[Path], dup_threshold: float = DUP_THRESHOLD, today: datetime.date | None = None
) -> Scan:
    store = roots.store
    today = today or datetime.date.today()
    files: dict[str, tuple[dict[str, str], str, str]] = {}
    problems: list[Problem] = []
    sizes: list[tuple[str, int, int]] = []
    listings: list[tuple[str, list[str], dict[str, str]]] = []
    vocabulary = when_vocabulary()
    added, last = commit_dates(store)
    for d, dirs, names in os.walk(store):
        rel = os.path.relpath(d, store)
        rel = "" if rel == "." else rel
        dirs[:] = sorted(x for x in dirs if not x.startswith(".") and not _personal(os.path.join(rel, x)))
        mds = sorted(n for n in names if is_memory_file(d, n, store))
        idx = os.path.join(d, "MEMORY.md")
        if not mds and not os.path.exists(idx):
            continue
        entries = index_entries(idx)
        if os.path.exists(idx):
            with open(idx, encoding="utf-8") as handle:
                raw = handle.read()
            sizes.append((rel or "(global)", len(entries), len(raw)))
        listings.append((rel, mds, entries))
        for n in sorted(set(entries) - set(mds)):
            problems.append((os.path.join(rel, "MEMORY.md"), "dangling", f"lists {n}, which does not exist"))
        for n in mds:
            p = os.path.join(rel, n)
            parsed, body = parse(os.path.join(d, n))
            files[p] = (parsed or {}, body, rel)
            if parsed is None:
                problems.append((p, "frontmatter", "missing or malformed"))
                continue
            fm = parsed
            stem = n[:-3]
            if fm.get("name") != stem:
                problems.append((p, "name", f"name: {fm.get('name')!r} ≠ filename"))
            typ = fm.get("type") or ""
            if typ not in TYPES:
                problems.append((p, "type", f"type: {typ!r}"))
            elif not stem.startswith(typ + "_"):
                problems.append((p, "type", f"filename prefix ≠ type {typ}"))
            desc = fm.get("description", "")
            if not desc:
                problems.append((p, "description", "missing"))
            changed = as_date(last.get(p))
            settled = changed is not None and (today - changed).days >= FRESH_DAYS
            if settled and n in entries and desc and entries[n].strip("\"'") != desc.strip("\"'"):
                problems.append((p, "index-drift", f"index: {entries[n][:80]!r} / description: {desc[:80]!r}"))
            limit = BUDGET.get(typ, DEFAULT_BUDGET)
            if settled and len(body) > limit * OVER_BUDGET_SLACK:
                problems.append(
                    (p, "over-budget", f"body {len(body)} chars > {limit} by more than {OVER_BUDGET_SLACK - 1:.0%}")
                )
            problems += when_problems(p, fm, vocabulary)
            if fm.get("source") and fm["source"] not in SOURCE_BASE:
                problems.append((p, "source", f"source: {fm['source']!r}"))
            if fm.get("confirmed"):
                day = as_date(fm["confirmed"])
                if day is None:
                    problems.append((p, "confirmed", f"confirmed: {fm['confirmed']!r} is not YYYY-MM-DD"))
                elif day > datetime.date.today():
                    problems.append((p, "confirmed", f"confirmed: {fm['confirmed']} is in the future"))
            if re.search(r"/Users/[^/\s]+/", body):
                problems.append((p, "abs-path", "uses /Users/<name> instead of ~"))

    personal_stems, personal_superseded = _personal_names(roots.personal)
    stems = {os.path.basename(p)[:-3] for p in files}
    superseded: dict[str, str] = {}
    for p, (front, _, _) in sorted(files.items()):
        old = front.get("supersedes")
        if old in superseded:
            problems.append((p, "supersedes", f"{superseded[old]} supersedes {old!r} too; keep one"))
        elif old:
            superseded[old] = p
    retired = {**personal_superseded, **superseded}
    history: dict[str, str] = {}
    for rel, mds, entries in listings:
        for n in mds:
            p, stem = os.path.join(rel, n), n[:-3]
            if stem in retired and n in entries:
                problems.append(
                    (
                        p,
                        "supersedes",
                        f"{retired[stem]} supersedes it, yet it is indexed: if the pair "
                        "is right, drop this index line, else fix that file's supersedes name",
                    )
                )
            elif stem in retired:
                history[p] = retired[stem]
            elif n not in entries:
                problems.append((p, "unindexed", "no line in this dir's MEMORY.md"))
    for old, by in sorted(superseded.items()):
        if old not in stems | personal_stems:
            problems.append((by, "supersedes", f"supersedes {old!r}, which does not exist"))
    known = stems | personal_stems
    for p, (_, body, _) in files.items():
        for link in sorted(set(re.findall(r"\[\[([^\]]+)\]\]", body))):
            if link not in known:
                problems.append((p, "broken-link", f"[[{link}]]{_suggestion(link, known)}"))

    keys = sorted(set(files) - set(history))
    sig = {p: words(os.path.basename(p)[:-3] + " " + files[p][0].get("description", "")) for p in keys}
    dups = []
    for a, b in itertools.combinations(keys, 2):
        if not sig[a] or not sig[b]:
            continue
        j = len(sig[a] & sig[b]) / len(sig[a] | sig[b])
        if j >= dup_threshold:
            dups.append((j, a, b))

    held, counts = recall_outcomes(str(roots.state), {os.path.basename(p)[:-3]: last.get(p, "") for p in files})
    levels: dict[str, int] = {}
    weak = []
    undated = 0
    for p, (fm, _, _) in files.items():
        if p in history:
            continue
        stem = os.path.basename(p)[:-3]
        v = validity(fm, [fm.get("confirmed"), held.get(stem), added.get(p)], today)
        if not v:
            undated += 1
            continue
        score, level, age = v
        levels[level] = levels.get(level, 0) + 1
        if level in ("uncertain", "stale"):
            weak.append((score, p, level, age, fm.get("source") or "?"))
    noisy = sorted((c.get("irrelevant", 0), stem) for stem, c in counts.items() if c.get("irrelevant", 0) >= 2)
    misled = sorted(stem for stem, c in counts.items() if c.get("misled"))

    repos = repo_map(repo_roots)
    stale = []
    refs: dict[str, tuple[str | None, str, set[str]]] = {}
    for p, (_, body, rel) in files.items():
        repo = repos.get(rel) if rel.count("/") >= 1 and p not in history else None
        if not repo:
            continue
        if repo not in refs:
            ref = default_ref(repo)
            tree = set((git(repo, "ls-tree", "-r", "--name-only", ref) or "").splitlines()) if ref else set()
            date = (git(repo, "log", "-1", "--format=%cs", ref) or "").strip() if ref else ""
            refs[repo] = (ref, date, tree)
        _, _, tree = refs[repo]
        if not tree:
            continue
        for cand in sorted(set(re.findall(r"`([\w.-]+(?:/[\w.-]+)+\.\w{1,5})`", body))):
            if cand.startswith(("~", "/")) or "://" in cand:
                continue
            if cand not in tree and not any(t.endswith("/" + cand) for t in tree):
                stale.append((p, cand))

    return Scan(
        store,
        files,
        listings,
        problems,
        sizes,
        vocabulary,
        dups,
        levels,
        history,
        undated,
        weak,
        noisy,
        misled,
        refs,
        repos,
        stale,
        dup_threshold,
    )


def lint(
    roots: Roots, repo_roots: list[Path], dup_threshold: float = DUP_THRESHOLD, today: datetime.date | None = None
) -> str:
    s = scan(roots, repo_roots, dup_threshold, today)
    store, sizes, problems, vocabulary, dups, levels = s.store, s.sizes, s.problems, s.vocabulary, s.dups, s.levels
    history, undated, weak, noisy, misled, refs = s.history, s.undated, s.weak, s.noisy, s.misled, s.refs
    repos, stale, files = s.repos, s.stale, s.files
    out = [f"# memory-lint — {store}\n", "## Index sizes\n"]
    out.append("| Dir | Entries | Chars | Hook parts (9500 chars each) |\n|---|---|---|---|")
    for rel, count, chars in sizes:
        out.append(f"| {rel} | {count} | {chars} | {-(-chars // HOOK_PART)} |")
    out.append(f"\n## Problems ({len(problems)})\n")
    if problems:
        out.append("| File | Check | Detail |\n|---|---|---|")
        for p, check, detail in sorted(problems, key=lambda x: (x[1], x[0])):
            out.append(f"| {p} | {check} | {detail.replace('|', '/')} |")
    if vocabulary is None:
        out.append("\nThe when.txt vocabulary is missing, so `when` values were not checked.")
    out.append(f"\n## Duplicate candidates ({len(dups)}, name+description word overlap ≥ {dup_threshold})\n")
    for j, a, b in sorted(dups, reverse=True):
        out.append(f"- {j:.2f} {a} ↔ {b}")
    tally = [f"{name} {levels[name]}" for _, name in LEVELS if name in levels]
    tally += [f"history {len(history)}"] + ([f"undated {undated}"] if undated else [])
    out.append(f"\n## Validity ({', '.join(tally)})\n")
    out.append(
        f"The source weight minus {DECAY_PER_DAY * 120:.1f} per 120 days since the latest of `confirmed`, the last"
    )
    out.append("`held` outcome and the first commit. Stale files are `verify` candidates;")
    out.append("history files are superseded and never acted on.\n")
    for score, p, level, age, source in sorted(weak):
        out.append(f"- {level} {score:.2f}: {p} ({age} days, source {source})")
    for old, by in sorted(history.items()):
        out.append(f"- history: {old}, superseded by {by}")
    out.append(f"\n## Recall outcomes ({len(noisy)} noisy triggers, {len(misled)} misled)\n")
    for times, stem in sorted(noisy, reverse=True):
        out.append(f"- irrelevant {times}×: {stem} — its index line fires for the wrong tasks (`retrigger`)")  # noqa: RUF001
    for stem in misled:
        out.append(f"- misled: {stem} — check that it was fixed or superseded")
    out.append(f"\n## Stale candidates ({len(stale)}): backticked paths missing from the repo's origin default ref\n")
    for repo, (ref, date, tree) in sorted(refs.items()):
        out.append(f"- {repo}: {ref or 'no origin ref'} @ {date or '?'}, {len(tree)} files")
    unmapped = sorted({rel for _, _, rel in files.values() if rel.count("/") >= 1 and rel not in repos})
    if unmapped:
        out.append(f"- not checked, no local clone found: {', '.join(unmapped)}")
    out.append("")
    for p, cand in stale:
        out.append(f"- {p}: `{cand}`")
    return "\n".join(out)
