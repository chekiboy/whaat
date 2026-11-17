"""whaat over MCP: the calls the connector's skills make, each one API call with this identity's token.

Only what a skill uses is here; a tool takes what its API route takes. The session is the client's when it names one
(Claude Code passes CLAUDE_CODE_SESSION_ID to its MCP servers), else this process's own; recall, outcome, journal and
migration-plan calls are logged under it.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from whaat.config import Settings
from whaat.journal.schemas import CurationApplied
from whaat.memory.schemas import MigrationSource
from whaat.platform.repo_key import repo_key
from whaat.reports.types.journal import JournalBlockIn
from whaat.reports.types.memory_curation import CurationReportBodyIn
from whaat.reports.types.session_report import SessionReportBodyIn

IDENTITY_FIRST = """Before your first reply in every conversation, call identity_load and read what it returns: it is
this identity's personal core in full (who it is, how it works with the user). Call it again after a compaction or
when the core changed. Below is only its outline."""

INSTRUCTIONS = """whaat keeps this identity's memory, journal and reports in every client and session; a client's own
memory feature does not reach it, so save here what the identity should keep.
Recall: before each reply call memory_index (what the message asks for, in a sentence; the repo's path or key; known=
the digest of the last index you still see, none without one), then memory_open each memory whose trigger matches,
saying in `because` which words match. memory_dump reads a whole dir, only to curate, review or save; memory_where
only names the dirs.
Save: when the work taught something that should outlive the session, above all a user's correction or decision, use
memory_save (format in its description) and fix what its warnings name.
Before reporting a task done: memory_reads lists what this session opened; memory_record whether each recall held,
misled or was irrelevant (leave personal: ones out).
Journal and session report: journal_save and journal_save_report when the user ends the session or asks; report_open
then shows the report.
memory_delete, memory_revert, memory_import and memory_move_personal change the memory in commits: only when the user
asked for that.
Curation, only when the user asks to tidy the memory: memory_lint; per dir memory_curation_brief for a judging agent,
then memory_curation_refute_brief with its rows for a second agent; skip what journal_discarded lists as discarded
unless changed since; journal_save_curation saves the rows, report_open shows them for the user's decisions. Applying
them: memory_save or memory_delete, memory_fidelity before committing a merge, split or trim, journal_save_applied,
and memory_lint again.
Bringing memory in, only when the user asks: memory_migration_plan keeps the sources as a plan the user chooses from on
its page, then memory_import with that plan."""
INSTRUCTIONS_BUDGET = 3900

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True)

Session = Annotated[
    str | None, Field(pattern=r"^[0-9a-f]{8}$", description="The session's first 8 characters; this one when left out.")
]
Tags = Annotated[list[str], Field(description="Topics of the session.")]
EntryDate = Annotated[date | None, Field(description="The file's day; today when left out.")]
Purpose = Literal["recall", "save", "curate", "review"]
DumpPurpose = Literal["curate", "review", "save"]


Send = Callable[[str, str, bytes | None, dict[str, str]], tuple[int, bytes]]


def http_send(method: str, url: str, data: bytes | None, headers: dict[str, str]) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()
    except urllib.error.URLError as err:
        raise ToolError(f"whaat does not answer on {url}: {err.reason}") from err


class Api:
    """The whaat API as this identity: JSON in, JSON out; a refusal becomes a ToolError with the server's words."""

    def __init__(self, settings: Settings, token: str, send: Send = http_send) -> None:
        self._base = f"http://{settings.host}:{settings.port}/api/v1"
        self._token = token
        self._send = send

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        status, raw = self._send(
            method,
            self._base + path,
            None if body is None else json.dumps(body, default=str).encode("utf-8"),
            {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
        )
        if status < 400:
            return json.loads(raw)
        text = raw.decode("utf-8", "replace")
        try:
            detail = json.loads(text)["detail"]
        except (ValueError, KeyError, TypeError):
            detail = text
        raise ToolError(detail if isinstance(detail, str) else f"whaat refused it ({status}): {text}")


def _key_of(path: str | None) -> str | None:
    found = repo_key(Path(path).expanduser().resolve()) if path else None
    return "/".join(found) if found else None


CORE_PARTS = 50


def start_body(session: str, part: int, parts: int, **more: object) -> dict[str, object]:
    """A personal-level session-start call, as the hook sends it; the CLI path is only for its open lines."""
    return {"level": "personal", "part": part, "parts": parts, "session": session, "source": "mcp", "cli": "", **more}


def load_core(api: Api, session: str) -> str:
    """The identity's personal core as the session-start hook puts it in, every part, each file logged as a load."""
    texts = []
    for part in range(1, CORE_PARTS + 1):
        text = api.call("POST", "/memory/recall/start", start_body(session, part, CORE_PARTS))["text"]
        if not text:
            break
        texts.append(text)
    return "\n".join(texts)


def instructions(api: Api, session: str) -> str:
    """What the client gets at connect: the call to load the core first and the core's outline, then how to use the
    tools, under the size some clients cut instructions at; the core itself comes through identity_load."""
    try:
        body = start_body(session, 1, 1, outline=True)
        outline = api.call("POST", "/memory/recall/start", body)["text"] or "(this identity keeps no personal core yet)"
    except ToolError as err:
        outline = f"(the outline could not be read at connect: {err})"
    room = INSTRUCTIONS_BUDGET - len(IDENTITY_FIRST) - len(INSTRUCTIONS) - 4
    if len(outline) > room:
        outline = outline[: max(room - 40, 0)].rsplit("\n", 1)[0] + "\n- … (the rest in identity_load)"
    return f"{IDENTITY_FIRST}\n{outline}\n\n{INSTRUCTIONS}"


def build(settings: Settings, token: str, environ: Mapping[str, str] = os.environ, send: Send = http_send) -> MCPServer:
    """The MCP server; the session and the project dir come from the client's env when it gives them."""
    api = Api(settings, token, send)
    this = environ.get("CLAUDE_CODE_SESSION_ID", "")[:8] or uuid.uuid4().hex[:8]
    project_dir = environ.get("CLAUDE_PROJECT_DIR") or None
    mcp = MCPServer(name="whaat", instructions=instructions(api, this))

    def text(answer: dict[str, Any]) -> str:
        return answer.get("text") or ""

    @mcp.tool(annotations=READ_ONLY)
    def identity_load() -> str:
        """This identity's personal core in full: who it is and how it works with the user. Call it before your first
        reply in every conversation, again after a compaction or when the core changed; each file is logged as a
        load."""
        return load_core(api, this) or "This identity keeps no personal core (personal/core/ is empty)."

    @mcp.tool(annotations=READ_ONLY)
    def memory_index(
        task: Annotated[str, Field(description="What you are doing, in a sentence.")],
        path: Annotated[
            str | None, Field(description="A directory of the repo the work is on; the client's project by default.")
        ] = None,
        repo: Annotated[str | None, Field(description="Or the repo's key: <group> or <group>/<repo>.")] = None,
        known: Annotated[
            str | None,
            Field(description="The digest of the last index you still see in your context; leave it out with none."),
        ] = None,
    ) -> Any:
        """The memory indexes that apply: global, the repo's project and repo layer, and personal; each line a memory
        and its trigger, the situation in which to open it. Outside a git repo only global and personal come back: name
        the repo with repo= to see its layers. Personal memories are listed as personal:<file>. An answer with
        sections null means the index with that digest is unchanged: open from the copy in your context."""
        path = path or (None if repo else project_dir)
        key = None if repo else _key_of(path)
        return api.call(
            "POST",
            "/memory/recall/index",
            {
                "session": this,
                "task": task,
                "cwd": path or "",
                "repo": repo,
                "key": key.split("/") if key else None,
                "known": known,
            },
        )

    @mcp.tool(annotations=READ_ONLY)
    def memory_open(
        file: Annotated[str, Field(description="A memory path, as memory_index printed it.")],
        because: Annotated[str, Field(description="Which words of its trigger match which part of the task.")],
        purpose: Annotated[Purpose, Field(description="recall, or why else it is read.")] = "recall",
    ) -> str:
        """One memory, each time it is asked for: as a recall, with how far it can be trusted (truthness, validity);
        with another purpose, the file as it is. Logged under its purpose."""
        opened = api.call(
            "POST", "/memory/recall/open", {"session": this, "file": file, "because": because, "purpose": purpose}
        )
        if opened["text"] is not None:
            return str(opened["text"])
        framed = api.call(
            "POST",
            "/memory/recall/frame",
            {
                "session": this,
                "opened": [{"file": opened["file"], "path": opened["path"]}],
                "force": True,
                "uncapped": True,
            },
        )
        return framed["context"] or ""

    @mcp.tool(annotations=READ_ONLY)
    def memory_dump(
        dir: Annotated[str, Field(description="A memory dir below the memory root; personal: for the personal one.")],
        purpose: Annotated[DumpPurpose, Field(description="Why the whole dir is read.")],
        because: Annotated[str, Field(description="Why.")],
    ) -> Any:
        """Every memory of one dir in one call, to curate, review or save; not a recall (use memory_open for that)."""
        return api.call(
            "POST", "/memory/recall/dump", {"session": this, "dir": dir, "because": because, "purpose": purpose}
        )

    @mcp.tool(annotations=READ_ONLY)
    def memory_where(
        path: Annotated[
            str | None, Field(description="A directory of a repo; the client's project by default.")
        ] = None,
    ) -> Any:
        """Where this identity's memory lives on disk: root, personal and state dirs, and a repo's project and repo
        dirs; it lists no memories (memory_index does)."""
        key = _key_of(path or project_dir)
        return api.call("GET", "/memory/where" + (f"?key={urllib.parse.quote(key)}" if key else ""))

    @mcp.tool(annotations=WRITES)
    def memory_save(
        path: Annotated[
            str,
            Field(
                description="<dir>/<name>.md below the memory root: dir is empty for every repo, <project>/<repo> for"
                " one (memory_where names it), personal for the user and working together."
            ),
        ],
        content: Annotated[str, Field(description="The whole file, frontmatter included, written as given.")],
        trigger: Annotated[str, Field(description="The index line's text after the name: when to open it.")],
        unindex: Annotated[list[str], Field(description="Memories this one supersedes.")] = [],  # noqa: B006
    ) -> Any:
        """Write a memory and its index line exactly as given, and commit it; the warnings name what memory-lint finds
        in it. <name> is <type>_<slug>, type feedback (how to work), project (a fact about a codebase or domain) or
        reference (a recipe or pointer). The content starts with frontmatter: name (the file name without .md),
        description, type, and optionally source (measured, user-decision or inference) and confirmed (YYYY-MM-DD, the
        day the fact was checked: set it when you re-verify it or fix what it says, since an edit alone does not reset
        its age); then the rule or fact in 1-3 sentences, a **Why:** line and a **How to apply:** line. Write
        ~ for the home dir, absolute dates, and link related memories as [[<name>]]. These names use underscores, not
        the client's own memory naming. A personal memory is saved as personal/<file> and listed as personal:<file>."""
        return api.call(
            "POST", "/memory/memories", {"path": path, "content": content, "trigger": trigger, "unindex": unindex}
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    def memory_delete(
        path: Annotated[str, Field(description="The memory's path below the memory root.")],
    ) -> Any:
        """Remove a memory that was simply wrong, and its index line, in one commit."""
        return api.call("DELETE", "/memory/memories/" + urllib.parse.quote(path))

    @mcp.tool(annotations=READ_ONLY)
    def memory_reads(
        session_id: Annotated[str | None, Field(description="Another session's first 8 characters.")] = None,
    ) -> str:
        """What a session (this one when left out) read or opened through recall."""
        return text(api.call("POST", "/memory/outcome/reads", {"session": session_id or this}))

    @mcp.tool(annotations=WRITES)
    def memory_record(
        outcome: Literal["held", "misled", "irrelevant"],
        paths: Annotated[list[str], Field(description="Memory paths, as memory_reads printed them.")],
    ) -> str:
        """Before reporting a task done, record whether the memories it recalled held up: held (relied on and right,
        rescored at once), misled (wrong or stale: fix or supersede it now with memory_save) or irrelevant (its trigger
        fired for a task it does not fit). Personal memories are not scored: leave them out."""
        return text(api.call("POST", "/memory/outcome/record", {"session": this, "outcome": outcome, "paths": paths}))

    @mcp.tool(annotations=DESTRUCTIVE)
    def memory_revert(
        commits: Annotated[list[str], Field(min_length=1, description="The memory commits to undo.")],
    ) -> Any:
        """Undo commits of this identity's memory in one run that a conflict aborts whole."""
        return api.call("POST", "/memory/revert", {"commits": commits})

    @mcp.tool(annotations=DESTRUCTIVE)
    def memory_import(
        plan: Annotated[str | None, Field(description="A plan's id: import the groups the user chose for it.")] = None,
        sources: Annotated[list[MigrationSource] | None, Field(description="Without a plan: the sources.")] = None,
        groups: Annotated[list[str], Field(description="Without a plan: the group ids to bring in.")] = [],  # noqa: B006
        state: Annotated[str | None, Field(description="Without a plan: the source's state dir.")] = None,
    ) -> Any:
        """Import memory groups, one commit each; reports what came, what was skipped and what is in conflict."""
        if plan:
            return api.call("POST", f"/memory/migration/plans/{urllib.parse.quote(plan)}/import", {})
        if not sources:
            raise ToolError("memory_import needs a plan, or sources and groups")
        body = {"sources": [s.model_dump() for s in sources], "groups": groups, "state": state}
        return api.call("POST", "/memory/migration/import", body)

    @mcp.tool(annotations=WRITES)
    def memory_migration_plan(
        sources: Annotated[list[MigrationSource], Field(min_length=1, description="The sources found.")],
        state: Annotated[str | None, Field(description="The source's state dir.")] = None,
    ) -> Any:
        """Keep the sources as a plan for the user to choose from on this identity's page; imports nothing."""
        body = {"sources": [s.model_dump() for s in sources], "state": state, "session": this}
        return api.call("POST", "/memory/migration/plans", body)

    @mcp.tool(annotations=DESTRUCTIVE)
    def memory_move_personal() -> Any:
        """Move the personal memory still at the memory root into personal/, in one commit."""
        return api.call("POST", "/memory/migration/move-personal", {})

    @mcp.tool(annotations=READ_ONLY)
    def memory_lint(
        dup_threshold: Annotated[float, Field(description="Word overlap that marks a duplicate.")] = 0.4,
    ) -> str:
        """Mechanical checks over this identity's memory (names, links, index, validity); reads only. Run it after
        changing several memories, or when the user asks to check or curate them."""
        return text(api.call("POST", "/memory/lint", {"dup_threshold": dup_threshold}))

    @mcp.tool(annotations=READ_ONLY)
    def memory_curation_brief(
        dir: Annotated[str, Field(description='The memory dir to judge; "." is the global one.')],
    ) -> str:
        """A step of a memory curation run, when the user asked for one: the judge brief for one dir, for a judging
        agent, passed on as it is."""
        return text(api.call("POST", "/memory/curation-brief", {"dir": dir, "dump": "mcp"}))

    @mcp.tool(annotations=READ_ONLY)
    def memory_curation_refute_brief(
        dir: Annotated[str, Field(description="The memory dir the rows are from.")],
        rows: Annotated[list[dict[str, Any]], Field(description="The judge's rows for that dir, as returned.")],
    ) -> str:
        """A step of a memory curation run: the refuter brief for one dir and the judge's rows, for a second agent
        that tries to refute them, passed on as it is."""
        return text(api.call("POST", "/memory/curation-refute-brief", {"dir": dir, "rows": rows, "dump": "mcp"}))

    @mcp.tool(annotations=READ_ONLY)
    def memory_fidelity(
        file: Annotated[str, Field(description="The memory as it was, below the memory root.")],
        new: Annotated[list[str], Field(min_length=1, description="The memories its text now lives in.")],
        rev: Annotated[str, Field(description="The commit holding it as it was.")] = "HEAD",
    ) -> str:
        """After a merge, split or trim: every old sentence and whether the new text keeps it word for word."""
        return text(api.call("POST", "/memory/fidelity", {"file": file, "new": new, "rev": rev}))

    @mcp.tool(annotations=WRITES)
    def journal_save(
        block: JournalBlockIn,
        session: Session = None,
        tags: Tags = [],  # noqa: B006
        entry_date: EntryDate = None,
    ) -> Any:
        """Add a block to the session's journal entry, when the user ends the session or asks for it."""
        body = {
            "session": session or this,
            "entry_date": entry_date,
            "tags": tags,
            "block": block.model_dump(mode="json"),
        }
        return api.call("POST", "/journal/entries", body)

    @mcp.tool(annotations=WRITES)
    def journal_save_report(
        slug: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$", description="A few words of the topic.")],
        report: SessionReportBodyIn,
        session: Session = None,
        tags: Tags = [],  # noqa: B006
        entry_date: EntryDate = None,
    ) -> Any:
        """Save the session report, replacing the session's earlier one, when the user ends the session or asks for
        it."""
        body = {
            "session": session or this,
            "slug": slug,
            "entry_date": entry_date,
            "tags": tags,
            "report": report.model_dump(mode="json"),
        }
        return api.call("POST", "/journal/session-reports", body)

    @mcp.tool(annotations=WRITES)
    def journal_save_curation(report: CurationReportBodyIn, entry_date: EntryDate = None) -> Any:
        """Save memory-curation's report, replacing that day's report."""
        return api.call(
            "POST", "/journal/curation-reports", {"entry_date": entry_date, "report": report.model_dump(mode="json")}
        )

    @mcp.tool(annotations=WRITES)
    def journal_save_applied(
        report_id: Annotated[str, Field(description="The curation report's id.")], rows: list[CurationApplied]
    ) -> Any:
        """Write the Applied cells of a curation report's rows: commits only on a row the user decided as apply on the
        report page (others are refused); null empties one."""
        body = {"report_id": report_id, "rows": [r.model_dump() for r in rows]}
        return api.call("POST", "/journal/curation-reports/applied", body)

    @mcp.tool(annotations=READ_ONLY)
    def journal_discarded() -> Any:
        """The proposals the user discarded in this identity's curation reports, and whether each file changed since."""
        return api.call("GET", "/curation/discarded")

    @mcp.tool(annotations=WRITES)
    def report_open(
        report_id: Annotated[str, Field(description="The report's id, as a save returned it.")],
    ) -> Any:
        """Open a report in the UI on this machine; returns its address."""
        return api.call("POST", f"/reports/{urllib.parse.quote(report_id, safe=':/')}/open", {})

    return mcp
