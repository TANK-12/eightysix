"""Drive the Arcade page in headless Chrome, framed the way the Forge hub
frames it, and check the U1 sweep behaviour:

- hidden by the hub (menu, and a game with sound running): no fetch, no
  animation frame and no timer for 10 s, the game pauses, sound timers stop;
- shown again: the sound timers come back after Resume;
- the backend going away and coming back: the menu dot follows by itself
  when the page is shown again, and flipping visibility never storms /api/status;
- a game that wants Jan says plainly that it uses the built-in brain;
- thin themed scrollbars.

    .venv/bin/python tests/check_ui.py

Not collected by pytest (it needs the Flatpak Chrome). Runs the app on a free
port with a sandbox home (never the real Hearsay save) and a Jan address
nothing listens on. Prints PASS/FAIL lines, exits non-zero on a FAIL.
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
from cdp_driver import Page, chrome_page, free_port, reap, wait_http  # noqa: E402

results: list[str] = []


def check(name: str, ok: bool, extra: object = "") -> None:
    note = f" :: {extra}" if extra != "" and not ok else ""
    results.append(f"{'PASS' if ok else 'FAIL'} :: {name}{note}")


class Server:
    """The app on one port that can be stopped and started again."""

    def __init__(self, env: dict) -> None:
        self.port, self.env, self.proc = free_port(), env, None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            [str(APP / ".venv/bin/python"), "-m", "uvicorn", "web_app:app"]
            + ["--port", str(self.port)],
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


# counts in every frame: fetches (with their urls), animation frames, timers
COUNTERS = r"""
window.__c = {fetch: 0, raf: 0, timer: 0}; window.__urls = []; window.__e = [];
addEventListener('error', (e) => __e.push(e.message));
addEventListener('unhandledrejection', (e) => __e.push(String(e.reason)));
{ const of = window.fetch, or = window.requestAnimationFrame,
        ot = window.setTimeout, oi = window.setInterval;
  window.fetch = function (...a) { __c.fetch++; __urls.push(String(a[0])); return of.apply(this, a); };
  window.requestAnimationFrame = (cb) => or.call(window, (t) => { __c.raf++; cb(t); });
  window.setTimeout = (cb, ms, ...r) => ot.call(window, typeof cb === 'function' ? (...x) => { __c.timer++; cb(...x); } : cb, ms, ...r);
  window.setInterval = (cb, ms, ...r) => oi.call(window, (...x) => { __c.timer++; cb(...x); }, ms, ...r); }
