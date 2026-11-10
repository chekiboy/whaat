import time

from fastapi import FastAPI
from fastapi.routing import APIRoute

from whaat import __version__
from whaat.config import Settings
from whaat.curation.router import router as curation_router
from whaat.git import GitCommitter
from whaat.health.router import code_commit
from whaat.health.router import router as health_router
from whaat.identities.registry import IdentityRegistry
from whaat.identities.router import router as identities_router
from whaat.journal.router import router as journal_router
from whaat.journal.service import JournalService
from whaat.journal.store import FileJournalStore
from whaat.memory.router import router as memory_router
from whaat.memory.service import MemoryService
from whaat.preferences.router import router as preferences_router
from whaat.preferences.store import PreferencesStore
from whaat.reports.router import router as reports_router
from whaat.restart import schedule_restart, schedule_stop
from whaat.terminal.agent import launch_for
from whaat.terminal.native import open_in
from whaat.terminal.registry import SessionRegistry
from whaat.terminal.router import router as terminal_router
from whaat.terminal.service import Terminals
from whaat.terminal.themes import default_theme_id
from whaat.terminal.tmux import Tmux
from whaat.ui.router import router as ui_router
from whaat.ui_build import build_ui


def _operation_id(route: APIRoute) -> str:
    return route.name


def create_app(settings: Settings, token: str) -> FastAPI:
    app = FastAPI(
        title="Whaat?!",
        summary="Not just an agent. An agent with a past.",
        version=__version__,
        generate_unique_id_function=_operation_id,
    )
    code_commit()
    app.state.settings = settings
    app.state.token = token
    app.state.started = int(time.time())
    app.state.restart = schedule_restart
    app.state.stop = schedule_stop
    app.state.curation_runs = {}
    app.state.build_ui = lambda: build_ui(settings.ui_dir)
    registry = IdentityRegistry(settings, token, GitCommitter())
    app.state.registry = registry
    app.state.journal_service = JournalService(FileJournalStore(), registry.roots_for, GitCommitter())
    app.state.memory_service = MemoryService(registry, GitCommitter())
    app.state.preferences = PreferencesStore(settings.state_dir, settings.terminal_command, default_theme_id)
    app.state.tmux = Tmux(settings, app.state.preferences.command)
    app.state.native_open = open_in
    preferences = app.state.preferences
    app.state.terminals = Terminals(
        app.state.tmux,
        SessionRegistry(settings.state_dir),
        lambda persona: launch_for(
            persona, preferences.agent_config(persona), preferences.command(), settings, registry.stored_token
        ),
    )
    app.include_router(health_router)
    app.include_router(reports_router)
    app.include_router(identities_router)
    app.include_router(journal_router)
    app.include_router(memory_router)
    app.include_router(curation_router)
    app.include_router(terminal_router)
    app.include_router(preferences_router)
    app.include_router(ui_router)
    return app
