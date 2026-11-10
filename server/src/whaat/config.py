import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from whaat.platform.paths import state_dir

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 1111
LIVE_INSTANCE = "live"
OTHER_INSTANCE_PORT = 1112
HOSTNAME_SUFFIX = "whaat.localhost"
DEFAULT_IDENTITY = "wHaat"
# the older name of WHAAT_LIVE_IDENTITIES: CLAUDE_PRIVATE_ARCHIVE is this identity's folder on the live instance
ARCHIVE_IDENTITY = "claude"
DEFAULT_TERMINAL_COMMAND = "claude"
# where memory-lint looks for local clones to check stale paths against; none unless MEMORY_REPO_ROOTS names them
DEFAULT_MEMORY_REPO_ROOTS = ""
# the older names of WHAAT_SHARED_REPORTS: each names one shared root, whose report dirs are fixed
LEGACY_SHARED_ROOTS = {
    "artifacts": ("CLAUDE_ARTIFACTS_ROOT", ("reviews", "investigations")),
    "fw-state": ("CLAUDE_FW_STATE_DIR", ("memory-curation",)),
}
SHARED_ROOT_KEY = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
# a report's id starts with its root's key, and an identity's own root is private-<identity>
RESERVED_ROOT_PREFIX = "private-"
SHARED_REPORTS_SHAPE = (
    'WHAAT_SHARED_REPORTS must be a JSON object of root key → {"path": folder, "dirs": [report dirs below it]}'
)
# an identity's id may hold capitals (wHaat); two ids that differ only in case are refused, since the id is a folder
# and file name on a case-insensitive file system
IDENTITY_ID = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,31}$")
INSTANCE_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
REPO_UI_DIR = Path(__file__).resolve().parents[3] / "ui" / "dist"


class IdentityConfigError(ValueError):
    pass


class SharedReportsConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    shared_roots: dict[str, Path]
    identities: dict[str, Path]
    state_dir: Path
    shared_report_dirs: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {key: dirs for key, (_, dirs) in LEGACY_SHARED_ROOTS.items()}
    )
    default_identity: str = DEFAULT_IDENTITY
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    instance: str = LIVE_INSTANCE
    hostname: str = HOSTNAME_SUFFIX
    ui_dir: Path | None = None
    browser: str | None = None
    agent_token: str | None = None
    terminal_command: str = DEFAULT_TERMINAL_COMMAND
    terminal_cwd: Path | None = None
    memory_repo_roots: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        validate_identities(self.identities)
        if not INSTANCE_ID.match(self.instance):
            raise ValueError(f"instance name {self.instance!r} must match {INSTANCE_ID.pattern}")

    @property
    def public_url(self) -> str:
        """The address a browser uses; the CLI itself always connects to `host`."""
        return f"http://{self.hostname}:{self.port}"


def same_identity(identity: str, other: str) -> bool:
    return identity.casefold() == other.casefold()


def validate_identities(identities: dict[str, Path]) -> None:
    for identity in identities:
        if not IDENTITY_ID.match(identity):
            raise IdentityConfigError(f"identity id {identity!r} must match {IDENTITY_ID.pattern}")
    for identity in identities:
        for other in identities:
            if identity < other and same_identity(identity, other):
                raise IdentityConfigError(f"the identities {identity!r} and {other!r} differ only in case")
    resolved = {identity: root.expanduser().resolve() for identity, root in identities.items()}
    for identity, root in resolved.items():
        for other, other_root in resolved.items():
            if identity < other and (root.is_relative_to(other_root) or other_root.is_relative_to(root)):
                raise IdentityConfigError(
                    f"the private folders of {identity!r} and {other!r} overlap: {root}, {other_root}"
                )


def _settings_env(path: Path) -> dict[str, str]:
    try:
        env = json.loads(path.read_text(encoding="utf-8")).get("env", {})
    except (OSError, ValueError):
        return {}
    return {key: str(value) for key, value in env.items()} if isinstance(env, dict) else {}


def _identities(raw: str | None) -> dict[str, Path]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError as err:
        raise IdentityConfigError("WHAAT_IDENTITIES must be a JSON object of identity id → private folder") from err
    if not isinstance(parsed, dict) or not all(isinstance(value, str) for value in parsed.values()):
        raise IdentityConfigError("WHAAT_IDENTITIES must be a JSON object of identity id → private folder")
    return {str(identity): Path(folder).expanduser() for identity, folder in parsed.items()}


def _live_identities(raw: str | None) -> dict[str, Path]:
    if not raw:
        return {}
    try:
        return _identities(raw)
    except IdentityConfigError as err:
        raise IdentityConfigError(str(err).replace("WHAAT_IDENTITIES", "WHAAT_LIVE_IDENTITIES")) from err


