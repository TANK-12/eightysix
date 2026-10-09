"""Flash cut: burn out to white and come back on the new shot, for a hit."""

import cv2
import numpy as np

LABEL = "Flash"
DEFAULT_DUR = 0.3
SETTINGS = {"dur": {"type": "number", "min": 0.1, "max": 1.0, "step": 0.05}}


def blend(a, b, u, info):
    white = np.full_like(a, 255)
    if u < 0.35:  # quick burn-out
        k = u / 0.35
        return cv2.addWeighted(a, 1.0 - k, white, k, 0.0)
    k = (u - 0.35) / 0.65  # slower return, so the new panel lands
    return cv2.addWeighted(white, 1.0 - k, b, k, 0.0)
