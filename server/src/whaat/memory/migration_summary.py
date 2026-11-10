"""The migration's answers as short text for the agent: the counts come from whaat, so nobody counts a long JSON by
hand (a trial agent that did so reported every group one file too many, 2026-11-09). `--json` still gives it all."""

from typing import Any

HEAD = ("group", "files", "new", "same", "conflicts", "history", "rewritten", "dropped", "converted")


def _table(rows: list[tuple[str, ...]]) -> list[str]:
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return [
        "  ".join(
            cell.ljust(width) if i == 0 else cell.rjust(width)
            for i, (cell, width) in enumerate(zip(row, widths, strict=True))
        )
        for row in rows
    ]


def listing(groups: list[dict[str, Any]], warnings: list[str]) -> list[str]:
    rows = [HEAD] + [
        (
            g["id"],
            *(str(len(g[key])) for key in ("files", "new", "same", "conflicts", "unindexed", "rewritten", "dropped")),
            str(len(g["converted"])),
        )
        for g in groups
    ]
    out = [f"warning: {w}" for w in warnings] + _table(rows)
    out.append(f"total: {sum(len(g['files']) for g in groups)} files in {len(groups)} groups")
    for g in groups:
        out += [f"conflict {g['id']}: {f}" for f in g["conflicts"]]
    for g in groups:
        out += [f"history {g['id']}: {f}" for f in g["unindexed"]]
    for g in groups:
        out += [f"dropped {g['id']}: {line}" for line in g["dropped"]]
    for g in groups:
        out += [f"needs a decision {c['file']}: {' '.join(c['notes'])}" for c in g["converted"] if c["notes"]]
    return out


def plan(view: dict[str, Any]) -> str:
    head = [f"plan: {view['plan']['id']}", f"identity: {view['plan']['identity']}", f"page: {view['url']}"]
    return "\n".join(head + listing(view["listing"]["groups"], view["listing"]["warnings"]))


def imported(result: dict[str, Any]) -> str:
    rows = [("group", "copied", "same", "conflicts", "commit")] + [
        (g["id"], str(len(g["copied"])), str(len(g["same"])), str(len(g["conflicts"])), (g["commit"] or "-")[:10])
        for g in result["groups"]
    ]
    out = [f"warning: {w}" for w in result["warnings"]] + _table(rows)
    out.append(f"total: {sum(len(g['copied']) for g in result['groups'])} copied")
    out.append(f"dates carried: {result['origins']} files; outcome lines carried: {result['outcomes']}")
    out += [f"no link to or from: {rel}" for rel in result.get("unlinked", [])]
    if result.get("core_linked"):
        out.append(f"core files linked to each other: {', '.join(result['core_linked'])}")
    if result.get("core_defaults"):
        out.append(f"default core added (fill them in): {', '.join(result['core_defaults'])}")
    for g in result["groups"]:
        out += [f"conflict {g['id']}: {f}" for f in g["conflicts"]]
    for g in result["groups"]:
        out += [f"edited here since an earlier import {g['id']}: {f}" for f in g.get("edited", [])]
    for g in result["groups"]:
        out += [f"dropped {g['id']}: {line}" for line in g["dropped"]]
    for g in result["groups"]:
        out += [f"needs a decision {c['file']}: {' '.join(c['notes'])}" for c in g["converted"] if c["notes"]]
    return "\n".join(out)
