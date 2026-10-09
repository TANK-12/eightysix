"""Box helpers. A box is always [x, y, w, h] in integer pixels."""

from __future__ import annotations

import math
from typing import Sequence

Box = list[int]


def clip(box: Sequence[float], width: int, height: int) -> Box:
    x0 = max(0, min(width, int(round(box[0]))))
    y0 = max(0, min(height, int(round(box[1]))))
    x1 = max(x0, min(width, int(round(box[0] + box[2]))))
    y1 = max(y0, min(height, int(round(box[1] + box[3]))))
    return [x0, y0, x1 - x0, y1 - y0]


def center(box: Sequence[float]) -> tuple[float, float]:
    return box[0] + box[2] / 2, box[1] + box[3] / 2


def area(box: Sequence[float]) -> float:
    return max(0.0, box[2]) * max(0.0, box[3])


def intersection(a: Sequence[float], b: Sequence[float]) -> float:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    inter = intersection(a, b)
    union = area(a) + area(b) - inter
    return inter / union if union > 0 else 0.0


def contains_point(box: Sequence[float], x: float, y: float) -> bool:
    return box[0] <= x <= box[0] + box[2] and box[1] <= y <= box[1] + box[3]


def inside(inner: Sequence[float], outer: Sequence[float], slack: float = 0) -> bool:
    return (
        inner[0] >= outer[0] - slack
        and inner[1] >= outer[1] - slack
        and inner[0] + inner[2] <= outer[0] + outer[2] + slack
        and inner[1] + inner[3] <= outer[1] + outer[3] + slack
    )


def expand(box: Sequence[float], left: float, top: float, right: float, bottom: float):
    """Grow a box by fractions of its own width/height on each side."""
    x, y, w, h = box
    return [x - w * left, y - h * top, w * (1 + left + right), h * (1 + top + bottom)]


def nms(boxes: list[Sequence[float]], scores: list[float], thresh: float) -> list[int]:
    """Indices kept by greedy non-maximum suppression, best first."""
    order = sorted(range(len(boxes)), key=lambda i: -scores[i])
    keep: list[int] = []
    for i in order:
        if all(iou(boxes[i], boxes[k]) < thresh for k in keep):
            keep.append(i)
    return keep


def angle_deg(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dy, dx))


def angle_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Unsigned angle between two vectors, degrees, 0..180."""
    na = math.hypot(*a)
    nb = math.hypot(*b)
    if na == 0 or nb == 0:
        return 180.0
    cos = (a[0] * b[0] + a[1] * b[1]) / (na * nb)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))
