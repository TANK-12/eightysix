"""A command queue so something outside the page (the Claude panel) can use the browser.

The pages live in forge.py's WebKit views and are driven by the Browser app's
own page, so only that page can act on them. A caller POSTs a command to the
backend and waits; the page long-polls for the next command, carries it out,
and posts the result back, which wakes the caller.

    caller --submit--> Queue <--next-- page
    caller <--result-- Queue <--resolve-- page
"""

from __future__ import annotations

import itertools
import threading
from collections import deque

OPS = {"open", "read", "tabs", "back", "forward", "reload", "search", "switch", "close"}


class Queue:
    def __init__(self) -> None:
        self._pending: deque[dict] = deque()
        self._waiting: dict[str, dict] = {}
        self._ids = itertools.count(1)
        self._cond = threading.Condition()

    def submit(self, command: dict, timeout: float = 20.0) -> dict:
        """Hand a command to the page and wait for its result."""
        if command.get("op") not in OPS:
            return {"ok": False, "error": f"unknown op {command.get('op')!r}"}
        cid = str(next(self._ids))
        slot = {"done": threading.Event(), "result": None}
        with self._cond:
            self._waiting[cid] = slot
            self._pending.append(dict(command, cid=cid))
            self._cond.notify_all()
        if not slot["done"].wait(timeout):
            with self._cond:
                self._waiting.pop(cid, None)
                self._pending = deque(c for c in self._pending if c["cid"] != cid)
            return {
                "ok": False,
                "error": "The browser did not answer. Is Forge open with the Browser app loaded?",
            }
        return slot["result"]

    def next(self, timeout: float = 25.0) -> dict | None:
        """The next command for the page, waiting up to `timeout` seconds."""
        with self._cond:
            if not self._pending:
                self._cond.wait(timeout)
            return self._pending.popleft() if self._pending else None

    def resolve(self, cid: str, result: dict) -> bool:
        with self._cond:
            slot = self._waiting.pop(str(cid), None)
        if slot is None:
            return False
        slot["result"] = result if isinstance(result, dict) else {"ok": False}
        slot["done"].set()
        return True
