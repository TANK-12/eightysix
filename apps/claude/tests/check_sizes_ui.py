"""The Claude app at other App and Text sizes, in real headless Chrome (B14).

Not a pytest file (it needs Flatpak Chrome and `websockets`); run it with a
venv that has websockets, from the app folder:

    ../files/.venv/bin/python tests/check_sizes_ui.py

App size is WebKit page zoom in Forge, which lays the page out in a viewport
of window / zoom CSS pixels, so the window here is sized that way. Text size
is shared/forge_textsize.js. Both layouts (classic and Enjoy) and a task view
are opened at App size 0.8, 1 and 1.5 times Text size 0.8 and 1.5, and must
not scroll sideways, spill a box, or push the page past the window. Uses a
scratch data folder and the fake Claude, like check_enjoy_ui.py.
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

# the Forge window's content area at App size 1, in CSS pixels
WINDOW = (1500, 950)

# boxes whose children stick out sideways, plus the page's own scroll size
PROBE = r"""(() => {
  const name = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '');
  const spill = [];
  for (const e of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(e);
    if (!e.getClientRects().length || cs.visibility === 'hidden') continue;
    if (e.children.length && cs.overflowX === 'visible' && e.scrollWidth > e.clientWidth + 2)
      spill.push(name(e) + ' ' + e.scrollWidth + '>' + e.clientWidth);
  }
  const d = document.documentElement;
  const tall = [...document.querySelectorAll('body *')]
    .filter(e => e.getClientRects().length && e.getBoundingClientRect().bottom > innerHeight + 1
                 && getComputedStyle(e.parentElement).overflowY === 'visible')
    .slice(0, 6).map(e => name(e) + ' ' + Math.round(e.getBoundingClientRect().bottom));
  return JSON.stringify({w: d.scrollWidth - innerWidth, h: d.scrollHeight - innerHeight,
                         page: location.pathname, spill, tall});
})()"""

TEXT = """(async () => {
  if (!window.ForgeText) await new Promise(r => { const s = document.createElement('script');
    s.src = '/shared/forge_textsize.js'; s.onload = r; document.head.appendChild(s); });
  ForgeText.apply(%s);
})(); 1"""


async def run(port: int, sandbox: Path) -> list[str]:
    fails: list[str] = []
    call(port, "/api/projects", {"name": "cosmos", "cwd": str(sandbox)})
    task = call(port, "/api/conversations", {"cwd": str(sandbox)})["id"]
    call(port, f"/api/conversations/{task}/settings", {"title": "tidy the notes"})
    pages = ("index.html", "enjoy.html#projects", f"enjoy.html#task/{task}")
    for app_size in (0.8, 1, 1.5):
        size = f"{int(WINDOW[0] / app_size)},{int(WINDOW[1] / app_size)}"
        async with chrome_page(sandbox, size) as page:
            for text_size in (0.8, 1.5):
                for path in pages:
                    if path == "index.html":
                        # index.html jumps to Enjoy once Enjoy was used
                        await page.js(
                            "try{localStorage.removeItem('claude.layout')}catch(e){};1"
                        )
                    await page.go(f"http://127.0.0.1:{port}/{path}")
                    await asyncio.sleep(1.2)
                    await page.js(TEXT % text_size)
                    await asyncio.sleep(0.6)
                    got = json.loads(await page.js(PROBE))
                    what = f"app {app_size} text {text_size} {path.split('#')[0]}"
                    what += " task" if "task/" in path else ""
                    ok = got["w"] <= 0 and got["h"] <= 0 and not got["spill"]
                    print(("ok   " if ok else "FAIL ") + what, "" if ok else got)
                    if not ok:
                        fails.append(what)
    return fails


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="claude-sizes-"))
    try:
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
        print("all passed" if not fails else f"{len(fails)} failed")
        return 1 if fails else 0
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
