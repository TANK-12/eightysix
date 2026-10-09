"""Drive the real Compose tab in headless Chrome: the scene picker offers the
Spectrum Tunnel and Harmonograph Scope visualisers, and a frame scene's form
offers the particle effect and its amount.

    .venv/bin/python tests/check_scene_picker.py

Not collected by pytest (it needs the Flatpak Chrome). It starts its own
backend on a free port with HOME pointed at a sandbox folder, so the project
it creates never lands in the real ~/PulseForgeData. Prints PASS/FAIL lines,
saves a screenshot to ~/.cache/pulseforge-scene-picker.png and exits non-zero on any FAIL.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))
from cdp_driver import Page, chrome_page, reap, serve  # noqa: E402

results: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    results.append(
        f"{'PASS' if ok else 'FAIL'} :: {name}{' :: ' + extra if extra and not ok else ''}"
    )


def new_project(port: int) -> str:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/projects",
        data=json.dumps({"name": "picker check"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req))["slug"]


async def run(p: Page, port: int, shot: Path) -> None:
    slug = new_project(port)
    await p.go(f"http://127.0.0.1:{port}/")
    await p.wait("document.body.dataset.ready === '1'", 15)
    await p.js("document.querySelector('[data-mode=advanced]').click()")
    await p.js(f"location.hash = '#/{slug}/compose'")
    await p.wait("document.querySelectorAll('#sceneGrid .scene').length > 5", 10)
    # the Scene section is a folded <details>; open it so it can be read and seen
    await p.js("document.getElementById('sceneGrid').closest('details').open = true")
    labels = await p.js(
        "[...document.querySelectorAll('#sceneGrid .scene h4')].map(h => h.textContent)"
    )
    for want in ("Spectrum Tunnel", "Harmonograph Scope"):
        check(f"scene picker offers {want}", want in (labels or []), str(labels))

    # pick drift, the scene Emerson rated good, and look for the particle controls
    await p.js(
        "[...document.querySelectorAll('#sceneGrid .scene')]"
        ".find(e => e.querySelector('h4').textContent === 'Drifting Scenery').click()"
    )
    await p.wait("document.querySelector('#sceneGrid .scene.sel h4')", 5)
    form = await p.js("document.getElementById('sceneParams').innerText")
    check("drift's form shows the particle effect", "Particle" in (form or ""), form)
    options = await p.js(
        "[...document.querySelectorAll('#sceneParams select')]"
        ".map(s => [...s.options].map(o => o.value))"
        ".find(o => o.includes('embers')) || []"
    )
    for preset in ("none", "embers", "snow", "sparks", "dust", "petals"):
        check(f"particle list offers {preset}", preset in options, str(options))
    await p.js("document.getElementById('sceneParams').scrollIntoView({block: 'end'})")
    await p.screenshot(shot)


async def main() -> int:
    box = Path.home() / ".cache" / "pulseforge-picker-check"
    shutil.rmtree(box, ignore_errors=True)
    box.mkdir(parents=True)
    shot = Path.home() / ".cache" / "pulseforge-scene-picker.png"
    try:
        with serve(APP, {"HOME": str(box)}) as port:
            async with chrome_page(box, "1400,1100") as p:
                await run(p, port, shot)
    finally:
        reap(box)
        shutil.rmtree(box, ignore_errors=True)
    print("\n".join(results))
    print(f"screenshot: {shot}")
    return 1 if any(r.startswith("FAIL") for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
