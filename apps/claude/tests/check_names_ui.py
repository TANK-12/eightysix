"""Human names on the tabs and in the list, in real headless Chrome.

Not a pytest file (it needs Flatpak Chrome and `websockets`); run it from the
app folder with a venv that has websockets:

    ../files/.venv/bin/python tests/check_names_ui.py [--keep <folder>]

Seeds one conversation from before names existed, makes two new ones, opens
all three as tabs, and checks each tab and list row shows the name the API
gave it, with the topic after it. --keep copies the screenshot out.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "tests"))
sys.path.insert(0, str(APP.parents[1] / "tests"))
from cdp_driver import chrome_page  # noqa: E402
from check_enjoy_ui import call, start, stop  # noqa: E402

OLD = "0123456789ab"


async def run(port: int, sandbox: Path) -> list[str]:
    made = [call(port, "/api/conversations", {}) for _ in range(2)]
    call(
        port,
        f"/api/conversations/{made[0]['id']}/settings",
        {"title": "Fix the power drain in the hub"},
    )
    chats = {c["id"]: c for c in call(port, "/api/conversations")["conversations"]}
    tabs = [
        {"id": i, "profile": "default"} for i in (OLD, made[0]["id"], made[1]["id"])
    ]
    fails = []
    async with chrome_page(sandbox, "1300,700") as page:
        await page.go(f"http://127.0.0.1:{port}/")
        # the page lists conversations after its accounts check, which can be slow
        await page.js(
            "window.__errs = []; window.addEventListener('error', e => __errs.push(e.message))"
        )
        await page.js(
            f"localStorage.setItem('forge.claude.tabs', {json.dumps(json.dumps({'tabs': tabs, 'current': OLD}))})"
        )
        await page.go(f"http://127.0.0.1:{port}/")
        if not await page.wait(
            "document.querySelectorAll('.tab .who').length === 3", 30
        ):
            fails.append(
                "tabs never showed 3 names: "
                + str(
                    await page.js(
                        "JSON.stringify({tabs: document.querySelectorAll('.tab').length, items: document.querySelectorAll('.chat-item').length,  body: document.body.innerText.slice(0, 300), stored: localStorage.getItem('forge.claude.tabs')})"
                    )
                )
            )
        shown = await page.js(
            "JSON.stringify([...document.querySelectorAll('.tab')].map(t => [t.dataset.id, t.querySelector('.who').textContent, (t.querySelector('.topic') || {}).textContent || '']))"
        )
        for conv_id, who, topic in json.loads(shown):
            want = chats[conv_id]
            if who != want["name"] or topic != (want.get("title") or ""):
                fails.append(
                    f"tab {conv_id}: showed {who!r} / {topic!r}, API has {want['name']!r} / {want.get('title')!r}"
                )
            else:
                print(f"ok tab {conv_id}: {who} / {topic or '(no topic yet)'}")
        rows = await page.js("document.querySelectorAll('.chat-item .who').length")
        if rows != 3:
            fails.append(f"list shows {rows} names, want 3")
        await page.screenshot(sandbox / "names.png")
        # The Board's "Go to it": the same request board/web_app.py sends.
        await page.js(f"openTab({json.dumps(made[1]['id'])}); 1")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/sessions/s-old/focus?pid=1",
            method="POST",
            data=b"",
            headers={"X-Forge": "1"},
        )
        with urllib.request.urlopen(req, timeout=5) as reply:
            print("focus asked:", json.load(reply)["name"])
        if await page.wait(
            f"(document.querySelector('.tab.on') || {{}}).dataset?.id === {json.dumps(OLD)}",
            6,
        ):
            print("ok the page opened the jumped-to tab")
        else:
            fails.append("the page did not open the tab the Board asked for")
    return fails


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="names-"))
    try:
        folder = sandbox / "data" / "conversations"
        folder.mkdir(parents=True)
        (folder / f"{OLD}.json").write_text(
            json.dumps(
                {
                    "id": OLD,
                    "title": "Acchan headless shells",
                    "session_id": "s-old",
                    "cwd": str(Path.home()),
                    "created": 1,
                    "updated": 1,
                }
            )
        )
        env = {
            "FORGE_CLAUDE_DATA": str(sandbox / "data"),
            "FORGE_CLAUDE_BIN": f"{sys.executable} {APP / 'tests/fake_claude.py'}",
            "FORGE_SHARED_DIR": str(APP.parents[1] / "shared"),
        }
        proc, port = start(env)
        try:
            fails = asyncio.run(run(port, sandbox))
        finally:
            stop(proc)
        if "--keep" in sys.argv and (sandbox / "names.png").exists():
            shutil.copy(sandbox / "names.png", Path(sys.argv[-1]) / "names.png")
        print("all passed" if not fails else "\n".join(fails))
        return 1 if fails else 0
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
