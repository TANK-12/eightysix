"""The Relay page's running list names a session by task number and short
description, with the persona as a small tag, in headless Chrome. Uses a
scratch Relay data folder with one fake running session.

    ../files/.venv/bin/python tests/check_names_ui.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP.parents[1] / "shared"))
from cdp_driver import chrome_page, serve  # noqa: E402

TITLE = "Mission Control conversation view: part one, with a long tail of detail"


def seed(sandbox: Path) -> dict:
    data = sandbox / "relay"
    os.environ["RELAY_DATA_DIR"] = str(data)
    import items, runs, store  # noqa: E401

    store.ensure()
    task = items.new_task(TITLE, "x")
    runs.save(
        {
            "id": "sid-1",
            "session": "sid-1",
            "task": task["id"],
            "kind": "work",
            "account": "hey",
            "effort": "medium",
            "started": 1.0,
            "ended": None,
            "command": ["claude", "-p", "--name", f"relay-{task['id']}-work"],
        }
    )
    crew = sandbox / "crew" / "forge"
    crew.mkdir(parents=True)
    (crew / "board.json").write_text(
        json.dumps(
            {"members": {"m": {"session": "sid-1", "persona": "Mika", "last_seen": 5}}}
        )
    )
    return {
        "RELAY_DATA_DIR": str(data),
        "CREW_HOME": str(sandbox / "crew"),
        "FORGE_APPS_DIR": str(sandbox / "apps"),
        "FORGE_JAN_SETTINGS_DIR": str(sandbox / "jan"),
    }


async def run(port: int, sandbox: Path) -> list[str]:
    fails: list[str] = []
    async with chrome_page(sandbox, "1200,800") as page:
        await page.go(f"http://127.0.0.1:{port}/")
        await page.wait("document.querySelector('#running .title')", 15)
        title = await page.js("document.querySelector('#running .title').textContent")
        tag = await page.js("document.querySelector('#running .muted').textContent")
        for ok, what in (
            (
                title.startswith("#") and "Mission Control conversation view" in title,
                f"title {title!r}",
            ),
            ("part one" not in title, "title is cut short"),
            (tag == "Mika", f"persona tag {tag!r}"),
        ):
            print(("ok   " if ok else "FAIL ") + what)
            if not ok:
                fails.append(what)
        await page.screenshot(sandbox / "relay_names.png")
    return fails


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="relaynames-", dir=Path.home() / ".cache"))
    env = seed(sandbox)
    with serve(APP, env) as port:
        fails = asyncio.run(run(port, sandbox))
    print(f"screenshot: {sandbox / 'relay_names.png'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
