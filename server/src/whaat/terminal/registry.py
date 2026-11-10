"""What the terminal started, kept on disk:
each session's name, tmux id and tmux server, so after the server or tmux stops whaat still knows what it started and
which of them are gone."""

import json
import os
import threading
from pathlib import Path
from typing import Any


class SessionRegistry:
    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "terminal" / "sessions.json"
        self._lock = threading.Lock()

    def load(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return (
            [e for e in data if isinstance(e, dict) and isinstance(e.get("name"), str)]
            if isinstance(data, list)
            else []
        )

    def _save(self, entries: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        part = self.path.with_suffix(".json.part")
        part.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(part, self.path)

    def put(self, entry: dict[str, Any]) -> None:
        """Add a session, or replace the one with its name."""
        with self._lock:
            self._save([*(e for e in self.load() if e["name"] != entry["name"]), entry])

    def update(self, name: str, **fields: Any) -> None:
        with self._lock:
            self._save([{**e, **fields} if e["name"] == name else e for e in self.load()])

    def drop(self, name: str) -> bool:
        with self._lock:
            entries = self.load()
            kept = [e for e in entries if e["name"] != name]
            if len(kept) == len(entries):
                return False
            self._save(kept)
            return True
