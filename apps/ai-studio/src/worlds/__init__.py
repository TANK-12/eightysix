"""3D worlds: runners for world models and the sessions that play them.

Front door for app.py (docs/WORLDS.md has the full contract):

- ``runner_status(entry) -> (can_run, note)`` for a catalog entry of kind
  "world"; ``note`` is plain and can go straight on a card.
- ``start_session(entry, prompt=, image=, actions=, settings=)``,
  ``step_session(sid, actions)``, ``poll_session(sid, since)``,
  ``stop_session(sid)``, ``list_sessions()``, ``frame_path(sid, name)``,
  ``make_clip(sid)``. Each returns a plain dict (or a Path) and raises a
  ``WorldError`` subclass with a plain message and an HTTP ``status_code``.
- ``ACTION_LABELS``: move id -> button label.
- ``runtime_plan(runner_id)``: what a PyTorch runtime would install.
"""

import config  # pyright: ignore[reportMissingImports]

from .camera import ACTION_LABELS, ACTIONS
from .runners import RUNNERS, has_nvidia, runner_for, runtime_plan
from .session import (
    SessionManager,
    WorldBusy,
    WorldCannotRun,
    WorldError,
    WorldNotFound,
)

__all__ = [
    "ACTIONS",
    "ACTION_LABELS",
    "RUNNERS",
    "SessionManager",
    "WorldBusy",
    "WorldCannotRun",
    "WorldError",
    "WorldNotFound",
    "has_nvidia",
    "runner_for",
    "runner_status",
    "runtime_plan",
    "manager",
    "start_session",
    "step_session",
    "poll_session",
    "stop_session",
    "list_sessions",
    "frame_path",
    "make_clip",
]

NOTE_NO_RUNNER = "No way to run this world yet"

_manager = None


def manager():
    """The app's session manager; sessions live in outputs/worlds/."""
    global _manager
    if _manager is None:
        _manager = SessionManager(config.OUTPUTS_DIR / "worlds")
    return _manager


def runner_status(entry):
    runner = runner_for(entry)
    if runner is None:
        return False, NOTE_NO_RUNNER
    return runner.status(entry)


def start_session(entry, prompt="", image=None, actions=None, settings=None):
    runner = runner_for(entry)
    if runner is None:
        raise WorldCannotRun(NOTE_NO_RUNNER)
    return manager().start(
        runner, entry, prompt=prompt, image=image, actions=actions, settings=settings
    )


def step_session(sid, actions):
    return manager().step(sid, actions)


def poll_session(sid, since=0):
    return manager().poll(sid, since)


def stop_session(sid):
    return manager().stop(sid)


def list_sessions():
    return manager().list()


def frame_path(sid, name):
    return manager().frame_path(sid, name)


def make_clip(sid, fps=None):
    return manager().make_clip(sid, fps)
