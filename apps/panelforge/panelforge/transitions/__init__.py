"""Transitions registry: one module per transition, listed in TRANSITION_MODULES.

Each module defines:
    LABEL: str               shown in the editor
    DEFAULT_DUR: float       seconds (0 for a cut)
    SETTINGS: dict           settings schema for the UI
    blend(a, b, u, info) -> frame
        a = outgoing frame, b = incoming frame (BGRA uint8, same size),
        u = progress 0..1, info = TransitionInfo.

`choose_auto` picks a transition from scene facts (see its docstring).
"""

import importlib
from dataclasses import dataclass

TRANSITION_MODULES = (
    "cut",
    "fade",
    "slide",
    "whip",
    "zoom_through",
    "match",
    "morph",
    "screentone",
    "flash",
)


@dataclass
class TransitionInfo:
    direction: tuple[float, float] = (0.0, -1.0)  # where the new shot comes from
    fps: int = 30


def _load() -> dict:
    reg = {}
    for name in TRANSITION_MODULES:
        mod = importlib.import_module(f"{__name__}.{name}")
        reg[name.replace("_", "-")] = mod
    return reg


REGISTRY = _load()


def listing() -> list[dict]:
    return [
        {
            "kind": k,
            "label": m.LABEL,
            "default_dur": m.DEFAULT_DUR,
            "settings": m.SETTINGS,
        }
        for k, m in REGISTRY.items()
    ]


def reading_direction(reading: str) -> tuple[float, float]:
    """Unit vector the new shot slides in from: follows the reading order."""
    return {"ttb": (0.0, 1.0), "ltr": (1.0, 0.0), "rtl": (-1.0, 0.0)}.get(
        reading, (0.0, 1.0)
    )


def _shared_cast(prev, cur) -> set:
    ids = lambda p: {  # noqa: E731
        getattr(c, "cast_id", None)
        or (c.get("cast_id") if isinstance(c, dict) else None)
        for c in (getattr(p, "characters", None) or [])
    } - {None}
    return ids(prev) & ids(cur)


def choose_auto(prev, cur, reading: str = "ttb", style_pref: str | None = None):
    """Pick (kind, dur) for the cut into `cur` (camera.PanelInfo) from `prev`.

    Rules, first match wins:
      1. first shot: fade in
      2. style asks for a fixed transition (slideshow: fade; inbetween: morph,
         but never between panels that keep lettering)
      3. location or scene change: fade
      4. same character framed the same way: match cut
      5. action panel: whip
      6. splash panel: zoom-through
      7. same scene: slide along the reading direction for strips, else cut
    """
    if prev is None:
        return "fade", 0.5
    if style_pref == "morph":
        # An in-between only makes sense between two drawings of the same
        # subject: the panels must share a character. Between unrelated
        # drawings the flow is a liquid smear, and between panels with kept
        # lettering the words turn to mush (both seen on chapter 1). Such
        # cuts get the ordinary choice.
        shared = _shared_cast(prev, cur)
        if (
            not shared
            or getattr(prev, "has_text", False)
            or getattr(cur, "has_text", False)
        ):
            style_pref = None
    if style_pref:
        return style_pref, REGISTRY[style_pref].DEFAULT_DUR
    if (prev.scene_id or cur.scene_id) and (
        prev.scene_id != cur.scene_id
        or (prev.location and cur.location and prev.location != cur.location)
    ):
        return "fade", 0.6
    if _same_framing(prev, cur):
        return "match", REGISTRY["match"].DEFAULT_DUR
    if cur.action >= 0.6 or cur.mood == "action":
        return "whip", REGISTRY["whip"].DEFAULT_DUR
    if cur.kind == "splash":
        return "zoom-through", REGISTRY["zoom-through"].DEFAULT_DUR
    if reading == "ttb":
        return "slide", REGISTRY["slide"].DEFAULT_DUR
    return "cut", 0.0


def _same_framing(prev, cur) -> bool:
    """One main character, same cast id, face at a similar size in both panels."""
    if len(prev.characters) != 1 or len(cur.characters) != 1:
        return False
    a, b = prev.characters[0], cur.characters[0]
    if not a.cast_id or a.cast_id != b.cast_id or not a.face or not b.face:
        return False
    ra = a.face[2] / max(1, prev.w)
    rb = b.face[2] / max(1, cur.w)
    return 0.7 < ra / max(rb, 1e-6) < 1.43


def blend(kind: str, a, b, u: float, info: TransitionInfo | None = None):
    mod = REGISTRY.get(kind) or REGISTRY["cut"]
    return mod.blend(a, b, min(1.0, max(0.0, u)), info or TransitionInfo())
