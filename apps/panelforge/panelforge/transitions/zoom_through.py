"""Zoom-through: fly into the old shot, arrive pulled back on the new one."""

import cv2

from ..camera.keys import ease

LABEL = "Zoom through"
DEFAULT_DUR = 0.45
SETTINGS = {"dur": {"type": "number", "min": 0.2, "max": 1.5, "step": 0.05}}


def _scaled(img, s):
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), 0, s)
    return cv2.warpAffine(
        img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
    )


def blend(a, b, u, info):
    e = ease(u, "in" if u < 0.5 else "out")
    if u < 0.5:
        return _scaled(a, 1.0 + 2.0 * e)
    x = _scaled(b, 0.7 + 0.3 * e)
    return cv2.addWeighted(
        x, min(1.0, (u - 0.5) * 4), _scaled(a, 3.0), max(0.0, 1 - (u - 0.5) * 4), 0
    )
