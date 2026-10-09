"""Push: the new shot slides in along the reading direction, pushing the old one out."""

import numpy as np

from ..camera.keys import ease

LABEL = "Slide"
DEFAULT_DUR = 0.35
SETTINGS = {"dur": {"type": "number", "min": 0.1, "max": 1.5, "step": 0.05}}


def blend(a, b, u, info):
    h, w = a.shape[:2]
    e = ease(u, "inout")
    dx, dy = info.direction
    out = np.empty_like(a)
    if abs(dy) >= abs(dx):
        off = int(round(e * h))
        if dy > 0:  # new content comes from below, old moves up
            out[: h - off] = a[off:]
            out[h - off :] = b[: off or None][:off]
        else:
            out[off:] = a[: h - off]
            out[:off] = b[h - off :]
    else:
        off = int(round(e * w))
        if dx > 0:
            out[:, : w - off] = a[:, off:]
            out[:, w - off :] = b[:, :off]
        else:
            out[:, off:] = a[:, : w - off]
            out[:, :off] = b[:, w - off :]
    return out
