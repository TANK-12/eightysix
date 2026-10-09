"""Whip pan: a fast motion-blurred slide, for action."""

import cv2
import numpy as np

from ..camera.keys import ease

LABEL = "Whip pan"
DEFAULT_DUR = 0.28
SETTINGS = {"dur": {"type": "number", "min": 0.1, "max": 0.8, "step": 0.02}}


def blend(a, b, u, info):
    h, w = a.shape[:2]
    e = ease(u, "inout")
    off = int(round(e * w))
    out = np.empty_like(a)
    out[:, : w - off] = a[:, off:]
    out[:, w - off :] = b[:, :off]
    k = int(w * 0.18 * np.sin(np.pi * u)) | 1
    if k > 3:
        small = cv2.resize(out, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
        small = cv2.blur(small, (max(3, k // 4) | 1, 1))
        out = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    return out
