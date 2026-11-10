import json
import re
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel

from whaat.reports.types.journal import JournalBlockIn
from whaat.reports.types.session_report import SessionReportBodyIn

SKILL = Path(__file__).resolve().parents[3] / "connectors/claude_code/skills/journal/SKILL.md"


def example(section: str) -> Any:
    text = SKILL.read_text(encoding="utf-8").split(f"## {section}", 1)[1]
    block = re.search(r"```json\n(.*?)```", text, re.S)
    assert block is not None, f"no JSON example under {section}"
    return json.loads(block.group(1))


def model_of(annotation: Any) -> type[BaseModel] | None:
    for candidate in (annotation, *get_args(annotation)):
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate
        if get_origin(candidate) is list:
            inner = model_of(get_args(candidate)[0])
            if inner:
                return inner
    return None


def shape(model: type[BaseModel]) -> dict[str, Any]:
    return {
        name: shape(inner) if (inner := model_of(field.annotation)) else None
        for name, field in model.model_fields.items()
    }


def keys(value: Any) -> Any:
    if isinstance(value, list):
        return keys(value[0]) if value and isinstance(value[0], dict) else None
    if isinstance(value, dict):
        return {name: keys(item) for name, item in value.items()}
    return None


def test_the_entry_example_in_the_skill_has_exactly_the_schema_fields() -> None:
    assert keys(example("write-session-entry")) == shape(JournalBlockIn)


def test_the_report_example_in_the_skill_has_exactly_the_schema_fields() -> None:
    assert keys(example("write-session-report")) == shape(SessionReportBodyIn)
