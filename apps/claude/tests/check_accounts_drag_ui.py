"""The account box in the classic sidebar resizes by dragging its top edge.

Not a pytest file (it needs Flatpak Chrome and `websockets`); run it with a
venv that has websockets, from the app folder:

    ../files/.venv/bin/python tests/check_accounts_drag_ui.py [shot.png]

Real mouse events through CDP drag #split-accounts: up makes the box taller,
down makes it shorter, the height survives a reload, folding still shrinks it
to its header, a double-click goes back to the default size, and the
Web logins list folds away on its own and stays folded. Uses a
scratch data folder and the fake Claude, like check_enjoy_ui.py.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "tests"))
sys.path.insert(0, str(APP.parents[1] / "tests"))
from cdp_driver import chrome_page  # noqa: E402
from check_enjoy_ui import start, stop  # noqa: E402

KEY = "forge.claude.height.accounts"
HEIGHT = (
    "Math.round(document.getElementById('accounts').getBoundingClientRect().height)"
)
BAR = """(() => { const r = document.getElementById('split-accounts').getBoundingClientRect();
  return [Math.round(r.x + r.width / 2), Math.round(r.y + r.height / 2)].join(','); })()"""


async def booted(page) -> None:
    """The dividers are set up at the very end of boot, after the account checks."""
    if not await page.wait("typeof state !== 'undefined' && state.booted", 30):
        raise RuntimeError("the page did not finish booting")


async def drag(page, dy: int) -> None:
    x, y = (int(v) for v in (await page.js(BAR)).split(","))
    mouse = "Input.dispatchMouseEvent"
    await page.call(mouse, type="mousePressed", x=x, y=y, button="left", clickCount=1)
    for step in range(1, 6):
        await page.call(
            mouse, type="mouseMoved", x=x, y=y + dy * step // 5, button="left"
        )
    await page.call(
        mouse, type="mouseReleased", x=x, y=y + dy, button="left", clickCount=1
    )
    await asyncio.sleep(0.2)


async def run(port: int, sandbox: Path, shot: Path | None) -> list[str]:
    fails: list[str] = []

    def check(what: str, ok: bool, got: object) -> None:
        print(("ok   " if ok else "FAIL ") + what, got)
        if not ok:
            fails.append(what)

    async with chrome_page(sandbox, "1500,950") as page:
        url = f"http://127.0.0.1:{port}/index.html"
        await page.go(url)
        await page.js("try{localStorage.removeItem('claude.layout')}catch(e){};1")
        await page.go(url)
        await booted(page)
        h0 = await page.js(HEIGHT)
        await drag(page, -150)
        h1 = await page.js(HEIGHT)
        check("drag up makes it taller", h1 >= h0 + 140, (h0, h1))
        await drag(page, 250)
        h2 = await page.js(HEIGHT)
        check("drag down makes it shorter", h2 <= h1 - 240 or h2 <= 60, (h1, h2))
        saved = await page.js(f"localStorage.getItem('{KEY}')")
        check("height remembered", saved == str(h2), saved)
        await page.go(url)
        await booted(page)
        h3 = await page.js(HEIGHT)
        check("height kept after reload", abs(h3 - h2) <= 1, (h2, h3))
        await drag(page, -200)
        tall = await page.js(HEIGHT)
        await page.js("document.getElementById('fold-accounts').click(); 1")
        folded = await page.js(HEIGHT)
        check("fold still shrinks to the header", folded < 50, (tall, folded))
        await page.js("document.getElementById('fold-accounts').click(); 1")
        back = await page.js(HEIGHT)
        check("unfold brings the dragged size back", abs(back - tall) <= 1, back)
        web = "document.getElementById('web-account-list').offsetParent === null"
        await page.js("document.getElementById('fold-web').click(); 1")
        check("Web logins fold away", await page.js(web) is True, "")
        await page.go(url)
        await booted(page)
        check("Web logins stay folded after reload", await page.js(web) is True, "")
        if shot:
            await page.screenshot(shot)
        await page.js("document.getElementById('fold-web').click(); 1")
        check("Web logins open again", await page.js(web) is False, "")
        await page.js(
            "document.getElementById('split-accounts')"
            ".dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); 1"
        )
        await asyncio.sleep(0.2)
        # back to its natural size, which follows what the account list shows by now
        fixed = await page.js("document.getElementById('accounts').style.height")
        gone = await page.js(f"localStorage.getItem('{KEY}')")
        check("double-click resets", fixed == "" and gone is None, (fixed, gone))
    return fails


def main() -> int:
    shot = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    sandbox = Path(tempfile.mkdtemp(prefix="claude-accounts-"))
    try:
        env = {
            "FORGE_CLAUDE_DATA": str(sandbox / "data"),
            "FORGE_CLAUDE_BIN": f"{sys.executable} {APP / 'tests/fake_claude.py'}",
            "FORGE_SHARED_DIR": str(APP.parents[1] / "shared"),
        }
        proc, port = start(env)
        try:
            fails = asyncio.run(run(port, sandbox, shot))
        finally:
            stop(proc)
        print("all passed" if not fails else f"{len(fails)} failed")
        return 1 if fails else 0
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
