"""Headless browser checks for the page itself (no test surface in pytest).

    .venv/bin/python tests/check_ui.py            # serves a copy on a free port
    .venv/bin/python tests/check_ui.py --port N   # uses a copy already running

Run the served copy against a temporary HOME holding copies of ~/ForgeArtData
and ~/ForgeGameData so no real save is touched; with --port, start that copy
the same way. Prints one line per check and exits 1 if any failed.
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP.parent.parent / "tests"))
from cdp_driver import chrome_page, serve  # noqa: E402

# Counts what the page does: fetches by URL, frames of the game loop (two loops
# show up as the same frame time twice), timers firing, and page errors.
PROBE = """
window.__p = { fetch: [], loopT: [], timers: 0, frames: 0, errors: [] };
const _f = window.fetch;
window.fetch = function (u, o) { __p.fetch.push(String(u)); return _f.apply(this, arguments); };
const _r = window.requestAnimationFrame;
window.requestAnimationFrame = function (cb) {
  return _r.call(window, (t) => { __p.frames++; if (cb.name === 'loop') __p.loopT.push(t); cb(t); });
};
for (const name of ['setTimeout', 'setInterval']) {
  const orig = window[name];
  window[name] = function (cb, ms, ...rest) {
    return orig.call(window, function () { __p.timers++; return cb.apply(this, arguments); }, ms, ...rest);
  };
}
window.__p.suspended = 0;
const _s = AudioContext.prototype.suspend;
AudioContext.prototype.suspend = function () { __p.suspended++; return _s.apply(this, arguments); };
addEventListener('error', (e) => __p.errors.push(String(e.message)));
addEventListener('unhandledrejection', (e) => __p.errors.push('rejection: ' + (e.reason && e.reason.message || e.reason)));
"""

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(("ok   " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))


async def run(port, sandbox):
    base = f"http://127.0.0.1:{port}"
    async with chrome_page(
        sandbox,
        size="1500,900",
        extra_args=("--autoplay-policy=no-user-gesture-required",),
    ) as page:
        await page.call("Page.addScriptToEvaluateOnNewDocument", source=PROBE)
        await page.call("Network.enable")

        # 1. The server not answering at boot: a calm message, then it recovers.
        await page.call("Network.setBlockedURLs", urls=["*/api/content*"])
        await page.go(base + "/")
        shown = await page.wait("/trying again/i.test(document.body.innerText)", 10)
        check("boot failure shows a calm retry message", shown)
        await page.call("Network.setBlockedURLs", urls=[])
        back = await page.wait("!!document.querySelector('#begin')", 12)
        check("boot recovers by itself once the server answers", back)

        # 2. Begin double-clicked: one valley, one loop.
        if not back:
            await page.go(base + "/")
            await page.wait("!!document.querySelector('#begin')", 12)
        await page.js("__p.fetch = []; 1")
        await page.js(
            "const b = document.querySelector('#begin'); b.click(); b.click(); 1"
        )
        await page.wait("S.running", 15)
        await asyncio.sleep(1)
        grown = await page.js(
            "__p.fetch.filter(u => u.includes('/api/world/new')).length"
        )
        check(
            "a double click on Begin grows one valley", grown == 1, f"{grown} requests"
        )
        dup = await page.js(
            "__p.loopT = []; new Promise(r => setTimeout(() => r(__p.loopT.length - new Set(__p.loopT).size), 1000))"
        )
        check("one frame loop after starting", dup == 0, f"{dup} doubled frames")

        # 3. Escape twice inside one frame (pause, resume) must not add a loop.
        for _ in range(3):
            await page.js("pauseScreen(); resume(); 1")
        dup = await page.js(
            "__p.loopT = []; new Promise(r => setTimeout(() => r(__p.loopT.length - new Set(__p.loopT).size), 1000))"
        )
        check(
            "quick pause and resume leaves one loop", dup == 0, f"{dup} doubled frames"
        )

        # 4. Two presses at the cave mouth must not lose the valley.
        seed = await page.js("S.world.seed")
        await page.js("Promise.all([enterWilds(), enterWilds()]).then(() => 1)")
        await page.js("leaveWilds(); 1")
        check(
            "a double press into the wilds keeps the valley",
            await page.js(f"S.world.seed === {seed} && !S.inWilds && !S.valley"),
        )

        # 5. Narrow windows: tutorial, key hint and a full hotbar do not overlap.
        await page.js(
            "while (S.hotbar.length < 9) S.hotbar.push(S.hotbar[0]); drawHotbar(); 1"
        )
        for width in (760, 1100, 1500, 1920):
            await page.call(
                "Emulation.setDeviceMetricsOverride",
                width=width,
                height=900,
                deviceScaleFactor=1,
                mobile=False,
            )
            await asyncio.sleep(0.4)
            hits = await page.js("""(() => {
              const ids = ['#tut', '#hint', '#bar', '#hud'];
              const r = ids.map(i => document.querySelector(i))
                .filter(e => !e.hidden).map(e => [e.id, e.getBoundingClientRect()]);
              const out = [];
              for (let a = 0; a < r.length; a++) for (let b = a + 1; b < r.length; b++) {
                const [n1, p] = r[a], [n2, q] = r[b];
                if (p.left < q.right && q.left < p.right && p.top < q.bottom && q.top < p.bottom)
                  out.push(n1 + '/' + n2);
              }
              return out; })()""")
            check(f"nothing overlaps at {width} px", not hits, ", ".join(hits))
        await page.call("Emulation.clearDeviceMetricsOverride")

        # 6. Hidden by the hub: paused, audio suspended, nothing ticking.
        await page.js("Sound.unlock(); resume(); 1")
        await asyncio.sleep(0.5)
        await page.js("postMessage({forge: 'visible', visible: false}, '*'); 1")
        await asyncio.sleep(0.5)
        await page.js("__p.fetch = []; __p.frames = 0; __p.timers = 0; 1")
        await asyncio.sleep(10)
        quiet = await page.js(
            "[__p.fetch.length, __p.frames, __p.timers, S.running, !document.querySelector('#veil').hidden]"
        )
        check(
            "hidden for 10 s: no fetch, frame or timer, game paused",
            quiet == [0, 0, 0, False, True],
            json.dumps(quiet),
        )
        check(
            "hidden: the audio clock is suspended", await page.js("__p.suspended > 0")
        )
        await page.js("postMessage({forge: 'visible', visible: true}, '*'); 1")

        # 7. Save & leave with the server refusing: stay, and say so.
        await page.call("Network.setBlockedURLs", urls=["*/api/saves/*"])
        await page.js("document.querySelector('#title').click(); 1")
        await asyncio.sleep(1)
        stayed = await page.js(
            "S.world !== null && /Paused/.test(document.querySelector('#card').innerText)"
        )
        said = await page.js("document.querySelector('#toast').textContent")
        check(
            "save & leave stays put when the save fails",
            stayed and "could not save" in said,
            said,
        )
        await page.call("Network.setBlockedURLs", urls=[])
        await page.js("document.querySelector('#title').click(); 1")
        left = await page.wait("!!document.querySelector('#begin')", 5)
        check("save & leave works once the server answers", left)

        # 8. Escape on a death screen does nothing; full permadeath stays dead.
        await page.go(base + "/?seed=4242&rule=character")
        await page.wait("S.running", 15)
        await page.js("die(); 1")
        await page.key("Escape", "Escape", 0, 27)
        await asyncio.sleep(0.3)
        check(
            "escape on the death screen does not carry on playing",
            await page.js(
                "!S.running && /You fell/.test(document.querySelector('#card').innerText)"
            ),
        )
        await page.go(base + "/?seed=4243&rule=full")
        await page.wait("S.running", 15)
        await page.js("autosave(true)")
        # Die the real way, inside a frame: the frame must not draw a closed valley.
        await page.js(
            "const realStep = step; step = function (dt, t) { realStep(dt, t);"
            " if (!window.__died) { window.__died = 1; S.player.hurtT = 0; hurtPlayer(99); } }; 1"
        )
        await asyncio.sleep(0.3)
        died = await page.js("[window.__died === 1, S.world === null, __p.errors]")
        check(
            "dying inside a frame closes the valley cleanly",
            died[:2] == [True, True] and not died[2],
            json.dumps(died)[:300],
        )
        await page.key("Escape", "Escape", 0, 27)
        await asyncio.sleep(0.5)
        await page.go(base + "/")  # page close: beforeunload must not save
        await page.wait("!!document.querySelector('#begin')", 10)
        slots = await page.js(
            "fetch('/api/saves').then(r => r.json()).then(s => s.map(x => x.slot))"
        )
        check(
            "full permadeath stays dead after escape and a reload",
            "valley-4243" not in slots,
            json.dumps(slots),
        )

        errors = await page.js("__p.errors")
        check("no page errors", not errors, "; ".join(errors)[:300])


def main():
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
        with tempfile.TemporaryDirectory() as sandbox:
            asyncio.run(run(port, Path(sandbox)))
    else:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            for name in ("ForgeArtData", "ForgeGameData"):
                src = Path.home() / name
                if src.is_dir():
                    shutil.copytree(src, home / name)
            env = {
                "HOME": str(home),
                "FORGE_SHARED_DIR": str(APP.parent.parent / "shared"),
            }
            with serve(APP, env) as port:
                sandbox = Path(tmp) / "sb"
                sandbox.mkdir()
                asyncio.run(run(port, sandbox))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    os.chdir(APP)
    main()