def _shared_reports(raw: str | None) -> dict[str, tuple[Path, tuple[str, ...]]]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError as err:
        raise SharedReportsConfigError(SHARED_REPORTS_SHAPE) from err
    if not isinstance(parsed, dict):
        raise SharedReportsConfigError(SHARED_REPORTS_SHAPE)
    roots = {}
    for key, root in parsed.items():
        if not SHARED_ROOT_KEY.match(key) or key.startswith(RESERVED_ROOT_PREFIX):
            raise SharedReportsConfigError(
                f"shared root key {key!r} must match {SHARED_ROOT_KEY.pattern}"
                f" and not start with {RESERVED_ROOT_PREFIX}"
            )
        dirs = root.get("dirs") if isinstance(root, dict) else None
        if (
            not isinstance(root, dict)
            or not isinstance(root.get("path"), str)
            or not isinstance(dirs, list)
            or not all(isinstance(name, str) for name in dirs)
        ):
            raise SharedReportsConfigError(SHARED_REPORTS_SHAPE)
        roots[key] = (Path(root["path"]).expanduser(), tuple(dirs))
    return roots


def claude_settings_file() -> Path:
    """The settings.json of the Claude Code config that runs us, so a separate CLAUDE_CONFIG_DIR stays separate."""
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(config_dir).expanduser() if config_dir else Path.home() / ".claude") / "settings.json"


def instance_identity_folder(instance_state_dir: Path, identity: str) -> Path:
    """Where an instance other than live keeps an identity's data, so it never writes into the live archive."""
    return instance_state_dir / "identities" / identity


def load_settings(settings_file: Path | None = None) -> Settings:
    settings_env = _settings_env(settings_file or claude_settings_file())

    def lookup(name: str) -> str | None:
        return os.environ.get(name) or settings_env.get(name)

    default_identity = lookup("WHAAT_DEFAULT_IDENTITY") or DEFAULT_IDENTITY
    identities = _identities(lookup("WHAAT_IDENTITIES"))
    instance = lookup("WHAAT_INSTANCE") or LIVE_INSTANCE
    live = instance == LIVE_INSTANCE
    custom_state_dir = lookup("WHAAT_STATE_DIR")
    instance_state_dir = (
        Path(custom_state_dir).expanduser() if custom_state_dir else state_dir("" if live else f"-{instance}")
    )
    if live:
        live_identities = _live_identities(lookup("WHAAT_LIVE_IDENTITIES"))
        if not live_identities and (archive := lookup("CLAUDE_PRIVATE_ARCHIVE")):
            live_identities = {ARCHIVE_IDENTITY: Path(archive).expanduser()}
        identities = {**live_identities, **identities}
    shared = _shared_reports(lookup("WHAAT_SHARED_REPORTS")) or {
        key: (Path(value).expanduser(), dirs)
        for key, (name, dirs) in LEGACY_SHARED_ROOTS.items()
        if (value := lookup(name))
    }
    if not any(same_identity(default_identity, identity) for identity in identities):
        identities[default_identity] = instance_identity_folder(instance_state_dir, default_identity)
    custom_ui_dir = lookup("WHAAT_UI_DIR")
    return Settings(
        shared_roots={key: path for key, (path, _) in shared.items()},
        shared_report_dirs={key: dirs for key, (_, dirs) in shared.items()},
        identities=identities,
        state_dir=instance_state_dir,
        default_identity=default_identity,
        host=lookup("WHAAT_HOST") or DEFAULT_HOST,
        port=int(lookup("WHAAT_PORT") or (DEFAULT_PORT if live else OTHER_INSTANCE_PORT)),
        instance=instance,
        hostname=lookup("WHAAT_HOSTNAME") or (HOSTNAME_SUFFIX if live else f"{instance}.{HOSTNAME_SUFFIX}"),
        ui_dir=Path(custom_ui_dir).expanduser() if custom_ui_dir else REPO_UI_DIR,
        browser=lookup("WHAAT_BROWSER") or lookup("CLAUDE_REPORT_BROWSER"),
        agent_token=lookup("WHAAT_TOKEN"),
        terminal_command=lookup("WHAAT_TERMINAL_COMMAND") or DEFAULT_TERMINAL_COMMAND,
        terminal_cwd=Path(cwd).expanduser() if (cwd := lookup("WHAAT_TERMINAL_CWD")) else None,
        memory_repo_roots=tuple(
            Path(root).expanduser()
            for root in (lookup("MEMORY_REPO_ROOTS") or DEFAULT_MEMORY_REPO_ROOTS).split(":")
            if root
        ),
    )
