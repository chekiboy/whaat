"""Starting an identity's own agent from the terminal: when the identity has an agent config dir,
its session runs the start command with `CLAUDE_CONFIG_DIR` set to it and whaat's plugin, and whaat writes the
identity's kept token into that config's settings, so the agent works as the identity chosen.
The token goes into the file only: the start command is shown in the UI."""

import json
import logging
import os
import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from whaat.config import Settings

CONNECTOR = Path(__file__).resolve().parents[4] / "connectors" / "claude_code"
RULE_BEGIN = "<memory_handling>"
RULE_END = "</memory_handling>"
RECALL_RULE = f"""{RULE_BEGIN}
## Memory

Before every reply, recall your memories through the whaat:memory-recall skill: run `memory-recall index task="<what
the message asks for>"`. While an index you yourself read in full is still in your context, pass its digest as
`known=<digest>` and you get one line back; with none in your context, leave `known` out and read every part it gives.
Then open each memory whose trigger matches. No match is a valid result: say so. When whaat answers that no token is
set, this session has no identity: skip recall for it.
{RULE_END}
"""


class AgentTokenMissingError(RuntimeError):
    def __init__(self, identity: str) -> None:
        super().__init__(
            f"whaat keeps no token for {identity}: give it a new token in Settings, then start the session again"
        )


@dataclass(frozen=True)
class Launch:
    command: str
    env: dict[str, str] = field(default_factory=dict)


PLUGIN_DIRS = "CLAUDE_CODE_PLUGIN_DIRS"


def _read_settings(settings_file: Path) -> dict[str, Any]:
    data = _parsed(settings_file)
    return data if isinstance(data, dict) else {}


def _env_of(data: dict[str, Any]) -> dict[str, Any]:
    env = data.get("env")
    return env if isinstance(env, dict) else {}


def agent_env(token: str, settings: Settings) -> dict[str, str]:
    """What an agent needs to call this instance as its identity."""
    return {"WHAAT_TOKEN": token, "WHAAT_INSTANCE": settings.instance, "WHAAT_PORT": str(settings.port)}


PLUGIN_NAME = "whaat"


def _is_whaat_plugin(folder: str) -> bool:
    """A plugin folder whose manifest names it whaat: another checkout's connector, which would load beside this one."""
    try:
        manifest = json.loads(
            (Path(folder).expanduser() / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return False
    return isinstance(manifest, dict) and manifest.get("name") == PLUGIN_NAME


def with_connector(plugin_dirs: object) -> str:
    """Claude Code's plugin folders with this checkout's whaat connector in place of any other whaat connector, once;
    the other plugins stay, in their order."""
    dirs = [part.strip() for part in plugin_dirs.split(os.pathsep)] if isinstance(plugin_dirs, str) else []
    kept = [
        part for part in dirs if part and Path(part).expanduser().resolve() != CONNECTOR and not _is_whaat_plugin(part)
    ]
    return os.pathsep.join([*kept, str(CONNECTOR)])


class SettingsUnreadableError(RuntimeError):
    def __init__(self, settings_file: Path) -> None:
        super().__init__(f"{settings_file} is not a JSON object: fix it first, whaat leaves it as it is")


def check_writable(settings_file: Path) -> None:
    """A user's settings file that exists but does not read as a JSON object is never written over."""
    if settings_file.exists() and not isinstance(_parsed(settings_file), dict):
        raise SettingsUnreadableError(settings_file)


def _parsed(settings_file: Path) -> object:
    try:
        return json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def add_connector(settings_file: Path) -> None:
    """Load whaat's plugin in every session that reads this settings file; Claude Code takes the plugin folders from
    the user's settings only, not from a project's."""
    current = _env_of(_read_settings(settings_file)).get(PLUGIN_DIRS)
    write_agent_env(settings_file, {PLUGIN_DIRS: with_connector(current)})


class ClaudeMdUnusableError(RuntimeError):
    def __init__(self, claude_md: Path, why: str) -> None:
        super().__init__(f"{claude_md} {why}: fix it first, whaat leaves it as it is")


RULE_MARK = "whaat:memory-recall"


def check_claude_md(claude_md: Path) -> None:
    """A CLAUDE.md whaat could not read as text or write back is never touched."""
    target = claude_md.resolve()
    if target.exists():
        try:
            target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as err:
            raise ClaudeMdUnusableError(claude_md, "cannot be read as UTF-8 text") from err
        if not os.access(target, os.W_OK):
            raise ClaudeMdUnusableError(claude_md, "is not writable")
    if target.parent.exists() and not os.access(target.parent, os.W_OK):
        raise ClaudeMdUnusableError(claude_md, "cannot be written: its folder is not writable")


def add_recall_rule(claude_md: Path) -> None:
    """Puts whaat's recall rule at the top of this CLAUDE.md in place of an earlier one, so connecting again changes
    nothing else."""
    target = claude_md.resolve()
    old = target.read_text(encoding="utf-8") if target.exists() else ""
    text = old
    for block in re.findall(rf"{re.escape(RULE_BEGIN)}.*?{re.escape(RULE_END)}\n?", old, re.S):
        if RULE_MARK in block:
            text = text.replace(block, "", 1)
    rest = text.lstrip("\n")
    text = RECALL_RULE + ("\n" + rest if rest else "")
    if text == old:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    part.write_text(text, encoding="utf-8")
    if target.exists():
        os.chmod(part, target.stat().st_mode & 0o7777)
    os.replace(part, target)


def write_agent_env(settings_file: Path, values: dict[str, str]) -> None:
    """Set these keys in the config's settings.json `env` and keep the rest; written whole, owner-only."""
    data = _read_settings(settings_file)
    data["env"] = {**_env_of(data), **values}
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    part = settings_file.with_name(settings_file.name + ".part")
    descriptor = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(part, settings_file)


def launch_for(
    identity: str,
    config_dir: str | None,
    command: str,
    settings: Settings,
    stored_token: Callable[[str], str | None],
) -> Launch | None:
    """How a session of this identity starts; None when it has no agent config, so the plain start command runs."""
    if not config_dir:
        return None
    token = stored_token(identity)
    if not token:
        raise AgentTokenMissingError(identity)
    write_agent_env(Path(config_dir) / "settings.json", agent_env(token, settings))
    try:
        check_claude_md(Path(config_dir) / "CLAUDE.md")
        add_recall_rule(Path(config_dir) / "CLAUDE.md")
    except ClaudeMdUnusableError as err:
        logging.getLogger(__name__).warning("recall rule not written: %s", err)
    return Launch(
        command=f"{command} --plugin-dir {shlex.quote(str(CONNECTOR))}", env={"CLAUDE_CONFIG_DIR": config_dir}
    )
