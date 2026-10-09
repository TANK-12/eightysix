"""Drive Cosmos in headless Chrome, framed the way the Forge hub frames it, and
check the U1 sweep behaviour:

- hidden by the hub: the menu, map, sandbox and puzzles each go 10 s without
  a fetch, an animation frame or a timer, and draw again when shown;
- the menu sky draws about every other screen refresh (30 a second);
- the puzzles' sound device sleeps while hidden and wakes when shown;
- the menu, opened while the server does not answer (or answers with an
  error, which it names), says so calmly, tries
  again less and less often, never while hidden, and fills in by itself;
- a puzzle result sent while the server does not answer is kept and lands
  by itself once it answers again;
- the sandbox saves once for a double click;
- on every screen, wide and at 760 px, no control sits under the hub's
  Full screen or Close app buttons;
- no page errors.

    .venv/bin/python tests/check_ui.py

Not collected by pytest (it needs the Flatpak Chrome). Runs the app on a free
port with a temp HOME holding copies of the levels, presets, sounds and star
catalog; never the real saves. "Not answering" is made by the page's own
fetch refusing /api/... (the ?u1block= switch below), so the page stays
loaded. Prints PASS/FAIL lines, exits non-zero on a FAIL.
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


# Counters for fetch, animation frames and timers; a list of the sound
# devices made; and ?u1block=<word>: fetches to /api/ URLs holding that word
# fail as if the server were down, until __blockOn is set false; and
# ?u1refuse=<word>: they answer 500 {"detail": "boom"}.
COUNTERS = r"""
window.__c = {fetch: 0, raf: 0, timer: 0, draw: 0}; window.__urls = []; window.__e = [];
window.__actx = []; window.__blockOn = true;
addEventListener('error', (e) => __e.push(e.message));
addEventListener('unhandledrejection', (e) => __e.push(String(e.reason)));
{ const of = window.fetch, or = window.requestAnimationFrame,
        ot = window.setTimeout, oi = window.setInterval;
  window.fetch = function (...a) {
    // read per call: an iframe's first blank document shares this window
    const block = new URLSearchParams(location.search).get('u1block');
    __c.fetch++; __urls.push(((a[1] && a[1].method) || 'GET') + ' ' + a[0]);
    if (block && __blockOn && String(a[0]).includes('/api/') && String(a[0]).includes(block))
      return Promise.reject(new TypeError('Failed to fetch'));
    const refuse = new URLSearchParams(location.search).get('u1refuse');
    if (refuse && String(a[0]).includes('/api/') && String(a[0]).includes(refuse))
      return Promise.resolve(new Response('{"detail": "boom"}', {status: 500}));
    return of.apply(this, a);
  };
  window.requestAnimationFrame = (cb) => or.call(window, (t) => { __c.raf++; cb(t); });
  window.setTimeout = (cb, ms, ...r) => ot.call(window, typeof cb === 'function' ? (...x) => { __c.timer++; cb(...x); } : cb, ms, ...r);
  window.setInterval = (cb, ms, ...r) => oi.call(window, (...x) => { __c.timer++; cb(...x); }, ms, ...r);
  const oc = CanvasRenderingContext2D.prototype.clearRect;
  CanvasRenderingContext2D.prototype.clearRect = function (...a) { __c.draw++; return oc.apply(this, a); };
  const AC = window.AudioContext;
  if (AC) window.AudioContext = class extends AC { constructor(...a) { super(...a); __actx.push(this); } };
}
"""
F = "document.getElementById('f').contentWindow"
RESET = f"(() => {{ const w = {F}; Object.keys(w.__c).forEach((k) => (w.__c[k] = 0)); w.__urls.length = 0; return 1; }})()"


def hub(visible: bool) -> str:
    return f"{F}.postMessage({{forge: 'visible', visible: {str(visible).lower()}}}, '*'), 1"


def inner(expr: str) -> str:
    return f"(() => {{ const w = {F}, d = w.document; return ({expr}); }})()"


async def frame(p: Page, port: int, path: str, ready: str) -> bool:
    await p.go(f"http://127.0.0.1:{port}/no-such-page")
    await p.js(
        "document.body.innerHTML = '<iframe id=f src=\""
        + path
        + '" style="position:fixed;inset:0;width:100vw;height:100vh;border:0"></iframe>\'; 1'
    )
    return await p.wait(inner(ready), 20)


async def counts(p: Page, seconds: float) -> dict:
    await asyncio.sleep(0.3)  # the one frame already asked for before a change
    await p.js(RESET)
    await asyncio.sleep(seconds)
    return json.loads(await p.js(f"JSON.stringify({F}.__c)"))


def calls(word: str) -> str:
    return inner(f"w.__urls.filter((u) => u.includes({json.dumps(word)})).length")


SCREENS = [
    ("menu", "/", "d.querySelectorAll('.mode-card').length > 0"),
    (
        "map",
        "/#map",
        "!!d.querySelector('.map-clock') && !!d.querySelector('.map-clock').textContent",
    ),
    (
        "sandbox",
        "/#sandbox",
        "!!d.querySelector('.sb-stats') && !!d.querySelector('.sb-stats').textContent",
    ),
    (
        "puzzles",
        "/#puzzles",
        "!!d.querySelector('.pz-select') && !d.querySelector('.pz-select').hidden",
    ),
]


async def run(p: Page, port: int, home: Path) -> None:
    # every screen rests while the hub hides it
    for name, path, ready in SCREENS:
        if not await frame(p, port, path, ready):
            check(f"{name}: opens", False)
            continue
        await asyncio.sleep(
            5
        )  # past one-shot hints (the sandbox tool tip fades at 4 s)
        await p.js(hub(False))
        c = await counts(p, 10)
        check(
            f"{name}: hidden by the hub, 10 s without work",
            c["raf"] == 0 and c["fetch"] == 0 and c["timer"] == 0,
            c,
        )
        await p.js(hub(True))
        c = await counts(p, 2)
        check(f"{name}: shown again, it draws", c["raf"] > 20, c)
        if name == "menu":
            check(
                "menu: the sky draws about every other frame",
                0 < c["draw"] <= c["raf"] * 0.62,
                c,
            )
        errs = await p.js(inner("JSON.stringify(w.__e)"))
        check(f"{name}: no page errors", errs == "[]", errs)

    # the puzzles' sound device sleeps while hidden
    if await frame(
        p,
        port,
        "/?pz=01-first-light#puzzles",
        "!!d.querySelector('.pz-aim') && !d.querySelector('.pz-aim').hidden",
    ):
        await p.js(inner("d.querySelector('.pz-caption').click(), 1"))
        await p.wait(inner("w.__actx.length && w.__actx[0].state === 'running'"), 5)
        state = lambda: p.js(
            inner("w.__actx.length ? w.__actx[0].state : 'none'")
        )  # noqa: E731
        before = await state()
        await p.js(hub(False))
        await asyncio.sleep(0.6)
        hidden = await state()
        await p.js(hub(True))
        await asyncio.sleep(0.6)
        check(
            "puzzles: sound sleeps while hidden, wakes when shown",
            (before, hidden, await state()) == ("running", "suspended", "running"),
            (before, hidden),
        )

    # the menu waits calmly for a server that does not answer, and recovers
    await frame(p, port, "/?u1block=modes", "!!d.querySelector('.menu-wait')")
    note = await p.js(inner("(d.querySelector('.menu-wait') || {}).textContent || ''"))
    check("menu, server not answering: a calm note", "not answering" in note, note)
    await p.js(RESET)
    await asyncio.sleep(10)
    first = await p.js(calls("/api/modes"))
    await asyncio.sleep(20)
    later = await p.js(calls("/api/modes")) - first
    check(
        "menu, server not answering: tries back off (0-10 s vs 10-30 s)",
        2 <= first <= 4 and later <= 2,
        (first, later),
    )
    await p.js(hub(False))
    await asyncio.sleep(0.3)
    await p.js(RESET)
    await asyncio.sleep(15)
    check(
        "menu, not answering and hidden: no tries for 15 s",
        await p.js(calls("/api/modes")) == 0,
    )
    await p.js(inner("(w.__blockOn = false, 1)"))
    await p.js(hub(True))
    check(
        "menu: fills in by itself once the server answers",
        await p.wait(inner("d.querySelectorAll('.mode-card').length === 3"), 5),
    )
    await frame(p, port, "/?u1refuse=modes", "!!d.querySelector('.menu-wait')")
    note = await p.js(inner("d.querySelector('.menu-wait').textContent"))
    check(
        "menu, server answers with an error: says what it was", "(boom)" in note, note
    )

    # a puzzle result sent while the server does not answer lands later
    progress = home / "ForgeGameData/cosmos/puzzle-progress.json"
    plays = lambda: (
        json.loads(progress.read_text())["levels"]
        .get("01-first-light", {})
        .get("plays", 0)
        if progress.is_file()
        else 0
    )  # noqa: E731
    start = plays()
    ok = await frame(
        p,
        port,
        "/?u1block=progress&pz=01-first-light&pzwarp=8&pzfire=1#puzzles",
        "w.document.querySelector('.puzzles').__debug.state.phase === 'ended'",
    )
    check("puzzles: the reference flight ends", ok)
    if ok:
        toast = await p.wait(
            inner(
                "(d.getElementById('toast').textContent || '').includes('not answering')"
            ),
            3,
        )
        check("puzzles, server not answering: a calm toast", toast)
        await asyncio.sleep(7)
        tries = await p.js(calls("/api/puzzles/progress"))
        check(
            "puzzles, server not answering: a few tries, not a storm",
            2 <= tries <= 4,
            tries,
        )
        check("puzzles: nothing saved while not answering", plays() == start, plays())
        await p.js(inner("(w.__blockOn = false, 1)"))
        landed = False
        for _ in range(140):
            if plays() == start + 1:
                landed = True
                break
            await asyncio.sleep(0.25)
        check(
            "puzzles: the result lands by itself once the server answers",
            landed,
            plays(),
        )
        await asyncio.sleep(8)
        check(
            "puzzles: saved once, then the tries stop",
            plays() == start + 1
            and await p.js(calls("/api/puzzles/progress")) == tries + 1,
            plays(),
        )

    # the sandbox saves once for a double click
    if await frame(p, port, "/#sandbox", SCREENS[2][2]):
        await p.js(inner("(d.querySelector('.save-name').value = 'u1 check', 1)"))
        await p.js(RESET)
        await p.js(
            inner(
                "(d.querySelector('[data-act=save]').click(), d.querySelector('[data-act=save]').click(), 1)"
            )
        )
        await asyncio.sleep(1.5)
        posts = await p.js(
            inner("w.__urls.filter((u) => u.startsWith('POST /api/scenarios')).length")
        )
        saved = len(
            list((home / "ForgeGameData/cosmos/scenarios").glob("u1-check*.json"))
        )
        check(
            "sandbox: a double click saves once",
            posts == 1 and saved == 1,
            (posts, saved),
        )

    errs = await p.js(inner("JSON.stringify(w.__e)"))
    check("no page errors", errs == "[]", errs)


async def layout(p: Page, port: int, width: int) -> None:
    # nothing the player uses sits under the hub's Full screen or Close app
    # buttons, on any screen, wide or at 760 px
    clear = (
        "(() => { const chrome = ['go-fullscreen', 'forge-close-app']"
        ".map((id) => d.getElementById(id)).filter((e) => e && e.getClientRects().length);"
        " const seen = (e) => { let r = e.getBoundingClientRect(), x = {left: r.left, right: r.right, top: r.top, bottom: r.bottom};"
        " for (let p = e.parentElement; p; p = p.parentElement) { const st = w.getComputedStyle(p);"
        " if (st.overflow === 'visible' && st.overflowX === 'visible' && st.overflowY === 'visible') continue;"
        " const q = p.getBoundingClientRect(); x = {left: Math.max(x.left, q.left), right: Math.min(x.right, q.right), top: Math.max(x.top, q.top), bottom: Math.min(x.bottom, q.bottom)}; }"
        " return x; };"
        " const hit = (a, b) => !(b.right <= a.left || b.left >= a.right || b.bottom <= a.top || b.top >= a.bottom);"
        " const bad = [...d.querySelectorAll('button, input, select, label, a, .btn')]"
        ".filter((e) => e.getClientRects().length && w.getComputedStyle(e).visibility !== 'hidden' && !chrome.some((c) => c === e || c.contains(e)))"
        ".filter((e) => chrome.some((c) => hit(c.getBoundingClientRect(), seen(e))))"
        ".map((e) => (e.textContent || e.className).trim().slice(0, 20));"
        " if (chrome.length === 2 && hit(chrome[0].getBoundingClientRect(), chrome[1].getBoundingClientRect())) bad.push('chrome overlap');"
        " return [chrome.length, ...bad]; })()"
    )
    level = (
        "level",
        "/?pz=04-slingshot#puzzles",
        "!!d.querySelector('.pz-aim') && !d.querySelector('.pz-aim').hidden",
    )
    await p.call(
        "Emulation.setDeviceMetricsOverride",
        width=width,
        height=900,
        deviceScaleFactor=1,
        mobile=False,
    )
    for name, path, ready in [*SCREENS, level]:
        if not await frame(p, port, path, ready):
            check(f"{width} px {name}: opens", False)
            continue
        await asyncio.sleep(0.5)
        got = await p.js(inner(clear))
        check(
            f"{width} px {name}: controls clear Full screen and Close app",
            got == [2],
            got,
        )
    errs = await p.js(inner("JSON.stringify(w.__e)"))
    check(f"{width} px: no page errors", errs == "[]", errs)


async def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="cosmos-check-"))
    home = tmp / "home"
    real = Path.home()
    for src, dst in [
        ("ForgeGameData/cosmos/levels", "ForgeGameData/cosmos/levels"),
        ("ForgeGameData/cosmos/scenarios", "ForgeGameData/cosmos/scenarios"),
        (".cache/forge/cosmos", ".cache/forge/cosmos"),
    ]:
        if (real / src).is_dir():
            shutil.copytree(real / src, home / dst)
    (home / "ForgeGameData/sounds").mkdir(parents=True, exist_ok=True)
    for f in (real / "ForgeGameData/sounds").glob("cosmos-*.json"):
        shutil.copy(f, home / "ForgeGameData/sounds")
    port = free_port()
    proc = subprocess.Popen(
        [
            str(APP / ".venv/bin/python"),
            "-m",
            "uvicorn",
            "web_app:app",
            "--port",
            str(port),
        ],
        cwd=APP,
        env={
            **os.environ,
            "HOME": str(home),
            "FORGE_SHARED_DIR": str(APP.parents[1] / "shared"),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_http(f"http://127.0.0.1:{port}/")
        args = (
            "--enable-unsafe-swiftshader",
            "--autoplay-policy=no-user-gesture-required",
        )
        async with chrome_page(tmp, size="1500,900", extra_args=args) as p:
            await p.call("Page.addScriptToEvaluateOnNewDocument", source=COUNTERS)
            await run(p, port, home)
        # the layout pass in a fresh browser per width: one long-lived
        # software-WebGL browser is the first thing to go when memory is short
        for width in (1500, 760):
            async with chrome_page(tmp, size="1500,900", extra_args=args) as p:
                await p.call("Page.addScriptToEvaluateOnNewDocument", source=COUNTERS)
                await layout(p, port, width)
    finally:
        proc.terminate()
        proc.wait(10)
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n".join(results))
    return 1 if any(r.startswith("FAIL") for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
