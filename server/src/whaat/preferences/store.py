"""The preferences file: one JSON per instance, in its state folder, written whole and atomically."""

import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

FILE_NAME = "preferences.json"
OLD_PROJECTS = Path("terminal") / "projects.json"
MAX_PROJECTS = 30


class PreferencesStore:
    def __init__(
        self, state_dir: Path, default_command: str, default_theme: Callable[[], str | None] = lambda: None
    ) -> None:
        self.path = state_dir / FILE_NAME
        self.old_projects = state_dir / OLD_PROJECTS
        self.default_command = default_command
        self.default_theme = default_theme
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        terminal = data.setdefault("terminal", {})
        if not isinstance(terminal, dict):
            terminal = data["terminal"] = {}
        if "projects" not in terminal:  # once: the saved folders of the earlier terminal/projects.json
            try:
                old = json.loads(self.old_projects.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                old = []
            terminal["projects"] = [p for p in old if isinstance(p, dict) and isinstance(p.get("path"), str)]
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        part = self.path.with_suffix(".json.part")
        part.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(part, self.path)

    def load(self) -> dict[str, Any]:
        """The saved preferences with the defaults filled in."""
        with self._lock:
            data = self._read()
        terminal = data["terminal"]
        identity = data.get("identity") if isinstance(data.get("identity"), dict) else {}
        return {
            "language": data.get("language", "en"),
            "identity": {
                "open_with": identity.get("open_with", "last"),
                "last": identity.get("last"),
                "agents": dict(identity.get("agents") or {}),
            },
            "terminal": {
                "command": terminal.get("command") or self.default_command,
                "default_command": self.default_command,
                "theme": self._theme(terminal.get("theme")),
                "opener": terminal.get("opener", "browser"),
                "projects": terminal["projects"],
            },
        }

    def update(
        self,
        language: str | None = None,
        command: str | None = None,
        theme: str | None = None,
        opener: str | None = None,
        open_with: str | None = None,
        last_identity: str | None = None,
        agents: dict[str, str] | None = None,
    ) -> None:
        with self._lock:
            data = self._read()
            if language is not None:
                data["language"] = language
            if open_with is not None or last_identity is not None or agents is not None:
                identity = data.get("identity") if isinstance(data.get("identity"), dict) else {}
                if open_with is not None:
                    identity["open_with"] = open_with
                if last_identity is not None:
                    identity["last"] = last_identity
                for who, folder in (agents or {}).items():
                    kept = dict(identity.get("agents") or {})
                    if folder:
                        kept[who] = folder
                    else:
                        kept.pop(who, None)
                    identity["agents"] = kept
                data["identity"] = identity
            if command is not None:
                if command.strip():
                    data["terminal"]["command"] = command.strip()
                else:
                    data["terminal"].pop("command", None)
            if theme is not None:
                data["terminal"]["theme"] = theme
            if opener is not None:
                data["terminal"]["opener"] = opener
            self._write(data)

    def _theme(self, saved: str | None) -> str:
        """The saved theme when it is one of this machine's; otherwise the machine's own default, and whaat's colours
        only when the machine has none."""
        if saved and ":" in saved:
            return saved
        return self.default_theme() or "whaat"

    def agent_config(self, identity: str) -> str | None:
        """The identity's own agent config dir, when one is set."""
        return self.load()["identity"]["agents"].get(identity)

    def command(self) -> str:
        return str(self.load()["terminal"]["command"])

    def projects(self) -> list[dict[str, Any]]:
        return list(self.load()["terminal"]["projects"])

    def project_used(self, project: Path) -> None:
        """Put a project at the top of the saved folders, as the one used last."""
        with self._lock:
            data = self._read()
            rest = [p for p in data["terminal"]["projects"] if p["path"] != str(project)]
            data["terminal"]["projects"] = [{"path": str(project), "used": int(time.time())}, *rest][:MAX_PROJECTS]
            self._write(data)

    def forget_project(self, project: str) -> bool:
        with self._lock:
            data = self._read()
            projects = data["terminal"]["projects"]
            kept = [p for p in projects if p["path"] != project]
            if len(kept) == len(projects):
                return False
            data["terminal"]["projects"] = kept
            self._write(data)
            return True
