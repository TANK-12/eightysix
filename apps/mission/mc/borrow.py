"""Other Forge apps' readers, borrowed read-only instead of copied.

Mission Control shows what the Board, the Claude app, the Crew Room and Relay
already know, so it imports their modules rather than re-implementing them:

- Crew Room: sources/ (live sessions, helpers, crews, Jan), transcripts.py,
  conversation.py, where.py, art.py. Its folder goes on sys.path because
  those modules import each other by plain name.
- Relay: store.py, items.py, runs.py, for the same reason.
- Claude app: everyone.py (ended sessions, the "message a session" note).
- Board: web_app.py (post and answer notes, "go to it" for a terminal tab).

The last two are loaded by file under their own alias, so no app's
web_app.py can shadow another's. Other apps' folders are appended to
sys.path (never put first) so this app's own modules always win.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from types import ModuleType

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS = os.path.abspath(os.environ.get("MISSION_APPS_DIR") or os.path.dirname(ROOT))
SHARED = os.path.abspath(
    os.environ.get("FORGE_SHARED_DIR") or os.path.join(APPS, "..", "shared")
)
CREW_SKILL = os.path.abspath(
    os.environ.get("CREW_SKILL_DIR") or os.path.expanduser("~/.claude/skills/crew")
)

_loaded: dict[str, ModuleType] = {}


def app_dir(name: str) -> str:
    return os.path.join(APPS, name)


def setup() -> None:
    """Make the borrowed modules importable. Safe to call more than once."""
    for path in (SHARED, CREW_SKILL, app_dir("crewroom"), app_dir("relay")):
        if path not in sys.path:
            sys.path.append(path)


def by_file(alias: str, path: str) -> ModuleType:
    """Import one file as module `alias`, once."""
    if alias in _loaded:
        return _loaded[alias]
    setup()
    spec = importlib.util.spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    _loaded[alias] = module
    return module


def everyone() -> ModuleType:
    return by_file("claude_everyone", os.path.join(app_dir("claude"), "everyone.py"))


def board() -> ModuleType:
    return by_file("board_web_app", os.path.join(app_dir("board"), "web_app.py"))


def crew() -> ModuleType:
    setup()
    import crew as crew_module  # pyright: ignore[reportMissingImports]

    return crew_module
