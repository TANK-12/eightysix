"""Your own frames -- hand-drawn animation played inside a region."""

from .. import artsource
from . import common

EFFECT = {
    "id": "frames",
    "label": "My own frames",
    "family": "custom",
    "description": "Plays your own animation inside the region: a folder of "
    "numbered PNGs, an animated GIF, or one image holding a row "
    "of frames. Transparency is respected, and the playback rate "
    "is nudged so the animation loops with the shot.",
    "params": [
        {
            "key": "source",
            "label": "Folder, GIF or sprite strip",
            "type": "path",
            "default": "",
            "help": "A folder of numbered PNGs, an animated GIF/WebP, or one "
            "wide image plus a frame count below.",
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
            "label": "Frames per second",
            "type": "range",
            "default": 12,
            "min": 1,
            "max": 60,
            "step": 1,
        },
        {
            "key": "fit",
            "label": "Fit",
            "type": "select",
            "default": "cover",
            "options": ["cover", "contain", "stretch", "none"],
        },
        {
            "key": "scale",
            "label": "Scale",
            "type": "range",
            "default": 1.0,
            "min": 0.05,
            "max": 4.0,
            "step": 0.01,
        },
        {
            "key": "offset_x",
            "label": "Nudge across",
            "type": "range",
            "default": 0.0,
            "min": -1.0,
            "max": 1.0,
            "step": 0.01,
        },
        {
            "key": "offset_y",
            "label": "Nudge down",
            "type": "range",
            "default": 0.0,
            "min": -1.0,
            "max": 1.0,
            "step": 0.01,
        },
        common.amount("opacity", 1.0, "Opacity", 1.0),
        {
            "key": "blend",
            "label": "Blend",
            "type": "select",
            "default": "over",
            "options": ["over", "screen", "add"],
        },
    ],
}


def apply(frame, mask, box, tl, p, ctx):
    seq = artsource.load_sequence(p["source"], int(p["strip_columns"] or 0))
    if not seq:
        return frame

    y0, y1, x0, x1 = box
    bh, bw = y1 - y0, x1 - x0
    sprite = seq[artsource.frame_index(tl, len(seq), p["fps"])]
    fit = str(p["fit"])
    if fit != "none":
        sprite = artsource.fit_into(sprite, bh, bw, fit, float(p["scale"]))

    sh, sw = sprite.shape[:2]
    x = x0 + (bw - sw) * 0.5 + float(p["offset_x"]) * bw
    y = y0 + (bh - sh) * 0.5 + float(p["offset_y"]) * bh
    return artsource.blit(
        frame,
        sprite,
        x,
        y,
        opacity=float(p["opacity"]),
        mask=mask,
        mode=str(p["blend"]),
    )
