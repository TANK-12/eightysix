"""PrintForge headless UI check (not part of pytest: it starts Chrome).

    .venv/bin/python tests/check_ui.py [out_dir]

Serves a scratch copy with temp settings, cache and STL folders, then checks:
the page draws only on demand (no frames while nothing moves), the turntable
stops while the hub hides the page and comes back when shown, an empty and a
damaged STL get a calm message, a double click on Save and rescan saves once,
and screenshots at 760, 1100, 1500 and 1920 px land in out_dir.
"""

from __future__ import annotations

import asyncio
import json
import os
import struct
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))

from cdp_driver import chrome_page, serve  # noqa: E402

COUNTERS = r"""
window.__c = {fetch: 0, raf: 0, timer: 0, posts: 0}; window.__e = [];
addEventListener('error', (e) => __e.push(e.message));
addEventListener('unhandledrejection', (e) => __e.push(String(e.reason)));
{ const of = window.fetch, or = window.requestAnimationFrame,
        ot = window.setTimeout, oi = window.setInterval;
  window.fetch = function (...a) {
    __c.fetch++;
    if (a[1] && a[1].method === 'POST' && String(a[0]).includes('settings')) __c.posts++;
    return of.apply(this, a); };
  window.requestAnimationFrame = (cb) => or.call(window, (t) => { __c.raf++; cb(t); });
  window.setTimeout = (cb, ms, ...r) => ot.call(window, typeof cb === 'function' ? (...x) => { __c.timer++; cb(...x); } : cb, ms, ...r);
  window.setInterval = (cb, ms, ...r) => oi.call(window, (...x) => { __c.timer++; cb(...x); }, ms, ...r); }
"""
RESET = "Object.keys(__c).forEach((k) => (__c[k] = 0)), 1"
HUB = "postMessage({forge: 'visible', visible: %s}, '*'), 1"
STATUS = "document.getElementById('status').firstChild.textContent"


def box(x1: float, y1: float, z1: float) -> list:
    v = [(0, 0, 0), (x1, 0, 0), (x1, y1, 0), (0, y1, 0)]
    v += [(0, 0, z1), (x1, 0, z1), (x1, y1, z1), (0, y1, z1)]
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4)]
    f += [(2, 3, 7), (2, 7, 6), (1, 2, 6), (1, 6, 5), (3, 0, 4), (3, 4, 7)]
    return [[v[a], v[b], v[c]] for a, b, c in f]


def write_stl(path: Path, tris: list) -> None:
    out = bytearray(80) + struct.pack("<I", len(tris))
    for t in tris:
        out += struct.pack("<3f", 0, 0, 0)
        for p in t:
            out += struct.pack("<3f", *p)
        out += b"\0\0"
    path.write_bytes(bytes(out))


async def counts(page, seconds: float) -> dict:
    await asyncio.sleep(0.3)  # a frame asked for just before the change
    await page.js(RESET)
    await asyncio.sleep(seconds)
    return json.loads(await page.js("JSON.stringify(__c)"))


