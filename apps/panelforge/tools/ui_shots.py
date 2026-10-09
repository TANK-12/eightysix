"""Screenshot every PanelForge tab, with a chapter actually selected.

    .venv/bin/python tools/ui_shots.py --port 8461 --series test-series \
        --chapter 0001 --out /tmp/shots [--tabs library,editor,...]

Plain headless Chrome photographs the app with nothing selected, because the
working series and chapter live in localStorage. This drives Chrome over the
DevTools protocol instead: it sets that context first, then loads each tab and
saves a PNG. Point it at a server started with a temporary PANELFORGE_DATA --
never at the real library, which UI mocks have overwritten before.
"""

import argparse
import base64
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

import websocket

TABS = ["library", "editor", "cast", "previews", "timeline", "render"]
CHROME_PROFILE = os.path.expanduser("~/.var/app/com.google.Chrome/pf-ui-shots")


class Chrome:
    """A headless Flatpak Chrome driven over the DevTools protocol."""

    def __init__(self, port: int = 9335, size=(1400, 1000)):
        self.proc = subprocess.Popen(
            [
                "flatpak",
                "run",
                "com.google.Chrome",
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--hide-scrollbars",
                f"--remote-debugging-port={port}",
                "--remote-allow-origins=*",
                f"--user-data-dir={CHROME_PROFILE}",
                f"--window-size={size[0]},{size[1]}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tabs = None
        for _ in range(60):
            try:
                tabs = json.load(
                    urllib.request.urlopen(f"http://localhost:{port}/json")
                )
                break
            except Exception:
                time.sleep(0.5)
        if not tabs:
            raise RuntimeError("Chrome did not come up on the debugging port")
        page = [t for t in tabs if t["type"] == "page"][0]
        self.ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=120, suppress_origin=True
        )
        self.n = 0
        self.call("Page.enable")
        # Without this the profile's disk cache serves yesterday's JS and the
        # screenshot quietly shows the old UI.
        self.call("Network.enable")
        self.call("Network.setCacheDisabled", cacheDisabled=True)
        self.call(
            "Emulation.setDeviceMetricsOverride",
            width=size[0],
            height=size[1],
            deviceScaleFactor=1,
            mobile=False,
        )

    def call(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                return msg.get("result", {})

    def eval(self, js):
        r = self.call(
            "Runtime.evaluate", expression=js, returnByValue=True, awaitPromise=True
        )
        return r.get("result", {}).get("value")

    def shot(self, path: Path) -> Path:
        data = self.call("Page.captureScreenshot", format="png")["data"]
        path.write_bytes(base64.b64decode(data))
        return path

    def close(self):
        try:
            self.ws.close()
        finally:
            self.proc.terminate()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8461)
    ap.add_argument("--series", default="")
    ap.add_argument("--chapter", default="")
    ap.add_argument("--out", default="ui-shots")
    ap.add_argument("--tabs", default=",".join(TABS))
    ap.add_argument("--wait", type=float, default=3.0, help="seconds per tab")
    ap.add_argument(
        "--js",
        default="",
        help="JavaScript run on each tab after it loads, e.g. to open a drawer",
    )
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{args.port}/"
    chrome = Chrome()
    try:
        chrome.call("Page.navigate", url=base)
        time.sleep(args.wait)
        if args.series:
            chrome.eval(
                "localStorage.setItem('pf.series', %s);"
                "localStorage.setItem('pf.chapter', %s);"
                % (json.dumps(args.series), json.dumps(args.chapter))
            )
        for tab in [t for t in args.tabs.split(",") if t]:
            chrome.call("Page.navigate", url=f"{base}#{tab}")
            chrome.eval("location.reload()")
            time.sleep(args.wait)
            js_result = None
            if args.js:
                js_result = chrome.eval(args.js)  # once: a click run twice toggles back
                time.sleep(min(args.wait, 2.0))
            title = chrome.eval(
                "document.querySelector('nav .active, nav .tab.active')?.textContent || ''"
            )
            errors = chrome.eval("(window.PF && PF.lastError) || ''")
            if args.js:
                print("js:", js_result)
            path = chrome.shot(out / f"{tab}.png")
            print(
                f"{tab}: {path} (nav shows {title!r}{', error ' + errors if errors else ''})"
            )
    finally:
        chrome.close()


if __name__ == "__main__":
    main()
