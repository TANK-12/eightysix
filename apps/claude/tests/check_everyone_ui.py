"""The classic layout's "everyone" view, dividers and account fold in headless
Chrome, against a scratch data folder and the fake Claude (nothing is spent).
The session list is the laptop's real ~/.claude/sessions, read only.

    ../files/.venv/bin/python tests/check_everyone_ui.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))
from cdp_driver import chrome_page, serve  # noqa: E402

WIDTH = "document.getElementById('list').getBoundingClientRect().width"


async def run(port: int, sandbox: Path) -> list[str]:
    fails: list[str] = []

    def check(ok, what: str) -> None:
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    async with chrome_page(sandbox, "1400,900") as page:
        await page.go(f"http://127.0.0.1:{port}/index.html")
        await page.wait("document.getElementById('to-everyone')", 15)
        await page.js(
            "window.__e=[];addEventListener('error',e=>__e.push(String(e.message)));1"
        )
        await page.wait("window.splitters && document.getElementById('input')", 15)
        await asyncio.sleep(1.5)
        await page.js("document.getElementById('to-everyone').click();1")
        found = await page.wait("document.querySelectorAll('#everyone .ev').length", 10)
        rows = await page.js("document.querySelectorAll('#everyone .ev').length")
        check(found, f"everyone lists the laptop's sessions ({rows})")
        check(
            await page.js("getComputedStyle(document.getElementById('chats')).display")
            == "none",
            "the conversation list makes way for it",
        )
        before = await page.js(WIDTH)
        await page.js(
            """(()=>{const b=document.getElementById('split-list');const r=b.getBoundingClientRect();
            const at=(t,x)=>b.dispatchEvent(new PointerEvent(t,{bubbles:true,pointerId:1,clientX:x,clientY:300}));
            b.setPointerCapture=()=>{};at('pointerdown',r.x);at('pointermove',r.x+150);at('pointerup',r.x+150);return 1})()"""
        )
        after = await page.js(WIDTH)
        check(
            after > before + 100,
            f"dragging the divider widens the list ({before:.0f} -> {after:.0f} px)",
        )
        saved = await page.js("localStorage.getItem('forge.claude.width.list')")
        check(bool(saved), f"the width is remembered ({saved})")
        await page.js("document.getElementById('fold-accounts').click();1")
        check(
            await page.js(
                "document.getElementById('account-list').offsetParent===null"
            ),
            "the accounts fold away",
        )
        await page.screenshot(sandbox / "everyone.png")
        errs = await page.js("window.__e")
        check(not errs, f"no page errors: {errs}")
    return fails


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="everyone-"))
    env = dict(
        os.environ,
        FORGE_CLAUDE_DATA=str(sandbox / "data"),
        FORGE_CLAUDE_BIN=f"{sys.executable} {APP / 'tests/fake_claude.py'}",
    )
    with serve(APP, env) as port:
        fails = asyncio.run(run(port, sandbox))
    print("screenshot:", sandbox / "everyone.png")
    print("all passed" if not fails else f"{len(fails)} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
