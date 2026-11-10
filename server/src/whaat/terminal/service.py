"""The terminal sessions as whaat knows them: what tmux runs now, joined with what whaat recorded when it started them.
A recorded session tmux no longer has (tmux stopped, the machine restarted) is listed as gone until it is forgotten; a
whaat session tmux runs but the record lacks (one started before the record existed) is taken into the record."""

import shlex
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from whaat.terminal.agent import Launch
from whaat.terminal.registry import SessionRegistry
from whaat.terminal.tmux import MAX_LABEL, Session, SessionNotFoundError, Tmux, prompt_line


def _entry(session: Session, tmux_server: str) -> dict[str, Any]:
    return {
        "name": session.name,
        "tmux_id": session.tmux_id,
        "tmux_server": tmux_server,
        "persona": session.persona,
        "number": session.number,
        "cwd": session.cwd,
        "command": session.command,
        "label": session.label,
        "created": session.created,
    }


def _gone(entry: dict[str, Any]) -> Session:
    return Session(
        name=entry["name"],
        persona=entry.get("persona", ""),
        number=int(entry.get("number", 0)),
        created=int(entry.get("created", 0)),
        attached=0,
        cwd=entry.get("cwd", ""),
        command=entry.get("command", ""),
        label=entry.get("label", ""),
        tmux_id=entry.get("tmux_id", ""),
        gone=True,
    )


class Terminals:
    def __init__(
        self, tmux: Tmux, registry: SessionRegistry, launch: Callable[[str], Launch | None] = lambda persona: None
    ) -> None:
        self.tmux = tmux
        self.registry = registry
        self.launch = launch

    def sessions(self, persona: str | None = None) -> list[Session]:
        live = {s.name: s for s in self.tmux.sessions()}
        recorded = {e["name"]: e for e in self.registry.load()}
        found: list[Session] = []
        for name, entry in recorded.items():
            session = live.get(name)
            if session and (not entry.get("tmux_id") or entry["tmux_id"] == session.tmux_id):
                found.append(replace(session, label=entry.get("label") or session.label))
            else:
                found.append(_gone(entry))
        for name, session in live.items():
            if name not in recorded:
                self.registry.put(_entry(session, self.tmux.label))
                found.append(session)
        return sorted((s for s in found if not persona or s.persona == persona), key=lambda s: (s.persona, s.number))

    def create(
        self, persona: str, cwd: Path | None = None, prompt: str | None = None, label: str | None = None
    ) -> Session:
        """A new session; `prompt` is handed to the start command as its first message, `label` names the session."""
        number = max((s.number for s in self.sessions(persona)), default=0) + 1
        launch = self.launch(persona)
        command = launch.command if launch else None
        if prompt:
            command = f"{command or self.tmux.command} {shlex.quote(prompt)}"
        session = self.tmux.create(persona, cwd, number, command=command, env=launch.env if launch else None)
        self.registry.put(_entry(session, self.tmux.label))
        return self.rename(session.name, label) if label else session

    def type_into(self, name: str, text: str) -> None:
        """Type text into a running session's claude prompt and submit it; TypingError when nothing was sent."""
        current = next((s for s in self.sessions() if s.name == name and not s.gone), None)
        if current is None:
            raise SessionNotFoundError(name)
        self.tmux.type_into(name, text)

    def busy(self, name: str) -> bool:
        return self.tmux.busy(name)

    def asking(self, name: str) -> bool:
        return self.tmux.asking(name)

    def state(self, name: str) -> tuple[bool, bool, bool]:
        return self.tmux.state(name)

    def runs_program(self, name: str) -> bool:
        return self.tmux.runs_program(name)

    def screen(self, name: str, history: int = 0) -> str:
        return self.tmux.screen(name, history=history)

    def prompt(self, name: str) -> tuple[str | None, bool]:
        return prompt_line(self.tmux.screen(name, escapes=True))

    def rename(self, name: str, label: str) -> Session:
        current = next((s for s in self.sessions() if s.name == name), None)
        if current is None:
            raise SessionNotFoundError(name)
        clean = " ".join(label.split())[:MAX_LABEL]
        if not current.gone:
            self.tmux.rename(name, clean)
        self.registry.update(name, label=clean)
        return replace(current, label=clean)

    def stop(self, name: str) -> None:
        """Stop a running session and forget it; a gone one is only forgotten."""
        current = next((s for s in self.sessions() if s.name == name), None)
        if current is None:
            raise SessionNotFoundError(name)
        if not current.gone:
            self.tmux.kill(name)
        self.registry.drop(name)
