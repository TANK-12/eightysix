"""Drive the Eighty Six page in headless Chrome, framed the way the Forge hub
frames it, and check the U1 sweep behaviour:

- test names from the game's log are shown as text, never as markup;
- Play is the main button, a double click on it or on Run tests sends one
  request;
- a test run is watched: the button says it is running, the panel fills in
  when the run ends, nothing runs while the hub hides the page, and a server
  that goes away mid-run is asked less and less often, then picked up again;
- opened while the server does not answer, the page says so calmly, backs
  off, rests while hidden and fills in by itself;
- the image viewer closes on Escape; scrollbars are thin; no page errors.

    .venv/bin/python tests/check_ui.py

Not collected by pytest (it needs the Flatpak Chrome). Runs the app on a free
port against a made-up game folder in a temp dir (its play.sh and
run_tests.sh do nothing but sleep and write a log), never ~/Games/eightysix.
"Not answering" at page load is made by the page's own fetch refusing
/api/... (the ?u1block= switch), so the page stays loaded. Prints PASS/FAIL
lines, exits non-zero on a FAIL.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))
from cdp_driver import (  # pyright: ignore[reportMissingImports]
    Page,
    chrome_page,
    free_port,
    wait_http,
)  # noqa: E402  # pyright: ignore[reportMissingImports]

results: list[str] = []


def check(name: str, ok: bool, extra: object = "") -> None:
    note = f" :: {extra}" if extra != "" and not ok else ""
    results.append(f"{'PASS' if ok else 'FAIL'} :: {name}{note}")


COUNTERS = r"""
window.__c = {fetch: 0, raf: 0, timer: 0}; window.__urls = []; window.__e = []; window.__blockOn = true;
addEventListener('error', (e) => __e.push(e.message));
addEventListener('unhandledrejection', (e) => __e.push(String(e.reason)));
{ const of = window.fetch, or = window.requestAnimationFrame,
        ot = window.setTimeout, oi = window.setInterval;
  window.fetch = function (...a) {
    // read per call: an iframe's first blank document shares this window
    const block = new URLSearchParams(location.search).get('u1block');
    __c.fetch++; __urls.push(((a[1] && a[1].method) || 'GET') + ' ' + a[0]);
    if (block && __blockOn && String(a[0]).startsWith('/api/'))
      return Promise.reject(new TypeError('Failed to fetch'));
    return of.apply(this, a);
  };
  window.requestAnimationFrame = (cb) => or.call(window, (t) => { __c.raf++; cb(t); });
  window.setTimeout = (cb, ms, ...r) => ot.call(window, typeof cb === 'function' ? (...x) => { __c.timer++; cb(...x); } : cb, ms, ...r);
  window.setInterval = (cb, ms, ...r) => oi.call(window, (...x) => { __c.timer++; cb(...x); }, ms, ...r);
}
"""
F = "document.getElementById('f').contentWindow"
RESET = f"(() => {{ const w = {F}; Object.keys(w.__c).forEach((k) => (w.__c[k] = 0)); w.__urls.length = 0; return 1; }})()"


def hub(visible: bool) -> str:
    return f"{F}.postMessage({{forge: 'visible', visible: {str(visible).lower()}}}, '*'), 1"


def inner(expr: str) -> str:
    return f"(() => {{ const w = {F}, d = w.document; return ({expr}); }})()"


def calls(prefix: str) -> str:
    return inner(f"w.__urls.filter((u) => u.startsWith({json.dumps(prefix)})).length")


class Server:
    def __init__(self, env: dict) -> None:
        self.port, self.env, self.proc = free_port(), env, None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            [
                str(APP / ".venv/bin/python"),
                "-m",
                "uvicorn",
                "web_app:app",
                "--port",
                str(self.port),
            ],
            cwd=APP,
            env={**os.environ, **self.env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_http(f"http://127.0.0.1:{self.port}/")

    def stop(self) -> None:
        if self.proc:
            self.proc.terminate()
            self.proc.wait(10)
            self.proc = None


def make_game(root: Path) -> None:
    (root / "logs").mkdir(parents=True)
    (root / "tools").mkdir()
    (root / "images/001-walk").mkdir(parents=True)
    (root / "images/002-run").mkdir(parents=True)
    # an fps log with markup where a number belongs
    (root / "logs/fps").mkdir(parents=True)
    (root / "logs/fps/low.json").write_text(
        json.dumps(
            {
                "preset": "low",
                "when": "2026-10-08",
                "avg_fps": 60.0,
                "target_fps": "<i>60</i>",
                "vsync_cap_hz": "<img src=x onerror=\"document.title='bad'\">",
                "est_uncapped_fps": None,
            }
        )
    )
    # a 1x1 png
    (root / "images/001-walk/front.png").write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
            "1f15c4890000000d49444154789c6360f8cfc0000003010100c9fe92ef0000000049454e44ae426082"
        )
    )
    shutil.copy(root / "images/001-walk/front.png", root / "images/002-run/side.png")
    (root / "README.md").write_text(
        "# Eighty Six\n\n## Current state\n\nA test game.\n\n## Log\n\n### 2026-10-08\nmade\n"
    )
    (root / "logs/tests-last.json").write_text(
        json.dumps(
            {
                "passed": 1,
                "failed": 1,
                "seconds": 2,
                "when": "then",
                "tests": [
                    {"name": "<b>bold</b> walker", "ok": True},
                    {"name": "aim", "ok": False, "message": "expected <3 got 5"},
                ],
            }
        )
    )
    for name, body in [
        ("play.sh", "#!/bin/sh\nexit 0\n"),
        (
            "run_tests.sh",
            "#!/bin/sh\nsleep 14\n"
            'echo \'{"passed": 7, "failed": 0, "seconds": 14, "when": "now", "tests": []}\' > logs/tests-last.json\n',
        ),
    ]:
        (root / "tools" / name).write_text(body)
        (root / "tools" / name).chmod(0o755)


async def frame(p: Page, port: int, path: str, ready: str) -> bool:
    await p.go(f"http://127.0.0.1:{port}/no-such-page")
    await p.js(
        "document.body.innerHTML = '<iframe id=f src=\""
        + path
        + '" style="position:fixed;inset:0;width:100vw;height:100vh;border:0"></iframe>\'; 1'
    )
    return await p.wait(inner(ready), 15)


async def run(p: Page, srv: Server) -> None:
    ok = await frame(
        p,
        srv.port,
        "/",
        "!!d.querySelector('.tests-summary') && !!d.querySelector('.thumbs img')",
    )
    check("page fills in", ok)
    bold = await p.js(
        inner(
            "[d.querySelectorAll('#tests-body b').length, d.querySelector('#tests-body li').textContent]"
        )
    )
    check(
        "test names from the log show as text, not markup",
        bold[0] == 0 and "<b>bold</b>" in bold[1],
        bold,
    )
    bg = await p.js(
        inner("w.getComputedStyle(d.getElementById('btn-play')).backgroundColor")
    )
    check(
        "Play is styled as the main button",
        bg not in ("rgba(0, 0, 0, 0)", "transparent"),
        bg,
    )

    await p.js(RESET)
    await p.js(
        inner(
            "(d.getElementById('btn-play').click(), d.getElementById('btn-play').click(), 1)"
        )
    )
    await asyncio.sleep(1)
    check(
        "Play: a double click sends one request",
        await p.js(calls("POST /api/play")) == 1,
    )

    # a test run is watched, rests while hidden, survives the server going away
    await p.js(RESET)
    await p.js(
        inner(
            "(d.getElementById('btn-run-tests').click(), d.getElementById('btn-run-tests').click(), 1)"
        )
    )
    await asyncio.sleep(1)
    check(
        "Run tests: a double click sends one request",
        await p.js(calls("POST /api/tests/run")) == 1,
    )
    label = await p.js(
        inner(
            "[d.getElementById('btn-run-tests').textContent, d.getElementById('btn-run-tests').disabled]"
        )
    )
    check(
        "Run tests: the button says the run is going",
        label == ["Tests running…", True],
        label,
    )
    await p.js(hub(False))
    await asyncio.sleep(5.5)  # past the 5 s toast fade, a one-shot
    await p.js(RESET)
    await asyncio.sleep(5)
    c = json.loads(await p.js(f"JSON.stringify({F}.__c)"))
    check(
        "hidden by the hub during a run: no fetch, frame or timer for 5 s",
        c == {"fetch": 0, "raf": 0, "timer": 0},
        c,
    )
    await p.js(hub(True))
    done = await p.wait(
        inner("d.querySelector('.tests-summary .n').textContent === '7'"), 20
    )
    check("Run tests: the panel fills in when the run ends", done)
    label = await p.js(
        inner(
            "[d.getElementById('btn-run-tests').textContent, d.getElementById('btn-run-tests').disabled]"
        )
    )
    check("Run tests: the button is back", label == ["Run tests", False], label)

    # a server that goes away mid-run: tries back off, then it is picked up
    await p.js(inner("d.getElementById('btn-run-tests').click(), 1"))
    await p.wait(inner("d.getElementById('btn-run-tests').disabled"), 5)
    srv.stop()
    await p.js(RESET)
    await asyncio.sleep(10)
    first = await p.js(calls("GET /api/tests"))
    await asyncio.sleep(20)
    later = await p.js(calls("GET /api/tests")) - first
    check(
        "server gone mid-run: tries back off (0-10 s vs 10-30 s)",
        1 <= first <= 3 and later <= 2,
        (first, later),
    )
    srv.start()
    back = await p.wait(inner("!d.getElementById('btn-run-tests').disabled"), 35)
    check("server back: the page picks the run up by itself", back)

    # the image viewer closes on Escape
    await p.js(inner("d.querySelector('.thumbs img').click(), 1"))
    opened = await p.js(inner("!d.getElementById('lightbox').hidden"))
    await p.js(
        inner("d.dispatchEvent(new w.KeyboardEvent('keydown', {key: 'Escape'})), 1")
    )
    check(
        "image viewer opens and closes on Escape",
        opened and await p.js(inner("d.getElementById('lightbox').hidden")),
    )
    fps = await p.js(
        inner("[d.querySelectorAll('#fps-body img, #fps-body i').length, d.title]")
    )
    check(
        "fps values from the game show as text, not markup",
        fps[0] == 0 and fps[1] != "bad",
        fps,
    )

    # a refresh after a minute away falls back to the newest image folder when
    # the one picked before is gone
    await p.js(inner("d.querySelector('[data-folder=\"001-walk\"]').click(), 1"))
    picked = await p.wait(
        inner("!!d.querySelector('[data-folder=\"001-walk\"].active')"), 5
    )
    game = Path(srv.env["EIGHTYSIX_ROOT"])
    (game / "images/001-walk").rename(game / "images/001-gone")
    await p.js(hub(False))
    await p.js(inner("(w.Date.now = ((n) => () => n() + 61000)(w.Date.now), 1)"))
    await p.js(hub(True))
    back = await p.wait(
        inner("!!d.querySelector('[data-folder=\"002-run\"].active')"), 10
    )
    check(
        "a vanished image folder: the refresh shows the newest instead", picked and back
    )

    sw = await p.js(inner("w.getComputedStyle(d.documentElement).scrollbarWidth"))
    check("scrollbars are thin", sw == "thin", sw)
    errs = await p.js(inner("JSON.stringify(w.__e)"))
    check("no page errors", errs == "[]", errs)

    # opened while the server does not answer
    await frame(
        p,
        srv.port,
        "/?u1block=1",
        "(d.getElementById('root-path').textContent || '').includes('not answering')",
    )
    note = await p.js(inner("d.getElementById('root-path').textContent"))
    check("not answering at load: a calm note", "not answering" in note, note)
    await p.js(RESET)
    await asyncio.sleep(10)
    first = await p.js(calls("GET /api/status"))
    await asyncio.sleep(20)
    later = await p.js(calls("GET /api/status")) - first
    check(
        "not answering at load: tries back off (0-10 s vs 10-30 s)",
        2 <= first <= 4 and later <= 2,
        (first, later),
    )
    await p.js(hub(False))
    await asyncio.sleep(0.3)
    await p.js(RESET)
    await asyncio.sleep(10)
    check(
        "not answering and hidden: no tries for 10 s",
        await p.js(calls("GET /api/")) == 0,
    )
    await p.js(inner("(w.__blockOn = false, 1)"))
    await p.js(hub(True))
    filled = await p.wait(
        inner(
            "!!d.querySelector('.tests-summary') && !!d.querySelector('.thumbs img')"
        ),
        5,
    )
    check("answering again: the page fills in by itself", filled)


async def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="eightysix-check-"))
    make_game(tmp / "game")
    srv = Server(
        {
            "EIGHTYSIX_ROOT": str(tmp / "game"),
            "FORGE_SHARED_DIR": str(APP.parents[1] / "shared"),
        }
    )
    srv.start()
    try:
        async with chrome_page(tmp, size="1200,900") as p:
            await p.call("Page.addScriptToEvaluateOnNewDocument", source=COUNTERS)
            await run(p, srv)
    finally:
        srv.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n".join(results))
    return 1 if any(r.startswith("FAIL") for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
