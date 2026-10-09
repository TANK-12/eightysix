#!/usr/bin/env python3
"""
Screenshot a page in headless Firefox, after its JavaScript has settled.

Why this exists: the working agreement says a UI change is not done until it
has been looked at in a browser, and the Chrome extension is not connected on
this machine. `firefox --screenshot` alone is not enough -- it fires on the load
event, so a page that fetches its data afterwards is captured empty.

So this drives Firefox over **Marionette**, its built-in automation socket. The
protocol is length-prefixed JSON over TCP, which means a client fits in a page
of stdlib and adds no dependency to the project.

    ./.venv/bin/python tools/shot.py http://127.0.0.1:8436/#/my-song/scenery out.png
    ./.venv/bin/python tools/shot.py URL out.png --wait "document.querySelectorAll('.sc-card').length > 3"
    ./.venv/bin/python tools/shot.py URL out.png --click "#scTool_brush" --size 1500x1200

`--wait` is a JavaScript expression polled until it returns true, which is the
part that makes the capture trustworthy: you assert the page is actually ready
rather than guessing at a sleep.
"""

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

PORT = 2829  # not the default 2828, so this never fights a real Firefox


class Marionette:
    def __init__(self, port=PORT, timeout=60):
        self.sock = None
        self.msg_id = 0
        self.port = port
        self.timeout = timeout

    def connect(self):
        deadline = time.time() + self.timeout
        last = None
        while time.time() < deadline:
            try:
                s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
                s.settimeout(60)
                self.sock = s
                self._read()  # the server greeting
                return
            except OSError as e:
                last = e
                time.sleep(0.3)
        raise RuntimeError(f"could not reach Marionette on {self.port}: {last}")

    def _live(self):
        if self.sock is None:
            raise RuntimeError("not connected -- call connect() first")
        return self.sock

    def _read(self):
        sock = self._live()
        length = b""
        while not length.endswith(b":"):
            ch = sock.recv(1)
            if not ch:
                raise RuntimeError("Marionette closed the connection")
            length += ch
        n = int(length[:-1])
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise RuntimeError("Marionette closed mid-message")
            buf += chunk
        return json.loads(buf)

    def call(self, name, params=None):
        self.msg_id += 1
        payload = json.dumps([0, self.msg_id, name, params or {}]).encode()
        self._live().sendall(f"{len(payload)}:".encode() + payload)
        while True:
            msg = self._read()
            if isinstance(msg, list) and len(msg) >= 4 and msg[0] == 1:
                _, _mid, err, result = msg[:4]
                if err:
                    raise RuntimeError(f"{name} failed: {err}")
                return result

    def script(self, js, args=None):
        return self.call(
            "WebDriver:ExecuteScript",
            {"script": js, "args": args or [], "newSandbox": False},
        ).get("value")

    def close(self):
        if self.sock:
            try:
                self.call("Marionette:Quit", {"flags": ["eForceQuit"]})
            except Exception:
                pass
            self.sock.close()


def firefox_binary():
    for name in ("firefox", "firefox-esr", "librewolf"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("no firefox on PATH")


def capture(url, out, size, wait_js, clicks, settle, keep_open=False):
    profile = tempfile.mkdtemp(prefix="pf-shot-")
    # the port comes from a profile pref, not the environment
    with open(os.path.join(profile, "user.js"), "w") as f:
        f.write(f'user_pref("marionette.port", {PORT});\n')
        f.write('user_pref("browser.shell.checkDefaultBrowser", false);\n')
        f.write('user_pref("datareporting.policy.firstRunURL", "");\n')
        f.write('user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);\n')
    w, h = size
    proc = subprocess.Popen(
        [
            firefox_binary(),
            "--headless",
            "--no-remote",
            "--profile",
            profile,
            "--marionette",
            "--window-size",
            f"{w},{h}",
            "about:blank",
        ],
        env={**os.environ, "MOZ_HEADLESS": "1"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    m = Marionette()
    try:
        m.connect()
        m.call("WebDriver:NewSession", {})
        m.call("WebDriver:SetWindowRect", {"width": w, "height": h})
        m.call("WebDriver:Navigate", {"url": url})

        # Collect page errors from here on. Without this the report below is
        # always empty, which is worse than no report -- it looks like the page
        # is fine when nothing was ever listening.
        m.script(
            "window.__shotErrors = window.__shotErrors || [];"
            "window.addEventListener('error', function (e) {"
            "  window.__shotErrors.push(String(e.message) + ' @ ' +"
            "    (e.filename || '?') + ':' + (e.lineno || 0)); });"
            "window.addEventListener('unhandledrejection', function (e) {"
            "  window.__shotErrors.push('unhandled: ' + String(e.reason)); });"
            "var _ce = console.error;"
            "console.error = function () {"
            "  window.__shotErrors.push(Array.prototype.join.call(arguments, ' '));"
            "  return _ce.apply(console, arguments); };"
        )

        if wait_js:
            deadline = time.time() + 45
            ok = False
            while time.time() < deadline:
                try:
                    if m.script(f"return !!({wait_js});"):
                        ok = True
                        break
                except Exception:
                    pass
                time.sleep(0.25)
            if not ok:
                print(
                    f"warning: condition never became true: {wait_js}", file=sys.stderr
                )

        for sel in clicks or []:
            m.script(
                "var e=document.querySelector(arguments[0]); if(e) e.click();", [sel]
            )
            time.sleep(0.4)

        if settle:
            time.sleep(settle)

        png = m.call("WebDriver:TakeScreenshot", {"full": True, "hash": False})["value"]
        with open(out, "wb") as f:
            f.write(base64.b64decode(png))

        errors = m.script("return (window.__shotErrors || []).slice(0, 8);") or []
        return out, errors
    finally:
        if not keep_open:
            m.close()
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--size", default="1440x1200", help="WIDTHxHEIGHT")
    ap.add_argument("--wait", default="", help="JS expression polled until true")
    ap.add_argument(
        "--click", action="append", default=[], help="CSS selector to click"
    )
    ap.add_argument(
        "--settle", type=float, default=1.0, help="extra seconds before the shot"
    )
    args = ap.parse_args()
    w, h = (int(v) for v in args.size.lower().split("x"))
    out, errors = capture(
        args.url, args.out, (w, h), args.wait, args.click, args.settle
    )
    print(f"wrote {out} ({os.path.getsize(out)} bytes)")
    for e in errors:
        print("page error:", e, file=sys.stderr)


if __name__ == "__main__":
    main()
