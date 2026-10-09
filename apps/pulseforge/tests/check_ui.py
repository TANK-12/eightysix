"""Drive the real PulseForge page in headless Chrome for the U1 sweep checks.

    .venv/bin/python tests/check_ui.py [port]

Not collected by pytest (it needs the Flatpak Chrome and ffmpeg). It starts its
own backend on `port` (default 9051) with HOME pointed at a sandbox folder, so
nothing lands in the real ~/PulseForgeData, and stops it by PID. The page runs
inside an iframe so the hub's "visible" message can be sent the way Forge does.

Checks:
- hidden by the hub, 10 s without fetches, timers or animation frames; shown
  again, the queue poll comes back;
- a looping, silent preview video pauses while hidden and plays when shown;
- a double click on Render, Create or Make sends one request;
- a project name with markup in it is shown as text;
- the Simple editor's empty preview is a calm note, not a broken image;
- with the server down the queue poll backs off (fewer asks 10-30 s than in
  the first 10 s) and says so; when it is back the page recovers by itself;
- a start that cannot reach the server shows a calm card and recovers by itself;
- no script errors or unhandled rejections.
Prints PASS/FAIL lines and exits non-zero on any FAIL.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))
from cdp_driver import Page, chrome_page, reap  # noqa: E402

results: list[str] = []


def check(name: str, ok: bool, extra: object = "") -> None:
    results.append(
        f"{'PASS' if ok else 'FAIL'} :: {name}" + (f" :: {extra}" if not ok else "")
    )


COUNTERS = r"""
window.__c = {fetch: 0, raf: 0, timer: 0}; window.__urls = []; window.__e = [];
window.__blockOn = true;
addEventListener('error', (e) => __e.push(e.message));
addEventListener('unhandledrejection', (e) => __e.push(String(e.reason)));
{ const of = window.fetch, or = window.requestAnimationFrame,
        ot = window.setTimeout, oi = window.setInterval;
  window.fetch = function (...a) {
    const block = new URLSearchParams(location.search).get('u1block');
    __c.fetch++; __urls.push(((a[1] && a[1].method) || 'GET') + ' ' + a[0]);
    if (block && __blockOn && String(a[0]).includes(block))
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
READY = "d.body && d.body.dataset.ready === '1'"


def hub(visible: bool) -> str:
    return f"{F}.postMessage({{forge: 'visible', visible: {str(visible).lower()}}}, '*'), 1"


def inner(expr: str) -> str:
    return f"(() => {{ const w = {F}, d = w.document; return ({expr}); }})()"


def calls(word: str, method: str = "") -> str:
    want = json.dumps(word)
    pre = json.dumps(method + " " if method else "")
    return inner(
        f"w.__urls.filter((u) => u.includes({want}) && u.startsWith({pre})).length"
    )


class Server:
    def __init__(self, port: int, home: Path) -> None:
        self.port, self.home, self.proc = port, home, None

    def start(self) -> None:
        env = dict(os.environ, HOME=str(self.home))
        env["FORGE_SHARED_DIR"] = str(APP.parents[1] / "shared")
        self.proc = subprocess.Popen(
            [
                str(APP / ".venv/bin/python"),
                "-m",
                "uvicorn",
                "web_app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=APP,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        (self.home / "server.pid").write_text(str(self.proc.pid))
        for _ in range(120):
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/api/state", timeout=1
                )
                return
            except OSError:
                time.sleep(0.25)
        raise RuntimeError("the scratch server did not start")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        return json.load(urllib.request.urlopen(req))


async def frame(p: Page, port: int, path: str, ready: str = READY) -> bool:
    await p.go(f"http://127.0.0.1:{port}/no-such-page")
    await p.js(
        "document.body.innerHTML = '<iframe id=f src=\""
        + path
        + '" style="position:fixed;inset:0;width:100vw;height:100vh;border:0"></iframe>\'; 1'
    )
    return await p.wait(inner(ready), 20)


async def counts(p: Page, seconds: float) -> dict:
    await asyncio.sleep(0.3)
    await p.js(RESET)
    await asyncio.sleep(seconds)
    return json.loads(await p.js(f"JSON.stringify({F}.__c)"))


async def run(p: Page, srv: Server) -> None:
    port = srv.port
    slug = srv.post("/api/projects", {"name": "Sweep check"})["slug"]
    srv.post("/api/projects", {"name": '<img src=x onerror="window.__pwned=1">'})
    renders = srv.home / "PulseForgeData/projects" / slug / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=24:duration=2",
            "-pix_fmt",
            "yuv420p",
            str(renders / "loop.mp4"),
        ],
        check=True,
    )
    await p.call("Page.addScriptToEvaluateOnNewDocument", source=COUNTERS)

    # markup in a name is text; the Simple editor's empty preview is a note
    check("page loads", await frame(p, port, "/"))
    listed = await p.js(inner("d.getElementById('projList').innerText"))
    check(
        "a name with markup in it shows as text",
        "<img" in (listed or "")
        and not await p.js(inner("!!d.querySelector('#projList img') || !!w.__pwned")),
        listed,
    )
    await p.js(
        inner(f"(w.applyMode('simple', {{save: false}}), w.openProject('{slug}'), 1)")
    )
    await asyncio.sleep(1.5)
    still = await p.js(
        inner(
            "[w.getComputedStyle(d.getElementById('smStill')).display,"
            " w.getComputedStyle(d.querySelector('.sm-empty')).display].join(' ')"
        )
    )
    check(
        "Simple preview with no picture: a note, no broken image",
        still == "none grid",
        still,
    )

    # hidden by the hub: nothing runs; shown: the queue poll is back
    await p.js(hub(False))
    c = await counts(p, 10)
    check(
        "hidden by the hub, 10 s without work",
        c == {"fetch": 0, "raf": 0, "timer": 0},
        c,
    )
    await p.js(hub(True))
    await asyncio.sleep(4)
    check(
        "shown again, the queue poll comes back", await p.js(calls("/api/state")) >= 1
    )

    # a looping silent preview pauses while hidden and plays when shown
    await p.js(
        inner("(w.applyMode('advanced', {save: false}), w.selectTab('scenery'), 1)")
    )
    await asyncio.sleep(1.5)
    await p.js(
        inner(
            "(() => { const v = d.getElementById('scPreviewVid'); v.muted = true; v.loop = true;"
            f" v.src = '/api/projects/{slug}/render-file?name=loop.mp4'; v.hidden = false;"
            " v.play(); return 1; })()"
        )
    )
    playing = await p.wait(
        inner(
            "!d.getElementById('scPreviewVid').paused && d.getElementById('scPreviewVid').currentTime > 0"
        ),
        10,
    )
    await p.js(hub(False))
    await asyncio.sleep(0.5)
    hid = await p.js(inner("d.getElementById('scPreviewVid').paused"))
    await p.js(hub(True))
    await asyncio.sleep(0.8)
    back = await p.js(inner("d.getElementById('scPreviewVid').paused"))
    check(
        "looping preview pauses while hidden, plays when shown",
        (playing, hid, back) == (True, True, False),
        (playing, hid, back),
    )

    # one press, one request
    await p.js(inner("(w.selectTab('compose'), 1)"))
    await p.js(RESET)
    await p.js(
        inner(
            "(() => { const b = d.getElementById('renderBtn'); b.click(); b.click(); b.click(); return 1; })()"
        )
    )
    await asyncio.sleep(2.5)
    check(
        "triple click on Render sends one request",
        await p.js(calls("/render", "POST")) == 1,
        await p.js(calls("/render", "POST")),
    )
    await p.js(
        inner(
            "(w.selectTab('projects'), d.getElementById('newName').value = 'Double', 1)"
        )
    )
    await p.js(RESET)
    await p.js(
        inner(
            "(() => { const b = d.getElementById('createBtn'); b.click(); b.click(); return 1; })()"
        )
    )
    await asyncio.sleep(2.5)
    check(
        "double click on Create makes one project",
        await p.js(calls("/api/projects", "POST")) == 1,
        await p.js(f"JSON.stringify({F}.__urls)"),
    )
    await p.js(
        inner(f"(w.applyMode('simple', {{save: false}}), w.openProject('{slug}'), 1)")
    )
    await asyncio.sleep(1.5)
    await p.js(RESET)
    # Make waits for a song and a picture; enable it as a ready project would
    await p.js(
        inner(
            "(() => { const b = d.getElementById('smMake'); b.disabled = false; b.click(); b.click(); return 1; })()"
        )
    )
    await asyncio.sleep(2.5)
    check(
        "double click on Make sends one request",
        await p.js(calls("/render", "POST")) == 1,
        await p.js(calls("/render", "POST")),
    )

    # server down: the queue poll asks less and less often and says why
    srv.stop()
    first = await counts(p, 10)
    second = await counts(p, 20)
    line = await p.js(inner("d.getElementById('queueLine').textContent"))
    check(
        "server down: queue poll backs off (asks 10-30 s <= first 10 s, <= 3)",
        second["fetch"] <= max(first["fetch"], 1) and second["fetch"] <= 3,
        (first, second),
    )
    check("server down: the queue line says so", "can't reach" in (line or ""), line)
    srv.start()
    ok = await p.wait(
        inner("d.getElementById('queueLine').textContent === 'Queue: idle'"), 40
    )
    check("server back: the page recovers by itself", ok)

    # a start that cannot reach the server: a calm card, then it recovers
    card = await frame(
        p,
        port,
        "/?u1block=/api/scenes",
        "d.getElementById('projList').innerText.includes(\"Can't reach\")",
    )
    check(
        "start without the server: calm card",
        card,
        await p.js(inner("d.getElementById('projList').innerText")),
    )
    await p.js(f"{F}.__blockOn = false, 1")
    check(
        "start without the server: recovers by itself", await p.wait(inner(READY), 10)
    )

    errors = await p.js(f"JSON.stringify({F}.__e)")
    check("no script errors or unhandled rejections", errors == "[]", errors)


async def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9051
    box = Path("/tmp/u1/G15/check")
    shutil.rmtree(box, ignore_errors=True)
    (box / "home").mkdir(parents=True)
    srv = Server(port, box / "home")
    srv.start()
    try:
        async with chrome_page(box, size="1300,900") as p:
            await run(p, srv)
    finally:
        srv.stop()
        reap(box)
    print("\n".join(results))
    return 1 if any(r.startswith("FAIL") for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
