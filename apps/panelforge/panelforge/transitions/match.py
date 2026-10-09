"""Match cut: a very short dissolve. The timeline builder lines the incoming
camera up so the character's face sits where it was in the outgoing shot."""

import cv2

LABEL = "Match cut"
DEFAULT_DUR = 0.18
SETTINGS = {"dur": {"type": "number", "min": 0.0, "max": 0.6, "step": 0.02}}


def blend(a, b, u, info):
    return cv2.addWeighted(a, 1.0 - u, b, u, 0.0)
