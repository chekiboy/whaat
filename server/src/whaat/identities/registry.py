import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from whaat.config import IDENTITY_ID, Settings, instance_identity_folder, same_identity
from whaat.git import GitCommitError, GitCommitter
from whaat.reports.service import PRIVATE_MARKER
from whaat.reports.store import Root, roots_from

TOKENS_DIR_NAME = "tokens"
# the token itself, kept so whaat can later write it into the identity's own agent config
SECRETS_DIR_NAME = "identity-secrets"
NEVER_SHARED_DIRS = ("journal", "session-reports", "memory/personal", "distilled")
STATE_DIR_NAME = "state"


class IdentityExistsError(Exception):
    def __init__(self, identity: str, existing: str | None = None) -> None:
        if existing and existing != identity:
            super().__init__(f"identity {identity!r} already exists as {existing!r}; ids must differ in more than case")
        else:
            super().__init__(f"identity {identity!r} already has a token")


class UnknownTokenError(LookupError):
    def __init__(self, identity: str) -> None:
        super().__init__(f"identity {identity!r} has no token to regenerate")


class InvalidIdentityError(ValueError):
    def __init__(self, identity: str) -> None:
        super().__init__(f"identity id {identity!r} must match {IDENTITY_ID.pattern}")


@dataclass(frozen=True)
class Principal:
    """Who calls: the admin (identity None), who sees everything, or one identity, who sees only its own folder."""

    identity: str | None

    @property
    def admin(self) -> bool:
        return self.identity is None


ADMIN = Principal(None)


def _write_private(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)  # the mode of os.open holds only for a new file
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(text)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class IdentityRegistry:
    """The identities this server knows, read from disk on every call, so one added while it runs is known at once."""

    def __init__(self, settings: Settings, admin_token: str, committer: GitCommitter) -> None:
        self._settings = settings
        self._admin_token = admin_token
        self._committer = committer

    @property
    def _tokens_dir(self) -> Path:
        return self._settings.state_dir / TOKENS_DIR_NAME

    @property
    def _secrets_dir(self) -> Path:
        return self._settings.state_dir / SECRETS_DIR_NAME

    def stored_token(self, identity: str) -> str | None:
        """The token of an identity added since tokens are kept; None for an earlier one, whose token only its holder
        has."""
        try:
            return (self._secrets_dir / identity).read_text(encoding="utf-8").strip()
        except OSError:
            return None

    def folder_of(self, identity: str) -> Path:
        return self._settings.identities.get(identity) or instance_identity_folder(self._settings.state_dir, identity)

    def folders(self) -> dict[str, Path]:
        """Configured folders, and every identity that has a token, in its own folder."""
        with_token = sorted(path.name for path in self._tokens_dir.glob("*") if IDENTITY_ID.match(path.name))
        return {**{identity: self.folder_of(identity) for identity in with_token}, **self._settings.identities}

    def has_token(self, identity: str) -> bool:
        return (self._tokens_dir / identity).is_file()

    def roots_for(self, principal: Principal) -> list[Root]:
        roots = roots_from(self._settings, self.folders())
        return roots if principal.admin else [root for root in roots if root.identity == principal.identity]

    def principal_for(self, token: str) -> Principal | None:
        if secrets.compare_digest(token, self._admin_token):
            return ADMIN
        digest = _digest(token)
        for path in self._tokens_dir.glob("*"):
            if IDENTITY_ID.match(path.name) and secrets.compare_digest(
                path.read_text(encoding="utf-8").strip(), digest
            ):
                return Principal(path.name)
        return None

    def add(self, identity: str) -> tuple[str, list[str]]:
        """Give an identity its token and, unless it has one, a folder under git whose never-shared parts are marked.

        The token decides who reads the folder; the marker says what is never to be shared, even once sharing comes.
        """
        if not IDENTITY_ID.match(identity):
            raise InvalidIdentityError(identity)
        known = {*self.folders(), self._settings.default_identity}
        clash = next((other for other in known if other != identity and same_identity(other, identity)), None)
        if clash:
            raise IdentityExistsError(identity, clash)
        token_path = self._tokens_dir / identity
        if token_path.exists():
            raise IdentityExistsError(identity)
        folder = self.folder_of(identity)
        warnings = [] if folder.exists() else self._create_folder(folder, identity)
        return self._issue_token(identity), warnings

    def regenerate(self, identity: str) -> str:
        """Replace an identity's token: the old one stops working at once, and the new one is kept as the old was."""
        # by the names on disk: on a case-insensitive file system tokens/Claude "exists" when tokens/claude does
        on_disk = {path.name for path in self._tokens_dir.glob("*")}
        if identity not in on_disk:
            raise UnknownTokenError(identity)
        return self._issue_token(identity)

    def _issue_token(self, identity: str) -> str:
        self._tokens_dir.mkdir(parents=True, exist_ok=True)
        self._tokens_dir.chmod(0o700)
        token = secrets.token_urlsafe(32)
        _write_private(self._tokens_dir / identity, _digest(token))
        self._secrets_dir.mkdir(parents=True, exist_ok=True)
        self._secrets_dir.chmod(0o700)
        _write_private(self._secrets_dir / identity, token)
        return token

    def _create_folder(self, folder: Path, identity: str) -> list[str]:
        markers = [folder / name / PRIVATE_MARKER for name in NEVER_SHARED_DIRS]
        for marker in markers:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
        ignore = folder / ".gitignore"
        ignore.write_text(f"{STATE_DIR_NAME}/\n", encoding="utf-8")
        self._committer.init(folder)
        try:
            self._committer.commit(folder, [ignore, *markers], f"identity: {identity} created")
        except GitCommitError as err:
            return [f"created but not committed: {err}"]
        return []
