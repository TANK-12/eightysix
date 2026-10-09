"""Data sources for the Crew Room, discovered rather than listed.

A source is any module in this package that defines

    NAME = "key"          # the key its result lands under in /api/room
    def collect(ctx): ... # returns plain JSON-ready data

Adding a source is one new file here; nothing else changes. A source that
raises is reported under "errors" and the rest of the room still loads.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from context import Context


def discover() -> list[ModuleType]:
    modules = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        if hasattr(module, "NAME") and callable(getattr(module, "collect", None)):
            modules.append(module)
    return modules


def collect_all(ctx: Context) -> dict:
    room: dict = {"errors": {}}
    # Sources run by ORDER, lowest first. One that sets WANTS_ROOM also gets
    # the results gathered so far (helpers need the live sessions).
    for module in sorted(discover(), key=lambda m: getattr(m, "ORDER", 50)):
        try:
            if getattr(module, "WANTS_ROOM", False):
                room[module.NAME] = module.collect(ctx, room)
            else:
                room[module.NAME] = module.collect(ctx)
        except Exception as exc:  # one broken source must not blank the room
            room["errors"][module.NAME] = f"{type(exc).__name__}: {exc}"
    room["now"] = ctx.now
    return room
