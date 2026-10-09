"""Your own sprites -- your PNGs or a ForgeArtData pixel pack, drifting."""

import numpy as np

from .. import artsource, overlay
from . import common

EMITTER = {
    "id": "sprites",
    "label": "My own sprites",
    "family": "custom",
    "description": "Sends your own artwork across the frame instead of a "
    "built-in shape: a folder of PNGs, an animated GIF, a sprite "
    "strip, or a pixel pack from ForgeArtData. Each copy gets its "
    "own size, speed and starting point.",
    "params": [
        {
            "key": "source",
            "label": "Folder, GIF or sprite strip",
            "type": "path",
            "default": "",
            "help": "Leave empty to use the project's attached pixel pack.",
        },
        {
            "key": "strip_columns",
            "label": "Frames across (sprite strips only)",
            "type": "int",
            "default": 0,
            "min": 0,
            "max": 64,
            "step": 1,
        },
        {
            "key": "fps",
            "label": "Animation frames per second",
            "type": "range",
            "default": 8,
            "min": 1,
            "max": 60,
            "step": 1,
        },
        common.count(12, 200),
        common.speed(0.25),
        common.direction(0),
        common.size(0.4),
        common.amount("size_variation", 0.4, "Size variation", 1.0),
        common.amount("bob", 0.4, "Bob", 1.0),
        common.amount("opacity", 1.0, "Opacity", 1.0),
        common.amount("band", 0.8, "Spread", 1.0),
    ],
}


def _pack_frames(ctx):
    """Fall back to the project's ForgeArtData pack when no path is given."""
    pack = getattr(ctx, "art_pack", None)
    if not pack:
        return []
    out = []
    palette = pack.get("palette") or {}
    for sprite in (pack.get("sprites") or [])[:12]:
        rows = sprite.get("rows") or sprite.get("pixels")
        if rows:
            out.append(overlay.rasterize_sprite(rows, palette, scale=1))
    return out


def draw(frame, tl, p, ctx, mask=None, offset=(0.0, 0.0)):
    seq = artsource.load_sequence(p["source"], int(p["strip_columns"] or 0))
    if not seq:
        seq = _pack_frames(ctx)
    if not seq:
        return frame

    h, w = frame.shape[:2]
    n = int(p["count"])
    period = common.period_from_speed(p["speed"], slowest=80.0, fastest=10.0)
    x, y, prog, tr = common.crossing_path(
        tl, n, tl.seed + 1117, period, p["direction"], spread=float(p["band"])
    )
    y = y + tl.waves(period * 0.19, tr["extra"] * 3.0) * float(p["bob"]) * 0.04

    idx = artsource.frame_index(tl, len(seq), p["fps"])
    sprite = seq[idx] if len(seq) > 1 else seq[0]
    sh, sw = sprite.shape[:2]
    target = float(p["size"]) * 0.25 * min(h, w)
    var = float(p["size_variation"])
    px = x * w + offset[0]
    py = y * h + offset[1]
    for k in range(n):
        f = (target / max(1, sh)) * (1.0 - var * 0.5 + var * float(tr["size"][k]))
        sp = artsource.fit_into(
            sprite, max(2, int(sh * f)), max(2, int(sw * f)), "stretch"
        )
        artsource.blit(
            frame,
            sp,
            px[k] - sp.shape[1] / 2,
            py[k] - sp.shape[0] / 2,
            opacity=float(p["opacity"]),
            mask=mask,
        )
    return frame
