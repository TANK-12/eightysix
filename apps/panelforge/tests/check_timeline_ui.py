"""Timeline tab in real headless Chrome with real mouse input.

Not a pytest file (it needs Flatpak Chrome and `websockets`, which this venv
lacks); run it with a venv that has websockets, from the app folder:

    ../files/.venv/bin/python tests/check_timeline_ui.py

It builds a fixture chapter in a temporary data root (never ~/PanelForgeData),
serves the app on a free port, and checks what broke on 2026-09-27: a real
click selects a shot without marking it edited, the Style list carries every
registered style by name, transitions come from the registry, a resize pushes
the later shots along and is saved, and shot thumbnails load.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))
from cdp_driver import (
    chrome_page,
    serve,
)  # noqa: E402

BASE = "/api/chapters/test-series/0001"


def _get(port: int, path: str):
    return json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}{path}"))


def _post(port: int, path: str):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.load(urllib.request.urlopen(req))


async def run(port: int, sandbox: Path) -> list[str]:
    fails: list[str] = []

    def check(ok: bool, what: str) -> None:
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    job = _post(port, BASE + "/timeline/auto")["job_id"]
    for _ in range(150):
        if _get(port, f"/api/jobs/{job}")["state"] in ("done", "error"):
            break
        time.sleep(0.2)
    async with chrome_page(sandbox, "1400,900") as page:

        async def mouse(x, y, kind, buttons=1):
            await page.call(
                "Input.dispatchMouseEvent",
                type=kind,
                x=x,
                y=y,
                button="left",
                buttons=buttons,
                clickCount=1,
            )

        async def rect(sel):
            return json.loads(
                await page.js(
                    f"JSON.stringify(document.querySelector({sel!r}).getBoundingClientRect())"
                )
            )

        await page.go(f"http://127.0.0.1:{port}/")
        await page.wait("window.PF && PF.tabs && PF.tabs.timeline")
        await page.js(
            "window.__errs=[];addEventListener('error',e=>__errs.push(String(e.message)));"
            "PF.setContext('test-series','0001');"
            "document.querySelector('[data-tab=timeline]').click(); 1"
        )
        await page.wait("document.querySelectorAll('#laneShots .tl-block').length")
        await asyncio.sleep(0.5)

        r = await rect("#laneShots .tl-block:nth-child(2)")
        x, y = r["x"] + r["width"] / 2, r["y"] + r["height"] / 2
        await mouse(x, y, "mouseMoved", 0)
        await mouse(x, y, "mousePressed")
        await mouse(x, y, "mouseReleased", 0)
        await asyncio.sleep(0.4)
        head = await page.js("document.querySelector('#tlInspector').innerText")
        check(head.startswith("Shot p0002"), "a real click selects the shot")
        cls = await page.js(
            "document.querySelector('#laneShots .tl-block:nth-child(2)').className"
        )
        check("user-edited" not in cls, "a click does not mark the shot edited")
        styles = json.loads(
            await page.js(
                "JSON.stringify([...document.querySelectorAll('#shStyle option')].map(o=>o.value))"
            )
        )
        check(
            {"depth3d", "puppet25d", "motion"} <= set(styles)
            and "undefined" not in styles,
            f"style list by name: {styles}",
        )
        kinds = json.loads(
            await page.js(
                "JSON.stringify([...document.querySelectorAll('#shTransKind option')].map(o=>o.value))"
            )
        )
        reg = [t["kind"] for t in _get(port, "/api/transitions")["transitions"]]
        check(kinds == reg, f"transition kinds follow the registry: {kinds}")

        r = await rect("#laneShots .tl-block .rh")
        x, y = r["x"] + 3, r["y"] + 10
        await mouse(x, y, "mouseMoved", 0)
        await mouse(x, y, "mousePressed")
        for i in range(1, 9):
            await mouse(x + i * 10, y, "mouseMoved")
        await mouse(x + 80, y, "mouseReleased", 0)
        await asyncio.sleep(1.6)
        lefts = json.loads(
            await page.js(
                "JSON.stringify([...document.querySelectorAll('#laneShots .tl-block')]"
                ".map(b=>[parseFloat(b.style.left),parseFloat(b.style.width)]))"
            )
        )
        check(
            all(abs(a[0] + a[1] - b[0]) < 1 for a, b in zip(lefts, lefts[1:])),
            "a resize pushes the later shots along",
        )
        saved = _get(port, BASE + "/timeline")["shots"]
        check(saved[0]["dur"] > 3 and saved[0]["edited"], "the resize is saved")
        thumb = await page.js(f"fetch('{BASE}/panels/p0001/image').then(r=>r.status)")
        check(thumb == 200, "shot thumbnails load")
        errs = await page.js("JSON.stringify(__errs)")
        check(errs == "[]", f"no page errors: {errs}")
        await page.screenshot(sandbox / "timeline.png")
    return fails


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="pf-tl-"))
    try:
        data = sandbox / "data"
        subprocess.run(
            [
                str(APP / ".venv/bin/python"),
                "-c",
                "import sys; from pathlib import Path;"
                "from panelforge.render.fixture import make_chapter, add_scene_layers;"
                "add_scene_layers(make_chapter(Path(sys.argv[1]), n_panels=4))",
                str(data),
            ],
            cwd=APP,
            check=True,
        )
        with serve(APP, {"PANELFORGE_DATA": str(data)}) as port:
            fails = asyncio.run(run(port, sandbox))
        print(f"{'all passed' if not fails else f'{len(fails)} failed'}")
        return 1 if fails else 0
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
