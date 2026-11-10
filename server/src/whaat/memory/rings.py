"""The Memória-pilot (distilled/pilot, build_pilot.py) on an identity's live memory, rendered from its template: the
core in the middle, the memory dirs around it as themes in layer order, the memories as cards.

The level is whaat's validity, named as the pilot names its levels; the halflife is the pilot's, estimated from the
memory's type and shown only on the opened card. A superseded memory is the pilot's "old" card, tied to its successor.
"""

import json
import re
import time
from collections import Counter
from collections.abc import Callable
from datetime import date
from pathlib import Path

from whaat.memory.labels import Language, label
from whaat.memory.schemas import MemoryCard, MemoryLayerView

TEMPLATE = Path(__file__).parent / "views" / "rings_template.html"
LEVELS = ["certain", "likely", "uncertain", "stale", "unscored"]
HALFLIFE = {"code-fact": 30, "tool-gotcha": 90, "work-practice": 120, "value": 365}
HALFLIFE_OF_TYPE = {"project": "code-fact", "reference": "tool-gotcha", "feedback": "work-practice", "user": "value"}
LAYER_ORDER = ["personal", "global", "project", "repo"]


def _when(card: MemoryCard) -> list[str]:
    return [w.strip() for w in card.frontmatter.get("when", "").strip("[]").split(",") if w.strip()]


def render(identity: str, layers: list[MemoryLayerView], embed: bool = False, lang: Language = "en") -> str:
    """The template with this identity's memory as its data slot; the level keys are the validity's own, their words
    in the given language."""
    themed = [layer for layer in layers if layer.layer in LAYER_ORDER]
    themed.sort(key=lambda layer: (LAYER_ORDER.index(layer.layer), layer.dir))
    themes = {
        f"t{i}": f"{label(lang, f'layer.{layer.layer}')} · "
        f"{layer.dir if layer.layer in ('project', 'repo') else layer.layer}"
        for i, layer in enumerate(themed)
    }
    id_of_path = {
        card.path: card.frontmatter.get("name") or Path(card.path).stem for layer in layers for card in layer.memories
    }
    cards = []
    levels: Counter[str] = Counter()
    whens: Counter[str] = Counter()
    by_halflife: Counter[str] = Counter()
    for i, layer in enumerate(themed):
        for card in layer.memories:
            v = card.validity
            old = bool(v and v.history)
            level = "stale" if old else ((v.level if v else None) or "unscored")
            level = level if level in LEVELS else "unscored"
            halflife = HALFLIFE_OF_TYPE.get(card.frontmatter.get("type", ""), "work-practice")
            if not old:
                levels[level] += 1
                whens.update(_when(card))
                by_halflife[f"{halflife}:{level}"] += 1
            cards.append(
                {
                    "id": id_of_path[card.path],
                    "kind": "old" if old else (card.frontmatter.get("type") or "memory"),
                    "text": card.frontmatter.get("description") or re.sub(r"\s+", " ", card.body)[:200],
                    "level": level,
                    "score": round(v.score, 2) if v and v.score is not None else 0,
                    "theme": f"t{i}",
                    "date": card.frontmatter.get("confirmed", ""),
                    "when": _when(card),
                    "area": [layer.layer],
                    "source": card.frontmatter.get("source")
                    or (v.source if v else None)
                    or label(lang, "rings.noSource"),
                    "halflife": halflife,
                    "store": [card.path],
                    "supports": (v.outcomes.get("held", 0) if v else 0),
                    "support_sessions": [],
                    "section": layer.layer,
                    "session": "",
                    "age_days": v.age_days if v else None,
                    "changed": None,
                    "refines": None,
                    "conflict": None,
                    "new": False,
                    **({"superseded_by": id_of_path.get(v.history or "", "")} if old and v else {}),
                }
            )
    core = [
        {
            "name": card.frontmatter.get("name") or Path(card.path).stem,
            "text": card.frontmatter.get("description") or "",
        }
        for layer in layers
        if layer.layer == "core"
        for card in layer.memories
    ]
    stats = {"levels": levels, "when": whens, "new": 0, "by_level_halflife": by_halflife}
    payload = {
        "kicker": label(lang, "rings.kicker", identity=identity, memories=sum(levels.values()), themes=len(themes)),
        "levelLabels": {key: label(lang, f"level.{key}") for key in LEVELS},
        "coreLabel": label(lang, "rings.core"),
        "coreFiles": label(lang, "rings.coreFiles", count=len(core)),
        "cards": cards,
        "themes": themes,
        "stats": stats,
        "halflife": HALFLIFE,
        "today": date.today().isoformat(),
        "core": core,
        "embed": embed,
    }
    html = TEMPLATE.read_text(encoding="utf-8")
    return html.replace("/*DATA*/null", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))


CACHE_SECONDS = 3600
_cache: dict[str, tuple[float, str]] = {}


def cached(key: str, build: Callable[[], str]) -> str:
    """The page built at most once an hour per identity, as the brain's; a new memory shows within the hour."""
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    html = build()
    _cache[key] = (time.monotonic(), html)
    return html
