"""The Archived list in real headless Chrome (Emerson, 2026-09-27: quiet
conversations in no folder are archived after 2 hours).

Not a pytest file (it needs Flatpak Chrome and `websockets`); run it from the
app folder with a venv that has websockets:

    ../files/.venv/bin/python tests/check_archive_ui.py [--keep <folder>]

Seeds a quiet loose conversation (open as a tab, not on screen), a quiet one
in a folder and a fresh one, then checks the quiet loose one sits in a shut
Archived group, its tab closed, and its ↩ button brings it back.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "tests"))
sys.path.insert(0, str(APP.parents[1] / "tests"))
from cdp_driver import chrome_page  # noqa: E402
from check_enjoy_ui import start, stop  # noqa: E402

QUIET, FILED, FRESH = "a00000000001", "a00000000002", "a00000000003"


async def run(port: int, sandbox: Path) -> list[str]:
    fails = []

    def check(name: str, ok: bool, extra: str = "") -> None:
        print(("ok " if ok else "FAIL ") + name + (f" :: {extra}" if extra else ""))
        if not ok:
            fails.append(name)

    tabs = [{"id": i, "profile": "default"} for i in (QUIET, FRESH)]
    async with chrome_page(sandbox, "1300,700") as page:
        await page.go(f"http://127.0.0.1:{port}/")
        await page.js(
            f"localStorage.setItem('forge.claude.tabs', {json.dumps(json.dumps({'tabs': tabs, 'current': FRESH}))})"
        )
        await page.go(f"http://127.0.0.1:{port}/")
        await page.js(
            "window.__errs = []; window.addEventListener('error', e => __errs.push(e.message))"
        )
        check(
            "the quiet loose conversation sits in a shut Archived group",
            await page.wait(
                "(() => { const g = document.querySelector('.folder.archived');"
                f" return !!g && g.classList.contains('shut') && !!g.querySelector('[data-id=\"{QUIET}\"]')"
                " && g.querySelector('.count').textContent === '1' })()",
                30,
            ),
        )
        check(
            "the filed and the fresh ones stay where they were",
            await page.js(
                f"!!document.querySelector('.folder:not(.archived) [data-id=\"{FILED}\"]')"
                f" && !!document.querySelector('.loose [data-id=\"{FRESH}\"]')"
            ),
        )
        tab_ids = await page.js(
            "JSON.stringify([...document.querySelectorAll('.tab')].map(t => t.dataset.id))"
        )
        check(
            "its tab closed, the tab on screen stayed",
            json.loads(tab_ids) == [FRESH],
            tab_ids,
        )
        await page.js(
            "document.querySelector('.folder.archived .folder-head').click(); 1"
        )
        check(
            "clicking Archived opens it",
            await page.js(
                "!document.querySelector('.folder.archived').classList.contains('shut')"
            ),
        )
        await page.screenshot(sandbox / "archive.png")
        await page.js(
            f"document.querySelector('.folder.archived [data-id=\"{QUIET}\"] .back').click(); 1"
        )
        check(
            "↩ brings it back to the loose list",
            await page.wait(
                f"!document.querySelector('.folder.archived') && !!document.querySelector('.loose [data-id=\"{QUIET}\"]')",
                10,
            ),
        )
        errs = await page.js("JSON.stringify(window.__errs)")
        check("no page errors", errs == "[]", errs)
    return fails


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="archive-"))
    try:
        folder = sandbox / "data" / "conversations"
        folder.mkdir(parents=True)
        now = time.time()
        for conv_id, title, age, where in (
            (QUIET, "Old loose chat", 3 * 3600, ""),
            (FILED, "Old filed chat", 3 * 3600, "work"),
            (FRESH, "Fresh chat", 60, ""),
        ):
            (folder / f"{conv_id}.json").write_text(
                json.dumps(
                    {
                        "id": conv_id,
                        "title": title,
                        "folder": where,
                        "cwd": str(Path.home()),
                        "created": now - age,
                        "updated": now - age,
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
        if "--keep" in sys.argv and (sandbox / "archive.png").exists():
            shutil.copy(sandbox / "archive.png", Path(sys.argv[-1]) / "archive.png")
        print("all passed" if not fails else f"{len(fails)} failed")
        return 1 if fails else 0
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
