"""The brief a curation judge gets for one memory dir: the skill's fixed judge-brief text, the dir, how to read it, and
the dir's candidates from the lint's checks. It is put together here, never written by the agent of a run, so every
run judges by the same words and the same list."""

import json
import os
from pathlib import Path
from typing import Any

from whaat.memory.lint import Scan

INDEX_LINE_LIMIT = 150
SKILL_DIR = Path(__file__).resolve().parents[4] / "connectors/claude_code/skills/memory-curation"
BRIEF_FILE = SKILL_DIR / "judge-brief.md"
REFUTE_FILE = SKILL_DIR / "refute-brief.md"
WHAAT = Path(__file__).resolve().parents[4] / "connectors/claude_code/scripts/whaat"

Candidate = tuple[str, str, str]


def _dir(path: str) -> str:
    return os.path.dirname(path)


def candidates(s: Scan) -> dict[str, list[Candidate]]:
    """Per dir ("" is the global one): every file a check names, with the check and its detail."""
    found: dict[str, list[Candidate]] = {}

    def add(path: str, check: str, detail: str) -> None:
        found.setdefault(_dir(path), []).append((path, check, detail))

    by_stem = {os.path.basename(p)[:-3]: p for p in s.files}
    for rel, mds, entries in s.listings:
        for n in mds:
            line = entries.get(n)
            p = os.path.join(rel, n)
            if line is not None and p not in s.history and len(line) > INDEX_LINE_LIMIT:
                add(p, "long-index-line", f"{len(line)} chars > {INDEX_LINE_LIMIT}: {line}")
    for p, cand in s.stale:
        repo = s.repos.get(s.files[p][2])
        ref, date, _ = s.refs.get(repo or "", (None, "", set()))
        add(p, "missing-path", f"`{cand}` not on {ref} @ {date}")
    for score, p, level, age, source in sorted(s.weak):
        add(p, "validity", f"{level} {score:.2f} ({age} days, source {source})")
    for j, a, b in sorted(s.dups, reverse=True):
        add(a, "duplicate-candidate", f"word overlap {j:.2f} with {b}")
        add(b, "duplicate-candidate", f"word overlap {j:.2f} with {a}")
    for times, stem in s.noisy:
        if stem in by_stem:
            add(by_stem[stem], "noisy-trigger", f"opened for the wrong task {times}×")  # noqa: RUF001
    for stem in s.misled:
        if stem in by_stem:
            add(by_stem[stem], "misled", "a session was misled by it")
    # over budget is the lint's own finding: over by more than 25% and unchanged for 14 days
    for p, check, detail in sorted(s.problems):
        add(p, "over-budget" if check == "over-budget" else f"lint-{check}", detail)
    return found


def dirs(s: Scan) -> list[str]:
    return [rel for rel, _, _ in s.listings]


def brief(s: Scan, rel: str) -> str:
    items = candidates(s).get(rel, [])
    refs = [f"- {repo}: {ref or 'no origin ref'} @ {date or '?'}" for repo, (ref, date, _) in sorted(s.refs.items())]
    listing = "\n".join(f"- {p}: {check} — {detail}" for p, check, detail in items) or "- (none)"
    count = next((len(mds) for d, mds, _ in s.listings if d == rel), 0)
    text = BRIEF_FILE.read_text(encoding="utf-8")
    return (
        text.replace("{{DIR}}", rel or "(global: the memory root)")
        .replace("{{FILES}}", str(count))
        .replace(
            "{{DUMP}}",
            f'{WHAAT} memory dump dir={rel or "."} purpose=curate because="curation judge of {rel or "global"}"',
        )
        .replace("{{REFS}}", "\n".join(refs) or "- (no repo refs)")
        .replace("{{CANDIDATES}}", listing)
        .replace("{{CANDIDATE_COUNT}}", str(len(items)))
    )


def _dump(rel: str, who: str) -> str:
    return f'{WHAAT} memory dump dir={rel or "."} purpose=curate because="curation {who} of {rel or "global"}"'


def _refs(s: Scan) -> str:
    lines = [f"- {repo}: {ref or 'no origin ref'} @ {date or '?'}" for repo, (ref, date, _) in sorted(s.refs.items())]
    return "\n".join(lines) or "- (no repo refs)"


def refute_brief(s: Scan, rel: str, rows: list[dict[str, Any]]) -> str:
    """The refuter's fixed text with the judge's rows of this dir, as the judge returned them."""
    text = REFUTE_FILE.read_text(encoding="utf-8")
    listed = json.dumps(rows, indent=1, ensure_ascii=False)
    return (
        text.replace("{{DIR}}", rel or "(global: the memory root)")
        .replace("{{DUMP}}", _dump(rel, "refuter"))
        .replace("{{REFS}}", _refs(s))
        .replace("{{ROWS}}", listed)
    )
