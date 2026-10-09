"""Drive Drift Peaks in headless Chrome, framed the way the Forge hub frames
it, and check the U1 sweep behaviour:

- hidden by the hub: the music pauses, and 10 s pass without a fetch, an
  animation frame or a timer; shown again, the music carries on;
- a settings save that fails is tried again, less and less often, never while
  hidden, and lands by itself once the server is back;
- the Art editor sends one save for a double click and answers a dead server
  with a calm sentence;
- thin scrollbars, no page errors.

    .venv/bin/python tests/check_ui.py

Not collected by pytest (it needs the Flatpak Chrome). Runs the app on a free
port with a sandbox save, shape store and a one-second music file; never the
real ones. Prints PASS/FAIL lines, exits non-zero on a FAIL.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave
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


COUNTERS = r"""
window.__c = {fetch: 0, raf: 0, timer: 0}; window.__urls = []; window.__e = [];
addEventListener('error', (e) => __e.push(e.message));
addEventListener('unhandledrejection', (e) => __e.push(String(e.reason)));
{ const of = window.fetch, or = window.requestAnimationFrame,
        ot = window.setTimeout, oi = window.setInterval, op = HTMLMediaElement.prototype.play;
  window.fetch = function (...a) { __c.fetch++; __urls.push(((a[1] && a[1].method) || 'GET') + ' ' + a[0]); return of.apply(this, a); };
  window.requestAnimationFrame = (cb) => or.call(window, (t) => { __c.raf++; cb(t); });
  window.setTimeout = (cb, ms, ...r) => ot.call(window, typeof cb === 'function' ? (...x) => { __c.timer++; cb(...x); } : cb, ms, ...r);
  window.setInterval = (cb, ms, ...r) => oi.call(window, (...x) => { __c.timer++; cb(...x); }, ms, ...r);
  HTMLMediaElement.prototype.play = function () { window.__media = this; return op.call(this); }; }
