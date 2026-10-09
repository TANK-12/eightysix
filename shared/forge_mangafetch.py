"""Shared manga/webtoon page fetcher: headless Flatpak Chrome over CDP.

Used by PanelForge's ``panelforge/sources/`` modules and available to
MediaForge's Manga Downloader (its own venv only needs the stdlib plus
``websocket-client``, both already present there).

Why CDP and not Selenium: the only Chrome on this machine is the Flatpak
build, which plain Selenium cannot drive (no matching chromedriver). This
module talks to it directly over the DevTools protocol instead.

Two hard rules learned building the comix.to prototype
(``tools/proto_comix_fetch.py`` in panelforge, see its HANDOFF.md):
  - ``canvas.toDataURL()`` on an anti-scraping canvas returns a blank image.
    The only reliable capture is a clipped ``Page.captureScreenshot`` of the
    canvas's *rendered* rect, at ``canvas.width / rect.width`` scale.
  - A screenshot taken too early (page still loading, or a page-counter
    overlay still showing) is silently wrong. Accept a canvas capture only
    once it has real content (grayscale stddev above a threshold) AND two
    captures in a row are byte-identical.

Every caller should fetch each chapter in **two passes**: run the page list
once, note failures/missing pages, then run again for just those pages. Site
images sometimes fail to load on the first attempt.
"""

from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import websocket  # websocket-client

CHROME_APP_ID = "com.google.Chrome"


class FetchError(Exception):
    pass


def _find_free_port() -> int:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@dataclass
class ChromeCDP:
    """One headless Flatpak Chrome tab, driven over the DevTools protocol.

    Use as a context manager::

        with ChromeCDP() as chrome:
            chrome.navigate(url)
            info = chrome.eval("document.title")
    """

    width: int = 1000
    height: int = 1400
    profile: str = "pf-mangafetch"
    port: int = field(default=0)
    _proc: Optional[subprocess.Popen] = field(default=None, repr=False)
    _ws: Optional[Any] = field(default=None, repr=False)
    _msg_id: int = field(default=0, repr=False)

    def __enter__(self) -> "ChromeCDP":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def start(self) -> None:
        if not self.port:
            self.port = _find_free_port()
        user_data = os.path.expanduser(f"~/.var/app/{CHROME_APP_ID}/{self.profile}")
        self._proc = subprocess.Popen(
            [
                "flatpak",
                "run",
                CHROME_APP_ID,
                "--headless=new",
                "--disable-gpu",
                f"--remote-debugging-port={self.port}",
                "--remote-allow-origins=*",
                f"--user-data-dir={user_data}",
                f"--window-size={self.width},{self.height}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tabs = None
        for _ in range(60):
            try:
                tabs = json.load(
                    urllib.request.urlopen(
                        f"http://localhost:{self.port}/json", timeout=2
                    )
                )
                break
            except Exception:
                time.sleep(0.5)
        if not tabs:
            raise FetchError(
                "headless Chrome (Flatpak) did not come up on the debug port"
            )
        page = next(t for t in tabs if t["type"] == "page")
        self._ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=120, suppress_origin=True
        )
        self.call("Page.enable")
        self.call(
            "Emulation.setDeviceMetricsOverride",
            width=self.width,
            height=self.height,
            deviceScaleFactor=1,
            mobile=False,
        )

    def close(self) -> None:
        try:
            if self._ws:
                self.call("Browser.close")
        except Exception:
            pass
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
        if self._proc:
            try:
                self._proc.wait(timeout=20)
            except Exception:
                self._proc.kill()

    def call(self, method: str, **params: Any) -> dict:
        assert self._ws is not None
        self._msg_id += 1
        mid = self._msg_id
        self._ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            m = json.loads(self._ws.recv())
            if m.get("id") == mid:
                if "error" in m:
                    raise FetchError(f"{method}: {m['error']}")
                return m.get("result", {})

    def eval(self, js: str, await_promise: bool = False) -> Any:
        r = self.call(
            "Runtime.evaluate",
            expression=js,
            returnByValue=True,
            awaitPromise=await_promise,
        )
        if "exceptionDetails" in r:
            raise FetchError(r["exceptionDetails"].get("text", "eval failed"))
        return r.get("result", {}).get("value")

    def navigate(self, url: str, settle: float = 6.0) -> None:
        self.call("Page.navigate", url=url)
        time.sleep(settle)

    def user_agent(self) -> str:
        return self.eval("navigator.userAgent")

    def screenshot_clip(
        self, x: float, y: float, w: float, h: float, scale: float = 1.0
    ) -> bytes:
        shot = self.call(
            "Page.captureScreenshot",
            format="png",
            clip={"x": x, "y": y, "width": w, "height": h, "scale": scale},
        )
        return base64.b64decode(shot["data"])


def capture_canvas_stable(
    chrome: ChromeCDP,
    rect_js: str,
    tries: int = 20,
    settle: float = 2.0,
    stddev_min: float = 4.0,
) -> Optional[bytes]:
    """Clip-screenshot a canvas until two captures in a row match and are non-blank.

    ``rect_js`` must evaluate to ``{x,y,w,h,cw}`` (page coords of the visible
    rect, plus the canvas's own pixel width) or ``null`` if not present.
    """
    from PIL import Image, ImageStat

    prev: Optional[bytes] = None
    for _ in range(tries):
        time.sleep(settle)
        r = chrome.eval(rect_js)
        if not r:
            continue
        raw = chrome.screenshot_clip(
            r["x"], r["y"], r["w"], r["h"], scale=r["cw"] / r["w"]
        )
        st = ImageStat.Stat(Image.open(io.BytesIO(raw)).convert("L"))
        if st.stddev[0] > stddev_min and prev == raw:
            return raw
        prev = raw
    return None


def download_image(
    url: str, referer: str, user_agent: str, timeout: float = 30
) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": user_agent, "Referer": referer}
    )
    return urllib.request.urlopen(req, timeout=timeout).read()


