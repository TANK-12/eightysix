"""A fixed-size, thread-safe buffer of recent readings for the page's graph."""

from __future__ import annotations

import threading
from collections import deque


class History:
    def __init__(self, max_points: int = 120) -> None:
        self._points: deque[dict] = deque(maxlen=max_points)
        self._lock = threading.Lock()

    def add(self, point: dict) -> None:
        with self._lock:
            self._points.append(point)

    def points(self) -> list[dict]:
        with self._lock:
            return list(self._points)
