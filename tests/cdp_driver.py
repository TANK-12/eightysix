"""Drive a real page in headless Chrome (Flatpak) over the DevTools protocol.

For app checks that need clicks and keys, not just a screenshot or a DOM dump:

    from cdp_driver import chrome_page, serve

    with serve(app_dir, env) as port:
        async with chrome_page(sandbox_dir) as page:
            await page.go(f"http://127.0.0.1:{port}/")
            await page.wait("document.querySelector('.item')")
            await page.key("c", "KeyC", CTRL, 67)

Needs only `websockets` in the calling app's venv (most Forge venvs have it).
Used by apps/files/tests/check_ui.py and apps/terminal/tests/check_ui.py.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import signal
import socket
import subprocess
import time
import urllib.request
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import AsyncGenerator, Generator

import websockets

ALT, CTRL, SHIFT = 1, 2, 8


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_http(url: str, seconds: float = 15) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            urllib.request.urlopen(url)
            return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"{url} never answered")


@contextmanager
def serve(app_dir: Path, env: dict | None = None) -> Generator[int]:
    """Run the app's uvicorn on a free port for the length of the block."""
    port = free_port()
    proc = subprocess.Popen(
        [
            str(app_dir / ".venv/bin/python"),
            "-m",
            "uvicorn",
            "web_app:app",
            "--port",
            str(port),
        ],
        cwd=app_dir,
        env={**os.environ, **(env or {})},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_http(f"http://127.0.0.1:{port}/")
        yield port
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            # a waiting long poll can hold uvicorn past the 10 s; do not
            # leave it running
            proc.kill()
            proc.wait(5)


class Page:
    def __init__(self, ws) -> None:
        self.ws = ws
        self.n = 0

    async def call(self, method: str, **params):
        self.n += 1
        mid = self.n
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    async def go(self, url: str) -> None:
        await self.call("Page.navigate", url=url)

    async def js(self, expr: str):
        r = await self.call(
            "Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True
        )
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r["result"].get("value")

    async def key(self, key: str, code: str, mods: int = 0, vk: int = 0) -> None:
        """One key press. `vk` is the Windows virtual key code Chrome needs for
        non-text keys and shortcuts (C=67, V=86, Enter=13, F2=113, Delete=46)."""
        text = key if len(key) == 1 and not mods & (CTRL | ALT) else ""
        text = {"Enter": "\r", "Tab": "\t"}.get(key, text)
        for t in ("keyDown", "keyUp"):
            params = dict(
                type=t, key=key, code=code, modifiers=mods, windowsVirtualKeyCode=vk
            )
            if t == "keyDown" and text:
                params["text"] = text
            await self.call("Input.dispatchKeyEvent", **params)

    async def type(self, text: str) -> None:
        await self.call("Input.insertText", text=text)

    async def wait(self, expr: str, timeout: float = 5.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                if await self.js(expr):
                    return True
            except RuntimeError:
                pass  # page still loading: its globals don't exist yet
            await asyncio.sleep(0.1)
        return False

    async def screenshot(self, path: Path) -> None:
        r = await self.call("Page.captureScreenshot", format="png")
        path.write_bytes(base64.b64decode(r["data"]))


async def close_browser(cdp: int) -> None:
    """Browser.close over the DevTools port; quietly nothing if it is gone."""
    try:
        info = json.load(
            urllib.request.urlopen(f"http://127.0.0.1:{cdp}/json/version", timeout=2)
        )
        async with websockets.connect(info["webSocketDebuggerUrl"]) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Browser.close"}))
            await asyncio.wait_for(ws.recv(), 3)
    except Exception:
        pass


def browsers_using(profile: Path, proc_dir: str = "/proc") -> list[int]:
    """Pids whose command line names this Chrome profile folder."""
    needle = f"--user-data-dir={profile}".encode()
    found = []
    for pid in os.listdir(proc_dir):
        if not pid.isdigit():
            continue
        try:
            with open(os.path.join(proc_dir, pid, "cmdline"), "rb") as f:
                if needle in f.read():
                    found.append(int(pid))
        except OSError:
            continue
    return found


def reap(profile: Path, seconds: float = 5) -> list[int]:
    """Stop every process still using `profile`: TERM, then KILL."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in browsers_using(profile):
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        deadline = time.time() + seconds
        while time.time() < deadline and browsers_using(profile):
            time.sleep(0.1)
        if not browsers_using(profile):
            break
    return browsers_using(profile)


@asynccontextmanager
async def chrome_page(
    sandbox: Path, size: str = "1200,800", extra_args: tuple[str, ...] = ()
) -> AsyncGenerator[Page]:
    """Headless Chrome with its profile inside `sandbox` (deleted by the caller).

    `extra_args` adds Chrome flags, e.g. ("--enable-unsafe-swiftshader",) for WebGL pages.
    """
    cdp = free_port()
    proc = subprocess.Popen(
        [
            "flatpak",
            "run",
            # headless checks never open files through the document portal,
            # and when its mount under /run/user/<uid>/doc is gone (seen on
            # 2026-10-08) bwrap refuses to start Chrome at all without this
            "--no-documents-portal",
            f"--filesystem={sandbox}",
            "--command=/app/extra/google-chrome",
            "com.google.Chrome",
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--user-data-dir={sandbox / 'chrome-profile'}",
            f"--remote-debugging-port={cdp}",
            f"--window-size={size}",
            *extra_args,
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        tabs: list[dict] = []
        for _ in range(150):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{cdp}/json"))
                break
            except OSError:
                await asyncio.sleep(0.1)
        target = next(t for t in tabs if t["type"] == "page")
        async with websockets.connect(
            target["webSocketDebuggerUrl"], max_size=None
        ) as ws:
            page = Page(ws)
            await page.call("Page.enable")
            yield page
    finally:
        # Chrome runs inside the Flatpak sandbox, so stopping `flatpak run`
        # alone left the browser running: every check leaked one, and on
        # 2026-09-27 about 300 of them held the CPU at 100%. Ask Chrome to
        # close itself, stop the launcher, then sweep up anything still
        # using this check's own profile folder.
        await close_browser(cdp)
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        reap(sandbox / "chrome-profile")
