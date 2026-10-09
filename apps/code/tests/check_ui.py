"""Drive the real editor in headless Chrome: open a file by link, type, save.

    .venv/bin/python tests/check_ui.py [--shots DIR]

Not collected by pytest (it needs the Flatpak Chrome). Starts its own wrapper
(and so its own OpenVSCode Server) with a sandbox data dir and a sandbox
project, so Emerson's editor settings and files are never touched.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))

from cdp_driver import CTRL, Page, chrome_page, serve  # noqa: E402

results: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    tail = f" :: {extra[-300:]!r}" if extra and not ok else ""
    results.append(f"{'PASS' if ok else 'FAIL'} :: {name}{tail}")


def get(port: int, path: str) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", headers={"X-Forge": "1"}
    )
    return json.load(urllib.request.urlopen(req))


async def run(p: Page, port: int, proj: Path, shots: Path | None) -> None:
    for _ in range(200):
        if get(port, "/api/session")["ready"]:
            break
        await asyncio.sleep(0.1)
    target = proj / "src" / "hello.py"
    info = get(port, "/api/url?" + urlencode({"path": str(target), "root": str(proj)}))
    check(
        "a file opens inside the given root",
        info["folder"] == str(proj),
        info["folder"],
    )

    # The wrapper page with #path= frames the editor on that file.
    await p.go(f"http://127.0.0.1:{port}/#path={target}")
    ok = await p.wait(
        "!document.getElementById('editor').hidden && document.getElementById('editor').src.includes('payload')",
        20,
    )
    check("wrapper frames the editor for #path=", ok)
    if shots:
        await asyncio.sleep(6)
        await p.screenshot(shots / "code-wrapper.png")

    # Straight to the editor address to reach its DOM (the frame is another origin).
    await p.go(info["url"])
    ok = await p.wait("!!document.querySelector('.monaco-workbench')", 30)
    check("VS Code workbench loads", ok)
    ok = await p.wait(
        "[...document.querySelectorAll('.tab .label-name')].some(e => e.textContent === 'hello.py')",
        30,
    )
    check("hello.py opens in a tab", ok)
    ok = await p.wait(
        "(document.querySelector('.view-lines')?.textContent || '').includes('greeting')",
        15,
    )
    check("its text is shown", ok)
    ok = await p.wait(
        "[...document.querySelectorAll('.monaco-list-row')].some(e => e.textContent.includes('src'))",
        15,
    )
    check("explorer shows the project folder", ok)

    # Type at the end and save with Ctrl+S.
    # Let the first-run notices settle, then click into the text as a person would.
    await asyncio.sleep(3)
    box = await p.js(
        "(() => { const r = document.querySelector('.view-lines').getBoundingClientRect(); return [r.left + 200, r.top + 30]; })()"
    )
    for t in ("mousePressed", "mouseReleased"):
        await p.call(
            "Input.dispatchMouseEvent",
            type=t,
            x=box[0],
            y=box[1],
            button="left",
            clickCount=1,
        )
    await asyncio.sleep(0.3)
    await p.key("End", "End", CTRL, 35)
    await p.type("# typed-in-forge\n")
    await p.key("s", "KeyS", CTRL, 83)
    for _ in range(50):
        if "typed-in-forge" in target.read_text():
            break
        await asyncio.sleep(0.1)
    shown = await p.js("document.querySelector('.view-lines')?.textContent || ''")
    check("typing reaches the editor", "typed-in-forge" in shown, shown)
    check(
        "Ctrl+S saves to disk",
        "typed-in-forge" in target.read_text(),
        target.read_text(),
    )
    ok = await p.wait(
        "!!document.querySelector('.mtk1, .mtk3, .mtk4, .mtk5, .mtk6, .mtk7, .mtk8')", 5
    )
    check("syntax colouring is applied", ok)
    dark = await p.js(
        "document.querySelector('.monaco-workbench').classList.contains('vs-dark')"
    )
    check("Forge's dark theme is the default", bool(dark))
    restricted = await p.js("document.body.textContent.includes('Restricted Mode')")
    check("no Restricted Mode prompt", not restricted)

    # Forge restarts the editor behind an open page (app restart, Forge
    # restart): the page it reloads must connect again, not be refused.
    log = proj.parent / "data" / "server.log"
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/restart", method="POST", headers={"X-Forge": "1"}
    )
    after = json.load(urllib.request.urlopen(req))
    check(
        "a restart keeps the editor's address",
        after["base"] in info["url"],
        after["base"],
    )
    # The same page, loaded again without the token: only its cookie is left.
    # VS Code asks "leave this page?" on the way out, which holds the
    # navigation in a headless browser until the question is answered.
    here = await p.js("location.href")
    try:
        await asyncio.wait_for(p.go(here), 8)
    except asyncio.TimeoutError:
        await p.call("Page.handleJavaScriptDialog", accept=True)
    ok = await p.wait(
        "[...document.querySelectorAll('.monaco-list-row')].some(e => e.textContent.includes('src'))",
        30,
    )
    check("after a restart the reloaded page reaches the files again", ok)
    text = log.read_text()
    check("and is never refused", "auth mismatch" not in text, text)
    if shots:
        await p.screenshot(shots / "code-editor.png")


async def drive(box: Path, shots: Path | None) -> None:
    with serve(APP, {"CODE_DATA_DIR": str(box / "data")}) as port:
        async with chrome_page(box, "1200,760") as page:
            await asyncio.wait_for(run(page, port, box / "proj", shots), 240)


def main() -> int:
    shots = (
        Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None
    )
    box = APP / "tests" / f".ui-{os.getpid()}"
    (box / "data").mkdir(parents=True)
    (box / "proj" / "src").mkdir(parents=True)
    (box / "proj" / "src" / "hello.py").write_text(
        'greeting = "hello"\nprint(greeting)\n'
    )
    (box / "proj" / "README.md").write_text("# Sandbox\n")
    try:
        asyncio.run(drive(box, shots))
    except Exception as e:  # noqa: BLE001 - report, then clean up
        results.append(f"FAIL :: harness error :: {e!r}")
    finally:
        shutil.rmtree(box, ignore_errors=True)
    print("\n".join(results))
    return 1 if any(r.startswith("FAIL") for r in results) or not results else 0


if __name__ == "__main__":
    sys.exit(main())
