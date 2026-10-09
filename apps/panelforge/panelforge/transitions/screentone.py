"""Screentone: the new shot grows in as halftone dots, like a manga tone sheet.

Dots sit on a 45-degree grid (the angle tone sheets are cut at) and swell
from nothing until they merge, sweeping along the reading direction so the
new panel is "printed" in the order it is read.
"""

import numpy as np

LABEL = "Screentone"
DEFAULT_DUR = 0.55
SETTINGS = {"dur": {"type": "number", "min": 0.2, "max": 1.5, "step": 0.05}}

CELLS = 48  # dots across the short side of the frame
SWEEP = 0.6  # how far behind the leading edge the trailing edge starts

_fields: dict = {}


def _field(h: int, w: int, direction) -> tuple[np.ndarray, np.ndarray]:
    """(distance to the nearest dot centre in cell units 0..~0.71, sweep 0..1)."""
    key = (h, w, direction)
    got = _fields.get(key)
    if got is None:
        if len(_fields) > 8:
            _fields.clear()
        cell = min(h, w) / CELLS
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        u = (xx + yy) / (cell * np.sqrt(2))
        v = (xx - yy) / (cell * np.sqrt(2))
        dist = np.hypot(u - np.round(u), v - np.round(v))
        dx, dy = direction
        # 0 where the new shot comes in from, 1 at the far side
        s = -(dx * (xx / max(1, w - 1) - 0.5) + dy * (yy / max(1, h - 1) - 0.5))
        s = (s - s.min()) / max(1e-6, float(s.max() - s.min()))
        got = _fields[key] = (dist, s.astype(np.float32))
    return got


def blend(a, b, u, info):
    if u <= 0:
        return a.copy()
    if u >= 1:
        return b.copy()
    h, w = a.shape[:2]
    dist, sweep = _field(h, w, tuple(info.direction))
    # each dot's radius runs 0 -> 0.72 (merged) over its own slice of time
    local = np.clip((u * (1 + SWEEP) - sweep * SWEEP), 0, 1)
    mask = dist < local * 0.72
    out = a.copy()
    out[mask] = b[mask]
    return out
