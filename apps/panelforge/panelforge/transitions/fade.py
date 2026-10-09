"""Cross-dissolve (fades from black when there is no outgoing shot)."""

import cv2

LABEL = "Fade"
DEFAULT_DUR = 0.5
SETTINGS = {"dur": {"type": "number", "min": 0.1, "max": 2.0, "step": 0.05}}


def blend(a, b, u, info):
    return cv2.addWeighted(a, 1.0 - u, b, u, 0.0)
