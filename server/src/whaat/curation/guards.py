"""The guards a curation report passes before whaat saves it: each row carries what its actions require. A refusal
names the row, so the agent fixes it and saves again."""

import re

from whaat.curation.view import resolver, row_files, scan_store
from whaat.reports.types.memory_curation import CurationRow

INDEX_LINE_LIMIT = 150
BUILDS_ON = re.compile(r"\b(needs?|after|leaves?|builds? on|once)\b", re.I)


def problems(memory_dir: str, rows: list[CurationRow]) -> list[str]:
    dirs = scan_store(memory_dir)
    resolve = resolver(dirs)
    found: list[str] = []
    for row in rows:

        def say(text: str, n: int = row.n) -> None:
            found.append(f"row {n}: {text}")

        files, into, dest = row_files(row, resolve)
        if not files:
            say(f"{row.file!r} names no memory of this identity")
        acts = row.actions
        for action in ("fix", "split"):
            if action in acts and not (row.target or "").strip():
                say(f"`{action}` needs a target (the corrected text, or the new file names)")
        if "merge" in acts and into is None:
            say("`merge` needs a target that is another existing memory")
        if "move" in acts:
            if dest is None and re.search(r"\broot\b", row.target or "", re.I):
                dest = ""
            if dest is None:
                say("`move` needs a target dir (in backticks) or the root")
            elif any(f[0] == dest for f in files):
                say(f"`move` target {dest or 'the root'} is the dir the file is in")
        if "retrigger" in acts and len((row.target or "").strip().strip("\"'“”")) > INDEX_LINE_LIMIT:
            say(f"`retrigger` target is over {INDEX_LINE_LIMIT} chars")
        for action in ("delete", "fix", "move"):
            if action in acts and not (row.evidence or "").strip():
                say(f"`{action}` needs evidence")
        if len(acts) > 1 and not BUILDS_ON.search(row.reason):
            say("a row with several actions says in its reason what the later one needs from the earlier")
    return found
