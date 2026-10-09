"""Styles registry: one module per style, listed in STYLE_MODULES.

Each module defines `STYLE`, an instance of `base.Style`, with:
    name, label, description, enabled
    settings: dict                  schema the editor turns into controls
    preferred_transition: str|None  used by the auto transition rule
    render(ctx, shot, t) -> BGRA frame at ctx.out size

`render_shot(ctx, shot, t)` is the common entry point used by the renderer.
"""

import importlib

from .base import Style

STYLE_MODULES = (
    "scroll",
    "slideshow",
    "motion",
    "depth3d",
    "puppet25d",
    "inbetween",
    "model3d",
)


def _load() -> dict[str, Style]:
    reg: dict[str, Style] = {}
    for name in STYLE_MODULES:
        st = importlib.import_module(f"{__name__}.{name}").STYLE
        reg[st.name] = st
    return reg


REGISTRY = _load()


def enabled() -> list[str]:
    return [k for k, s in REGISTRY.items() if s.enabled]


def listing() -> list[dict]:
    return [s.describe() for s in REGISTRY.values()]


def style_for(ctx, shot) -> Style:
    name = shot.get("style") or ctx.settings.get("style") or "motion"
    st = REGISTRY.get(name)
    if st is None or not st.enabled:
        st = REGISTRY["motion"]
    return st


def render_shot(ctx, shot, t):
    return style_for(ctx, shot).render(ctx, shot, t)
