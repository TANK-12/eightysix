"""The Normal / Ultracode switch, the agent limits fold and the avatar at
page load, in real headless Chrome, in both layouts (2026-10-07).

Not a pytest file (it needs Flatpak Chrome and `websockets`); from the app
folder:

    ../files/.venv/bin/python tests/check_run_controls_ui.py [shots folder]

Scratch data folder and the fake Claude, like check_enjoy_ui.py. The saved
persona prefs say avatar: true, and the classic page must still load without
the animated avatar; 🎭 turns it on until a reload.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "tests"))
sys.path.insert(0, str(APP.parents[1] / "tests"))
from cdp_driver import chrome_page  # noqa: E402
from check_enjoy_ui import call, start, stop  # noqa: E402

ON = "!!document.querySelector('#stage-view .stage-off')"


async def run(port: int, sandbox: Path, shots: Path) -> list[str]:
    fails: list[str] = []

    def check(ok, what: str) -> None:
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    call(port, "/api/personas/prefs", {"avatar": True})
    cid = call(port, "/api/conversations", {"cwd": str(sandbox)})["id"]
    call(port, f"/api/conversations/{cid}/settings", {"title": "ultracode check"})
    base = f"http://127.0.0.1:{port}"
    meta = lambda: call(port, f"/api/conversations/{cid}/events?after=999999")["meta"]
    async with chrome_page(sandbox, "1500,950") as page:
        await page.go(f"{base}/index.html")
        await page.js("try{localStorage.removeItem('claude.layout')}catch(e){};1")
        await page.go(f"{base}/index.html")
        if not await page.wait(
            "document.querySelectorAll('.chat-item').length > 0", 10
        ):
            print(
                await page.js(
                    "location.href + ' ' + document.body.innerText.slice(0, 600)"
                )
            )
        await page.js("document.querySelector('.chat-item').click(); 1")
        await page.wait("!!document.querySelector('#run-host .run-seg')", 5)
        await asyncio.sleep(0.8)
        check(await page.js(ON), "classic: avatar off at load though prefs say on")
        check(
            await page.js(
                "typeof PIXI === 'undefined' && !document.querySelector('#stage-view canvas')"
            ),
            "classic: no Live2D canvas or pixi loaded",
        )
        await page.js("document.querySelector('#stage-avatar').click(); 1")
        await asyncio.sleep(0.5)
        check(not await page.js(ON), "classic: 🎭 turns the avatar on")
        prefs = call(port, "/api/personas")["prefs"]
        check(prefs.get("avatar") is True, "saved prefs untouched by 🎭")
        await page.js("document.querySelector('#stage-avatar').click(); 1")
        await asyncio.sleep(0.4)
        check(await page.js(ON), "classic: 🎭 again turns it off")

        await page.js(
            "[...document.querySelectorAll('#run-host .run-seg button')][1].click(); 1"
        )
        await asyncio.sleep(0.6)
        check(meta().get("ultracode") is True, "classic: Ultracode click saves")
        check(
            await page.js("document.querySelector('#run-host .run-note').textContent")
            == "from the next message",
            "classic: says it applies from the next message",
        )
        await page.js("document.querySelector('#run-host details').open = true; 1")
        await page.js(
            "const n=document.querySelector('#run-max_helpers'); n.value='4';"
            "n.dispatchEvent(new Event('change')); 1"
        )
        await asyncio.sleep(0.6)
        check(
            meta().get("limits") == {"max_helpers": 4},
            "classic: number field saves a limit",
        )
        await page.js(
            "const s=document.querySelector('#run-host select'); s.value='haiku';"
            "s.dispatchEvent(new Event('change')); 1"
        )
        await asyncio.sleep(0.6)
        check(
            meta()["limits"].get("helper_model") == "haiku",
            "classic: helper model saves",
        )
        check(
            await page.js("document.querySelector('#run-host summary').textContent")
            == "Limits · 2",
            "classic: the fold counts the limits set",
        )
        await page.screenshot(shots / "run_controls_classic.png")
        await page.js("document.querySelector('#log').click(); 1")
        await page.js(
            "document.body.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true})); 1"
        )
        check(
            not await page.js("document.querySelector('#run-host details').open"),
            "classic: click outside closes the fold",
        )
        await page.js(
            "const m=document.querySelector('#model'); m.value='haiku';"
            "m.dispatchEvent(new Event('change')); 1"
        )
        await asyncio.sleep(0.6)
        check(
            await page.js("document.querySelector('#run-host .run-note').textContent")
            == "this model has no ultracode",
            "classic: haiku + ultracode warns",
        )
        await page.js(
            "[...document.querySelectorAll('#run-host .run-seg button')][0].click(); 1"
        )
        await asyncio.sleep(0.6)
        check(
            await page.js(
                "[...document.querySelectorAll('#run-host .run-seg button')][1].disabled"
            ),
            "classic: Ultracode greyed out on haiku once off",
        )
        await page.go(f"{base}/index.html")
        await asyncio.sleep(1.5)
        check(await page.js(ON), "classic: avatar off again after a reload")

        await page.go(f"{base}/enjoy.html#task/{cid}")
        await page.wait("!!document.querySelector('#e-t-run .run-seg')", 8)
        await asyncio.sleep(1.0)
        check(
            await page.js("document.querySelector('#e-t-run summary').textContent")
            == "Limits · 2",
            "enjoy: the same limits show",
        )
        await page.js(
            "[...document.querySelectorAll('#e-t-run .run-seg button')][1].click(); 1"
        )
        await asyncio.sleep(0.6)
        check(
            meta().get("ultracode") is False,
            "enjoy: Ultracode stays off on haiku (button disabled)",
        )
        await page.js(
            "const m=document.querySelector('#e-t-model'); m.value='opus';"
            "m.dispatchEvent(new Event('change')); 1"
        )
        await asyncio.sleep(0.8)
        await page.js(
            "[...document.querySelectorAll('#e-t-run .run-seg button')][1].click(); 1"
        )
        await asyncio.sleep(0.6)
        check(meta().get("ultracode") is True, "enjoy: Ultracode click saves on opus")
        await page.js("document.querySelector('#e-t-run details').open = true; 1")
        await asyncio.sleep(0.3)
        await page.screenshot(shots / "run_controls_enjoy.png")
    async with chrome_page(sandbox, "760,820") as page:
        await page.go(f"{base}/index.html")
        await page.wait("document.querySelectorAll('.chat-item').length > 0", 8)
        await page.js("document.querySelector('.chat-item').click(); 1")
        await asyncio.sleep(1.0)
        await page.js("document.querySelector('#run-host details').open = true; 1")
        await asyncio.sleep(0.3)
        box = json.loads(
            await page.js(
                "JSON.stringify(document.querySelector('#run-host .run-panel').getBoundingClientRect())"
            )
        )
        check(
            box["right"] <= 762 and box["left"] >= -1,
            f"narrow: limits panel inside the window {box['left']:.0f}-{box['right']:.0f}",
        )
        await page.screenshot(shots / "run_controls_narrow.png")
    return fails


def main() -> int:
    shots = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(tempfile.mkdtemp(prefix="run-shots-"))
    )
    shots.mkdir(parents=True, exist_ok=True)
    sandbox = Path(tempfile.mkdtemp(prefix="claude-run-"))
    try:
        env = {
            "FORGE_CLAUDE_DATA": str(sandbox / "data"),
            "FORGE_CLAUDE_BIN": f"{sys.executable} {APP / 'tests/fake_claude.py'}",
            "FORGE_SHARED_DIR": str(APP.parents[1] / "shared"),
        }
        proc, port = start(env)
        try:
            fails = asyncio.run(run(port, sandbox, shots))
        finally:
            stop(proc)
        print("shots in", shots)
        print("all passed" if not fails else f"{len(fails)} failed")
        return 1 if fails else 0
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
