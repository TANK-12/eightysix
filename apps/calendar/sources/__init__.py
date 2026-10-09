"""Feeders: each module here reads one place things happen and turns it into
calendar events. Adding a feeder is one new file; nothing else changes.

A feeder defines NAME, LABEL, DESCRIPTION, DEFAULT_ON, INTERVAL (seconds
between reads) and ``collect(state) -> list[event]``. ``state`` is the
feeder's own dict, saved between runs (read positions, what was running).
Every event should carry a ``key`` so that a re-read logs nothing twice.
A feeder that cannot run here (no Hyprland, no Jan) returns [].
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType


def load() -> dict[str, ModuleType]:
    found: dict[str, ModuleType] = {}
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        if hasattr(module, "collect") and hasattr(module, "NAME"):
            found[module.NAME] = module
    return dict(sorted(found.items()))
