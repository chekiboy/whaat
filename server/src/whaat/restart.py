"""Restarting and stopping the server from its own UI. A restart replaces the process with a fresh `whaat serve`, so it
loads the code on disk and keeps its environment, port and parent (a terminal, the launcher or the app). A stop sends
the process SIGTERM, so uvicorn shuts down as it does on Ctrl-C. tmux sessions live in their own server and keep
running through both."""

import os
import signal
import sys
import threading
from collections.abc import Callable

RESTART_DELAY_SECONDS = 0.5


def reexec() -> None:
    os.execv(sys.executable, [sys.executable, "-m", "whaat", "serve"])


def terminate() -> None:
    os.kill(os.getpid(), signal.SIGTERM)


def _later(action: Callable[[], None], delay: float) -> None:
    """Run the action a moment later, so the request that asked for it gets its answer first."""
    timer = threading.Timer(delay, action)
    timer.daemon = True
    timer.start()


def schedule_restart(delay: float = RESTART_DELAY_SECONDS) -> None:
    _later(reexec, delay)


def schedule_stop(delay: float = RESTART_DELAY_SECONDS) -> None:
    _later(terminate, delay)
