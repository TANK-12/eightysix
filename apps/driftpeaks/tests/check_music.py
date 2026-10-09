"""Drive the real game page in headless Chrome: the first key press starts the
background music from /api/music, and Settings shows the Music volume slider.

    .venv/bin/python tests/check_music.py

Not collected by pytest (it needs the Flatpak Chrome). The save goes to a
sandbox folder (DRIFTPEAKS_DATA), never the real one. Prints PASS/FAIL lines,
saves a screenshot to ~/.cache/driftpeaks-music.png, exits non-zero on a FAIL.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))
from cdp_driver import Page, chrome_page, reap, serve  # noqa: E402

results: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    results.append(
        f"{'PASS' if ok else 'FAIL'} :: {name}{' :: ' + extra if extra and not ok else ''}"
    )


MUSIC_FETCHED = (
    "performance.getEntriesByType('resource')"
    ".some(e => e.name.includes('/music/') && !e.name.includes('/api/'))"
)


async def run(p: Page, port: int, shot: Path) -> None:
    await p.go(f"http://127.0.0.1:{port}/")
    await p.wait("!document.getElementById('title').hidden", 10)
    check("no music is fetched before a key press", not await p.js(MUSIC_FETCHED))
    await p.key(" ", "Space", 0, 32)
    check("a key press starts the music", await p.wait(MUSIC_FETCHED, 10))
    await p.key("Escape", "Escape", 0, 27)
    await p.js(
        "[...document.querySelectorAll('button')]"
        ".find(b => /settings/i.test(b.textContent)).click()"
    )
    await p.wait("!document.getElementById('settings').hidden", 5)
    text = await p.js("document.getElementById('settings-form').innerText")
    check("Settings shows Music volume", "Music volume" in (text or ""), text)
    check("Settings still shows Sound volume", "Sound volume" in (text or ""), text)
    await p.screenshot(shot)


async def main() -> int:
    box = Path.home() / ".cache" / "driftpeaks-music-check"
    shutil.rmtree(box, ignore_errors=True)
    box.mkdir(parents=True)
    shot = Path.home() / ".cache" / "driftpeaks-music.png"
    try:
        with serve(APP, {"DRIFTPEAKS_DATA": str(box / "save")}) as port:
            async with chrome_page(box, "1280,800") as p:
                await run(p, port, shot)
    finally:
        reap(box)
        shutil.rmtree(box, ignore_errors=True)
    print("\n".join(results))
    print(f"screenshot: {shot}")
    return 1 if any(r.startswith("FAIL") for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
