"""A small blocking client for Firefox's built-in remote protocol (WebDriver BiDi).

Firefox started with `--remote-debugging-port N` accepts one BiDi session at
ws://127.0.0.1:N/session. Everything here acts on the visible window the user
is looking at: tabs it opens appear on screen, clicks happen on the real page.

Every call opens a session, does its work and ends it, so a crashed caller
never leaves Firefox holding a session no one can reuse.

Never call browser.createUserContext on a real profile: Firefox saves each one
as a public container named webdriver-<uuid> in containers.json.

Needs the `websockets` package in the caller's venv.
"""

from __future__ import annotations

import json
import socket
from typing import Any

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect


class BidiError(Exception):
    """Firefox is not reachable or refused a command; the text says why."""


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


class Session:
    """`with Session(9222) as s: s.call("browsingContext.getTree", {})`"""

    def __init__(self, port: int, timeout: float = 30.0):
        self.port = port
        self.timeout = timeout
        self._ws: Any = None
        self._next = 0

    def __enter__(self) -> "Session":
        try:
            self._ws = connect(
                f"ws://127.0.0.1:{self.port}/session",
                max_size=None,
                open_timeout=5,
            ).__enter__()
        except (OSError, WebSocketException) as exc:
            raise BidiError(
                f"Firefox is not listening for remote control on port {self.port}"
            ) from exc
        try:
            self.call("session.new", {"capabilities": {}})
        except BidiError:
            self._ws.close()
            raise
        return self

    def __exit__(self, *_exc) -> None:
        try:
            self.call("session.end", {})
        except (BidiError, OSError, WebSocketException):
            pass
        self._ws.close()

    def call(self, method: str, params: dict) -> dict:
        self._next += 1
        mid = self._next
        self._ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            try:
                reply = json.loads(self._ws.recv(timeout=self.timeout))
            except TimeoutError as exc:
                raise BidiError(f"Firefox did not answer {method} in time") from exc
            except WebSocketException as exc:
                raise BidiError(f"The connection to Firefox closed ({exc})") from exc
            if reply.get("id") != mid:
                continue  # an event or a late reply
            if reply.get("type") == "error":
                raise BidiError(
                    f"{method}: {reply.get('error')}: {reply.get('message')}"
                )
            return reply.get("result", {})

    # --- helpers ------------------------------------------------------------

    def evaluate(self, context: str, expression: str) -> Any:
        """Run JavaScript in a tab and return its value, passed through JSON.

        `expression` may be async; its result is awaited."""
        wrapped = f"(async () => JSON.stringify(await ({expression})))()"
        result = self.call(
            "script.evaluate",
            {
                "expression": wrapped,
                "target": {"context": context},
                "awaitPromise": True,
                "userActivation": True,
            },
        )
        if result.get("type") == "exception":
            details = result.get("exceptionDetails", {})
            raise BidiError(f"The page's script failed: {details.get('text')}")
        value = result.get("result", {}).get("value")
        return None if value is None else json.loads(value)

    def tabs(self) -> list[dict]:
        """Top-level tabs with url, title, container and whether it is shown."""
        tree = self.call("browsingContext.getTree", {"maxDepth": 0})
        rows = []
        for ctx in tree.get("contexts", []):
            row = {
                "context": ctx["context"],
                "url": ctx.get("url", ""),
                "user_context": ctx.get("userContext", "default"),
                "title": "",
                "visible": False,
                "focused": False,
            }
            try:
                info = self.evaluate(
                    ctx["context"],
                    "({t: document.title, v: document.visibilityState === 'visible',"
                    " f: document.hasFocus()})",
                )
                row.update(title=info["t"], visible=info["v"], focused=info["f"])
            except BidiError:
                pass  # about: pages and some privileged pages refuse scripts
            rows.append(row)
        return rows

    def user_contexts(self) -> list[str]:
        """'default' first, then one id per public container in containers.json order."""
        result = self.call("browser.getUserContexts", {})
        return [u["userContext"] for u in result.get("userContexts", [])]

    def open_tab(self, url: str, user_context: str | None = None) -> str:
        params: dict = {"type": "tab"}
        if user_context:
            params["userContext"] = user_context
        context = self.call("browsingContext.create", params)["context"]
        self.call("browsingContext.activate", {"context": context})
        self.call(
            "browsingContext.navigate",
            {"context": context, "url": url, "wait": "interactive"},
        )
        return context