"""
F = "document.getElementById('f').contentWindow"
RESET = f"(() => {{ const w = {F}; Object.keys(w.__c).forEach((k) => (w.__c[k] = 0)); w.__urls.length = 0; return 1; }})()"
COUNT = f"JSON.stringify({F}.__c)"


def hub(visible: bool) -> str:
    return f"{F}.postMessage({{forge: 'visible', visible: {str(visible).lower()}}}, '*'), 1"


def inner(expr: str) -> str:
    return f"(() => {{ const w = {F}, d = w.document; return ({expr}); }})()"


async def counts(p: Page, seconds: float) -> dict:
    await asyncio.sleep(0.3)  # the one frame already asked for before a change
    await p.js(RESET)
    await asyncio.sleep(seconds)
    return json.loads(await p.js(COUNT))


async def run(p: Page, srv: Server) -> None:
    base = f"http://127.0.0.1:{srv.port}"
    # a same-origin parent page holding the app in an iframe, like the hub
    await p.go(f"{base}/no-such-page")
    await p.js(
        'document.body.innerHTML = \'<iframe id=f src="/" style="position:fixed;inset:0;'
        "width:100vw;height:100vh;border:0\"></iframe>'; 1"
    )
    await p.wait(inner("w.ForgeVisible && d.querySelector('.card')"), 10)
    await asyncio.sleep(1.5)
    check("the menu draws while shown", (await counts(p, 2))["raf"] > 20)

    await p.js(hub(False))
    c = await counts(p, 10)
    check(
        "menu hidden by the hub: 10 s without work",
        c == {"fetch": 0, "raf": 0, "timer": 0},
        c,
    )
    await p.js(hub(True))

    # a game with sound: the demo tone, then Aphelion (it has its own bed too)
    await p.js(
        inner(
            "d.getElementById('chipBtn').click(), d.getElementById('pickDemo').click(), 1"
        )
    )
    await p.js(inner("d.querySelector('[data-id=aphelion]').click(), 1"))
    await asyncio.sleep(0.4)
    await p.js(inner("d.getElementById('beginBtn').click(), 1"))
    await asyncio.sleep(1.5)
    playing = await counts(p, 3)
    check("playing: the sound scheduler ticks", playing["timer"] > 3, playing)
    await p.js(hub(False))
    await asyncio.sleep(0.5)
    check(
        "hidden by the hub: the game pauses",
        await p.js(inner("!d.getElementById('pauseScreen').hidden")),
    )
    c = await counts(p, 10)
    check(
        "paused and hidden: 10 s without work",
        c == {"fetch": 0, "raf": 0, "timer": 0},
        c,
    )
    await p.js(hub(True))
    await asyncio.sleep(0.5)
    c = await counts(p, 3)
    check("shown but still paused: no sound timers", c["timer"] == 0, c)
    await p.js(inner("d.getElementById('resumeBtn').click(), 1"))
    await asyncio.sleep(0.5)
    c = await counts(p, 3)
    check("resumed: the sound scheduler is back", c["timer"] > 3, c)
    await p.js(inner("d.getElementById('backBtn').click(), 1"))

    # Hearsay with Jan off: the intro names the built-in brain
    await p.js(inner("d.querySelector('[data-id=hearsay]').click(), 1"))
    await asyncio.sleep(0.6)
    badge = await p.js(inner("d.getElementById('introBadge').textContent"))
    check(
        "Hearsay says it uses the built-in brain",
        "built-in brain" in (badge or ""),
        badge,
    )
    await p.js(inner("d.getElementById('backBtn').click(), 1"))

    # the backend goes away: shown again, the dot says so (one status ask)
    srv.stop()
    await p.js(inner("(w.__c.fetch = 0, w.__urls.length = 0, 1)"))
    await asyncio.sleep(15.5)
    await p.js(hub(False))
    await p.js(hub(True))
    await asyncio.sleep(1.5)
    dot = await p.js(inner("d.getElementById('chipDot').className"))
    check("backend down: the menu dot turns red", "no" in (dot or ""), dot)
    for _ in range(20):
        await p.js(hub(False))
        await p.js(hub(True))
    await asyncio.sleep(1)
    asks = await p.js(inner("w.__urls.filter((u) => u.includes('api/status')).length"))
    check("flipping visibility 20 times asks for status at most once", asks == 1, asks)

    srv.start()
    await asyncio.sleep(15)
    await p.js(hub(False))
    await p.js(hub(True))
    await p.wait(inner("!d.getElementById('chipDot').classList.contains('no')"), 5)
    dot = await p.js(inner("d.getElementById('chipDot').className"))
    check("backend back: the dot recovers by itself", "no" not in (dot or ""), dot)

    sw = await p.js(
        inner("w.getComputedStyle(d.getElementById('menu')).scrollbarWidth")
    )
    check("menu scrollbar is thin", sw == "thin", sw)
    errs = await p.js(inner("JSON.stringify(w.__e)"))
    check("no page errors", errs == "[]", errs)


async def main() -> int:
    box = Path(tempfile.mkdtemp(prefix="arcade-check-"))
    srv = Server(
        {
            "HOME": str(box / "home"),
            "JAN_BASE_URL": "http://127.0.0.1:9/v1",
            "FORGE_SHARED_DIR": str(APP.parents[1] / "shared"),
        }
    )
    try:
        srv.start()
        # headless clicks are not a user gesture: let the sound start anyway
        flags = ("--autoplay-policy=no-user-gesture-required",)
        async with chrome_page(box, "1280,800", flags) as p:
            await p.call("Page.addScriptToEvaluateOnNewDocument", source=COUNTERS)
            await run(p, srv)
    finally:
        srv.stop()
        reap(box)
        shutil.rmtree(box, ignore_errors=True)
    print("\n".join(results))
    return 1 if any(r.startswith("FAIL") for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
