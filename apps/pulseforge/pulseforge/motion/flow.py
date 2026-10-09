"""Flow -- waterfalls, rivers, smoke, steam, drifting cloud banks."""

import numpy as np

from .. import imageops
from . import common

EFFECT = {
    "id": "flow",
    "label": "Flow",
    "family": "geometry",
    "description": "Slides the region's contents steadily in one direction. "
    "Two copies half a cycle apart are cross-faded so the scroll "
    "never visibly snaps back to the start. For waterfalls, "
    "rivers, smoke and steam.",
    "params": [
        common.strength(0.4, "Distance"),
        common.speed(0.35),
        common.direction(270),
        common.amount("wobble", 0.25, "Wobble", 1.0),
    ],
}


def apply(frame, mask, box, tl, p, ctx):
    y0, y1, x0, x1 = box
    bh, bw = y1 - y0, x1 - x0

    ux, uy = imageops.direction_vector(p["direction"])
    dist = float(p["strength"]) * 0.5 * max(bh, bw)
    period = common.period_from_speed(p["speed"], slowest=20.0, fastest=2.0)

    # The scroll has to restart somewhere. Rather than let that show, sample the
    # region twice -- half a cycle apart -- and cross-fade so whichever copy is
    # near its own restart is the one faded out.
    a = tl.saw(period)
    b = (a + 0.5) % 1.0
    wa = abs(1.0 - 2.0 * a)

    wob = float(p["wobble"])
    if wob > 0.001:
        gy, gx = imageops.grid(box)
        ripple = np.sin(2 * np.pi * (gx * 2.0 + gy * 1.3 + tl.phase(period * 1.7)))
        side = (wob * 0.03 * max(bh, bw) * ripple).astype(np.float32)
    else:
        side = np.float32(0.0)

    px, py = -uy * side, ux * side  # wobble across the direction of travel
    sa = imageops.sample(
        frame, -ux * dist * a + px, -uy * dist * a + py, box, fast=ctx.fast
    )
    sb = imageops.sample(
        frame, -ux * dist * b + px, -uy * dist * b + py, box, fast=ctx.fast
    )
    return imageops.composite(frame, sa * wa + sb * (1.0 - wa), mask, box)