def sniff_ext(data: bytes) -> str:
    if data[:4] == b"\x89PNG":
        return "png"
    if data[8:12] == b"WEBP":
        return "webp"
    if data[:2] == b"\xff\xd8":
        return "jpg"
    return "bin"


# ---------------------------------------------------------------------------
# Page verification, shared by every source and by import.
# ---------------------------------------------------------------------------


@dataclass
class PageCheck:
    ok: bool
    reason: str = ""
    width: int = 0
    height: int = 0


def verify_page_bytes(
    data: bytes,
    expect_w: Optional[int] = None,
    expect_h: Optional[int] = None,
    blank_stddev_min: float = 3.0,
) -> PageCheck:
    """Decode, size and blank checks. Does not compare to neighbours (see seam_score)."""
    from PIL import Image, ImageStat

    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:
        return PageCheck(False, f"does not decode: {e}")
    w, h = im.size
    if w <= 0 or h <= 0:
        return PageCheck(False, "zero-sized image")
    if expect_w and abs(w - expect_w) > 2:
        return PageCheck(False, f"width {w} != expected {expect_w}", w, h)
    if expect_h and abs(h - expect_h) > 2:
        return PageCheck(False, f"height {h} != expected {expect_h}", w, h)
    st = ImageStat.Stat(im.convert("L"))
    if st.stddev[0] < blank_stddev_min:
        return PageCheck(False, f"looks blank (stddev {st.stddev[0]:.2f})", w, h)
    return PageCheck(True, "", w, h)


def seam_score(top_data: bytes, bottom_data: bytes, strip_px: int = 4) -> float:
    """Brightness difference between the bottom rows of one page and the top
    rows of the next. Used to spot a scrambled/half-drawn canvas capture: a
    real seam between two webtoon pages looks about the same whether both
    pages were plain downloads or canvas screenshots. A much larger jump
    means one side is corrupt (partial draw, stray tile, wrong crop).
    """
    from PIL import Image

    a = Image.open(io.BytesIO(top_data)).convert("L")
    b = Image.open(io.BytesIO(bottom_data)).convert("L")
    aw, ah = a.size
    bw, bh = b.size
    a_strip = a.crop((0, max(0, ah - strip_px), aw, ah))
    b_strip = b.crop((0, 0, bw, min(bh, strip_px)))
    a_bytes, b_bytes = a_strip.tobytes(), b_strip.tobytes()
    a_mean = sum(a_bytes) / len(a_bytes)
    b_mean = sum(b_bytes) / len(b_bytes)
    return abs(a_mean - b_mean)
