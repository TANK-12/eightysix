"""The "everyone" list names Relay sessions by task number and short
description, in headless Chrome against a scratch data folder and the fake
Claude. The session list is the laptop's real ~/.claude/sessions, read only,
so this needs at least one Relay session in the last three days.

    ../files/.venv/bin/python tests/check_relay_names_ui.py
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

NAMES = """[...document.querySelectorAll('#everyone .ev')].filter(
  e => /relay-\\d+-/.test(e.querySelector('.sub').textContent)
).map(e => e.querySelector('.n').textContent)"""


async def run(port: int, sandbox: Path) -> list[str]:
    fails: list[str] = []
    async with chrome_page(sandbox, "1400,900") as page:
        await page.go(f"http://127.0.0.1:{port}/index.html")
        await page.wait("document.getElementById('to-everyone')", 15)
        await asyncio.sleep(1.5)
        await page.js("document.getElementById('to-everyone').click();1")
        await page.wait("document.querySelectorAll('#everyone .ev').length", 10)
        names = await page.js(NAMES)
        ok = bool(names) and all(n.startswith("#") and len(n) <= 52 for n in names)
        print(
            ("ok   " if ok else "FAIL ")
            + f"relay rows read '#N short title': {names[:3]}"
        )
        if not ok:
            fails.append("relay names")
        await page.screenshot(sandbox / "relay_names.png")
    return fails


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="relaynames-"))
    env = dict(
        os.environ,
        FORGE_CLAUDE_DATA=str(sandbox / "data"),
        FORGE_CLAUDE_BIN=f"{sys.executable} {APP / 'tests/fake_claude.py'}",
    )
    with serve(APP, env) as port:
        fails = asyncio.run(run(port, sandbox))
    print(f"screenshot: {sandbox / 'relay_names.png'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