async def run(port: int, out: Path, sandbox: Path) -> list[tuple[str, bool]]:
    results = []
    base = f"http://127.0.0.1:{port}/"
    async with chrome_page(
        sandbox / "chrome", size="1500,900", extra_args=("--enable-unsafe-swiftshader",)
    ) as page:
        await page.call("Page.addScriptToEvaluateOnNewDocument", source=COUNTERS)
        await page.go(base + "?open=tower")
        ok = await page.wait(
            "document.getElementById('facts').textContent.includes('Size')", 20
        )
        results.append(("a print opens and its check fills in", ok))
        c = await counts(page, 3)
        results.append(
            (
                f"nothing moving: no frames or fetches in 3 s {c}",
                c["raf"] == 0 and c["fetch"] == 0,
            )
        )
        await page.js("document.getElementById('spin').click(), 1")
        c = await counts(page, 1)
        results.append((f"turntable on: frames run {c}", c["raf"] > 10))
        await page.js(HUB % "false")
        c = await counts(page, 10)
        results.append(
            (
                f"hidden by the hub, turntable on: 10 s without work {c}",
                c["raf"] == 0 and c["fetch"] == 0 and c["timer"] == 0,
            )
        )
        await page.js(HUB % "true")
        c = await counts(page, 1)
        results.append((f"shown again: the turntable carries on {c}", c["raf"] > 10))
        await page.js("document.getElementById('spin').click(), 1")
        c = await counts(page, 2)
        results.append((f"turntable off: frames stop {c}", c["raf"] == 0))

        await page.js(
            "[...document.querySelectorAll('.file')].find((b) => b.textContent.startsWith('empty')).click(), 1"
        )
        ok = await page.wait(STATUS + ".includes('no triangles')", 10)
        results.append(("an empty STL says it has no triangles", ok))
        await page.js(
            "[...document.querySelectorAll('.file')].find((b) => b.textContent.startsWith('junk')).click(), 1"
        )
        ok = await page.wait(
            STATUS
            + ".includes('Could not open') || "
            + STATUS
            + ".includes('no triangles')",
            10,
        )
        results.append(
            ("a damaged STL gets a calm message: " + str(await page.js(STATUS)), ok)
        )

        await page.js(RESET)
        await page.js(
            "(() => { const b = document.getElementById('rootsSave'); b.click(); b.click(); b.click(); return 1; })()"
        )
        await asyncio.sleep(1.5)
        c = json.loads(await page.js("JSON.stringify(__c)"))
        results.append(
            (f"triple click on Save and rescan saves once {c}", c["posts"] == 1)
        )
        await page.js("document.getElementById('light').value = 1.5, 1")
        await page.js(RESET)
        await page.js(
            "(() => { const r = document.getElementById('light'); for (const v of [1.1, 1.2, 1.3, 1.4]) { r.value = v; r.dispatchEvent(new Event('input')); } return 1; })()"
        )
        await asyncio.sleep(1)
        c = json.loads(await page.js("JSON.stringify(__c)"))
        results.append((f"dragging the light slider saves once {c}", c["posts"] == 1))
        errors = json.loads(await page.js("JSON.stringify(__e)"))
        results.append((f"no page errors {errors}", not errors))

    for w in (760, 1100, 1500, 1920):
        async with chrome_page(
            sandbox / f"chrome{w}",
            size=f"{w},900",
            extra_args=("--enable-unsafe-swiftshader",),
        ) as page:
            await page.go(base + "?open=tower")
            await page.wait(
                "document.getElementById('facts').textContent.includes('Size')", 20
            )
            await asyncio.sleep(1)
            await page.screenshot(out / f"printforge_{w}.png")
            wide = await page.js("document.documentElement.scrollWidth <= innerWidth")
            results.append((f"{w} px: no sideways scroll", bool(wide)))
    return results


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="pf-ui-"))
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pf-check-") as tmp:
        t = Path(tmp)
        models = t / "Models" / "demo"
        models.mkdir(parents=True)
        write_stl(models / "tower.stl", box(40, 30, 120))
        (models / "empty.stl").write_bytes(b"")
        (models / "junk.stl").write_text("solid x\nvertex 1 2\nendsolid\n")
        (t / "cfg").mkdir()
        (t / "cfg" / "settings.json").write_text(
            json.dumps({"roots": [str(t / "Models")]})
        )
        env = dict(
            os.environ,
            PRINTFORGE_CONFIG_DIR=str(t / "cfg"),
            PRINTFORGE_CACHE_DIR=str(t / "cache"),
        )
        with serve(APP, env) as port:
            results = asyncio.run(run(port, out, t))
    for name, ok in results:
        print("ok  " if ok else "FAIL", name)
    print("screenshots in", out)
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
