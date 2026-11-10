"""The fidelity table after a merge, split or trim: every
sentence of the memory as it was, and whether it is still found word for word in the new text. Each one that is not
needs a line of account from the agent (reworded where, moved where, cut as narrative) before the commit."""

import re
import subprocess
from pathlib import Path

SENTENCE = re.compile(r"(?<=[.!?:])\s+|\n+")


def _body(text: str) -> str:
    m = re.match(r"---\n.*?\n---\n?(.*)", text, re.S)
    return m.group(1) if m else text


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*_`>]|^\s*[-\d.]+\s+", "", text)).strip().lower()


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE.split(_body(text)) if len(_norm(s)) > 3]


def old_text(store: Path, file: str, rev: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(store), "show", f"{rev}:./{file}"], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise FileNotFoundError(f"{file} at {rev}: {out.stderr.strip()}")
    return out.stdout


def table(store: Path, file: str, rev: str, new: list[str]) -> str:
    before = sentences(old_text(store, file, rev))
    after = {n: _norm(_body((store / n).read_text(encoding="utf-8"))) for n in new if (store / n).is_file()}
    missing_files = [n for n in new if n not in after]
    rows, open_ = [], 0
    for i, sentence in enumerate(before, 1):
        where = next((n for n, text in after.items() if _norm(sentence) in text), None)
        if where is None:
            open_ += 1
        rows.append(f"| {i} | {'kept in ' + where if where else '**account for it**'} | {sentence.replace('|', '/')} |")
    head = [
        f"# Fidelity: {file} at {rev} → {', '.join(new)}",
        "",
        f"{len(before)} sentences; {len(before) - open_} kept word for word; {open_} to account for: reworded where,"
        " moved where, or cut as narrative. A changed meaning is fixed before the commit.",
    ]
    if missing_files:
        head.append(f"Not found (not counted): {', '.join(missing_files)}")
    return "\n".join([*head, "", "| # | Now | Sentence before |", "|---|---|---|", *rows])
