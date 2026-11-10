"""A migration plan: what the skill found, what the user chose on the page, and what the import did.

A plan belongs to one identity and lives in its state dir (`state/migrations/<id>.json`), outside git: the import's
own commits are the record that lasts.
"""

import os
import re
from datetime import datetime
from pathlib import Path

from whaat.identities.registry import STATE_DIR_NAME
from whaat.memory.schemas import (
    MigrationCall,
    MigrationDecisions,
    MigrationImported,
    MigrationPlan,
    MigrationPlanCall,
    MigrationPlanSummary,
    MigrationSource,
)
from whaat.memory.service import INDEX_NAME, MEMORY_DIR, layer_of

PLANS_DIR = "migrations"
PLAN_ID = re.compile(r"^\d{8}-\d{6}(-[A-Za-z0-9]{1,16})?$")
DIR_MODE = 0o700


class PlanNotFoundError(LookupError):
    pass


class PlanDecisionError(ValueError):
    """Decisions the plan cannot take: a target for a source that is not loose, or an unknown source."""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _path(folder: Path, plan_id: str) -> Path:
    if not PLAN_ID.match(plan_id):
        raise PlanNotFoundError(plan_id)
    return folder / STATE_DIR_NAME / PLANS_DIR / f"{plan_id}.json"


def create(identity: str, folder: Path, call: MigrationPlanCall) -> MigrationPlan:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    session = re.sub(r"[^A-Za-z0-9]", "", call.session)[:16]
    plan = MigrationPlan(
        id=f"{stamp}-{session}" if session else stamp,
        identity=identity,
        created_at=_now(),
        session=call.session,
        sources=call.sources,
        state=call.state,
        groups=None,
    )
    save(folder, plan)
    return plan


def load(folder: Path, plan_id: str) -> MigrationPlan:
    path = _path(folder, plan_id)
    if not path.is_file():
        raise PlanNotFoundError(plan_id)
    return MigrationPlan.model_validate_json(path.read_text(encoding="utf-8"))


def save(folder: Path, plan: MigrationPlan) -> None:
    path = _path(folder, plan.id)
    path.parent.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.partial")
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(plan.model_dump_json(indent=1) + "\n")
    partial.replace(path)


def summaries(folder: Path) -> list[MigrationPlanSummary]:
    directory = folder / STATE_DIR_NAME / PLANS_DIR
    found = []
    for path in sorted(directory.glob("*.json"), reverse=True) if directory.is_dir() else []:
        try:
            plan = MigrationPlan.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        found.append(
            MigrationPlanSummary(
                id=plan.id,
                created_at=plan.created_at,
                groups=len(plan.groups) if plan.groups is not None else None,
                imported_at=plan.imported_at,
            )
        )
    return found


def call_of(plan: MigrationPlan) -> MigrationCall:
    return MigrationCall(sources=plan.sources, groups=plan.groups or [], state=plan.state)


def decide(folder: Path, plan: MigrationPlan, decisions: MigrationDecisions) -> MigrationPlan:
    """The user's word from the page: a loose source's new target, and the groups to bring in."""
    sources = list(plan.sources)
    for number, target in decisions.targets.items():
        index = int(number) - 1 if number.isdigit() else -1
        if not 0 <= index < len(sources):
            raise PlanDecisionError(f"no source {number}")
        if sources[index].kind != "loose":
            raise PlanDecisionError(f"source {number} is a {sources[index].kind}; only a loose dir takes a target")
        sources[index] = MigrationSource(path=sources[index].path, kind="loose", target=target)
    decided = plan.model_copy(update={"sources": sources, "groups": decisions.groups, "decided_at": _now()})
    save(folder, decided)
    return decided


def record_import(folder: Path, plan: MigrationPlan, result: MigrationImported) -> MigrationPlan:
    done = plan.model_copy(update={"result": result, "imported_at": _now()})
    save(folder, done)
    return done


def mark_sent(folder: Path, plan: MigrationPlan) -> MigrationPlan:
    sent = plan.model_copy(update={"sent_at": _now()})
    save(folder, sent)
    return sent


def layers_now(folder: Path) -> dict[str, int]:
    root = folder / MEMORY_DIR
    counts = {layer: 0 for layer in ("core", "personal", "global", "project", "repo")}
    for path in root.rglob("*.md") if root.is_dir() else []:
        rel = path.relative_to(root)
        if path.name == INDEX_NAME or any(part.startswith(".") for part in rel.parts):
            continue
        counts[layer_of(rel)] += 1
    return counts