"""
F = "document.getElementById('f').contentWindow"
RESET = f"(() => {{ const w = {F}; Object.keys(w.__c).forEach((k) => (w.__c[k] = 0)); w.__urls.length = 0; return 1; }})()"


def hub(visible: bool) -> str:
    return f"{F}.postMessage({{forge: 'visible', visible: {str(visible).lower()}}}, '*'), 1"


def inner(expr: str) -> str:
    return f"(() => {{ const w = {F}, d = w.document; return ({expr}); }})()"


async def counts(p: Page, seconds: float) -> dict:
    await asyncio.sleep(0.3)  # the one frame already asked for before a change
    await p.js(RESET)
    await asyncio.sleep(seconds)
    return json.loads(await p.js(f"JSON.stringify({F}.__c)"))


SAVES = inner("w.__urls.filter((u) => u === 'PUT api/save').length")
PLAYING = inner("!!w.__media && !w.__media.paused")


async def run(p: Page, srv: Server, save: Path) -> None:
    await p.go(f"http://127.0.0.1:{srv.port}/no-such-page")
    await p.js(
        'document.body.innerHTML = \'<iframe id=f src="/" style="position:fixed;inset:0;'
        "width:100vw;height:100vh;border:0\"></iframe>'; 1"
    )
    await p.wait(inner("d.body && d.body.dataset.ready === '1'"), 15)

    # music starts on the first key, pauses while hidden, carries on after
    await p.js(
        inner("w.dispatchEvent(new w.KeyboardEvent('keydown', {code: 'KeyM'})), 1")
    )
    check("a key starts the music", await p.wait(PLAYING, 8))
    await p.js(hub(False))
    await asyncio.sleep(0.5)
    check("hidden by the hub: the music pauses", not await p.js(PLAYING))
    c = await counts(p, 10)
    check(
        "hidden by the hub: 10 s without work",
        c == {"fetch": 0, "raf": 0, "timer": 0},
        c,
    )
    await p.js(hub(True))
    check("shown again: the music carries on", await p.wait(PLAYING, 5))
    c = await counts(p, 2)
    check("shown again: the mountain draws", c["raf"] > 20, c)

    # a save that fails is retried with backoff, never while hidden
    await p.js(inner("d.getElementById('settings-btn').click(), 1"))
    srv.stop()
    await p.js(RESET)
    await p.js(
        inner(
            "(() => { const s = d.querySelector('#settings-form input[type=range]');"
            " s.value = 25; s.dispatchEvent(new Event('input')); return 1; })()"
        )
    )
    await asyncio.sleep(10)
    first = await p.js(SAVES)
    await asyncio.sleep(20)
    later = await p.js(SAVES) - first
    check(
        "server down: tries back off (0-10 s vs 10-30 s)",
        2 <= first <= 4 and later <= 2,
        (first, later),
    )
    await p.js(hub(False))
    await asyncio.sleep(0.3)
    await p.js(RESET)
    await asyncio.sleep(20)
    check("server down and hidden: no tries for 20 s", await p.js(SAVES) == 0)
    srv.start()
    await p.js(hub(True))
    await asyncio.sleep(2)
    kept = (
        json.loads(save.read_text()).get("settings", {}).get("volume")
        if save.is_file()
        else None
    )
    check("server back and shown: the change is saved by itself", kept == 25, kept)

    # Art: one save for a double click, a calm word for a dead server
    await p.js(
        inner(
            "d.getElementById('settings-close').click(), d.getElementById('art-btn').click(), 1"
        )
    )
    await p.wait(inner("d.querySelector('.art-tile')"), 5)
    await p.js(inner("d.querySelector('.art-tile').click(), 1"))
    await p.js(RESET)
    await p.js(
        inner(
            "(d.getElementById('art-save').click(), d.getElementById('art-save').click(), 1)"
        )
    )
    await asyncio.sleep(1.5)
    puts = await p.js(
        inner("w.__urls.filter((u) => u.startsWith('PUT api/shapes')).length")
    )
    check("Art: a double click saves once", puts == 1, puts)
    srv.stop()
    await p.js(inner("d.getElementById('art-save').click(), 1"))
    await asyncio.sleep(1.5)
    status = await p.js(inner("d.getElementById('art-status').textContent"))
    check(
        "Art: a dead server gets a calm sentence",
        "not answering" in (status or ""),
        status,
    )
    again = await p.js(inner("!d.getElementById('art-save').disabled"))
    check("Art: the buttons work again afterwards", again)
    srv.start()

    sw = await p.js(
        inner("w.getComputedStyle(d.getElementById('settings')).scrollbarWidth")
    )
    check("panel scrollbars are thin", sw == "thin", sw)
    errs = await p.js(inner("JSON.stringify(w.__e)"))
    check("no page errors", errs == "[]", errs)


def one_second_of_music(folder: Path) -> None:
    folder.mkdir(parents=True)
    with wave.open(str(folder / "tone.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0\1" * 8000)


async def main() -> int:
    box = Path(tempfile.mkdtemp(prefix="driftpeaks-check-"))
    one_second_of_music(box / "music")
    save = box / "save" / "save.json"
    srv = Server(
        {
            "HOME": str(box / "home"),
            "DRIFTPEAKS_DATA": str(save.parent),
            "DRIFTPEAKS_MUSIC": str(box / "music"),
            "FORGE_CONTENT_DIR": str(box / "store"),
            "FORGE_SHARED_DIR": str(APP.parents[1] / "shared"),
        }
    )
    try:
        srv.start()
        flags = ("--autoplay-policy=no-user-gesture-required",)
        async with chrome_page(box, "1280,800", flags) as p:
            await p.call("Page.addScriptToEvaluateOnNewDocument", source=COUNTERS)
            await run(p, srv, save)
    finally:
        srv.stop()
        reap(box)
        shutil.rmtree(box, ignore_errors=True)
    print("\n".join(results))
    return 1 if any(r.startswith("FAIL") for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
