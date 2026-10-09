"""Check that Forge apps use in-page ForgeDialog popups, never the browser's own.

    apps/terminal/.venv/bin/python tests/check_dialogs.py [--shots DIR]

The browser's confirm()/prompt()/alert() freeze the whole Forge page (and the
hub's music). For every app listed below this serves the app's static page and
/shared from a small local server (no app backend, so no jobs or models start),
opens it in headless Chrome, and checks:

- ForgeDialog is loaded on the page and a confirm round-trip works;
- where a converted button can be clicked without app data, clicking it shows
  a ForgeDialog, and the native confirm/prompt/alert are never called.

Not collected by pytest (it needs the Flatpak Chrome). Prints PASS/FAIL lines
and exits non-zero on any FAIL.
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import os
import shutil
import sys
import threading
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORGE / "tests"))

from cdp_driver import Page, chrome_page, free_port  # noqa: E402

# App -> buttons whose handler now opens a ForgeDialog before any server call.
APPS: dict[str, list[str]] = {
    "ai-studio": [],
    "browser": ["clear-history"],
    "calendar": [],
    "comix": [],
    "dossier": [],
    "foresight": [],
    "inkforge": [],
    "jan-tune": [],
    "mediaforge": [],
    "novelforge": ["hardStopBtn"],
    "pixelforge": ["newSprite", "newSound"],
    "pulseforge": [],
}

SPY = """(() => { window.__native = [];
  for (const k of ["alert", "confirm", "prompt"]) window[k] = () => { window.__native.push(k); return null; };
  return true; })()"""

results: list[str] = []
STEP = [""]  # the step running now, named in a timeout
ONLY = [a for a in sys.argv[1:] if a in APPS]


def check(name: str, ok: bool, extra: object = "") -> None:
    tail = f" :: {str(extra)[-300:]!r}" if extra and not ok else ""
    results.append(f"{'PASS' if ok else 'FAIL'} :: {name}{tail}")


class Static(http.server.SimpleHTTPRequestHandler):
    """/shared/* from ~/Forge/shared, everything else from the current app's static/."""

    app = ""

    def translate_path(self, path: str) -> str:
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith("/shared/"):
            return str(FORGE / "shared" / path[len("/shared/") :])
        rel = path.lstrip("/") or "index.html"
        return str(FORGE / "apps" / Static.app / "static" / rel)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


async def check_app(p: Page, port: int, app: str, shots: Path | None) -> None:
    Static.app = app
    STEP[0] = "loading the page"
    # go() does not wait for the load, so the URL names the app, and the
    # wait is for that page, not the one before it.
    await p.go(f"http://127.0.0.1:{port}/?app={app}")
    ok = await p.wait(
        f"location.search === '?app={app}' && document.readyState === 'complete'"
        " && typeof ForgeDialog === 'object'",
        10,
    )
    check(f"{app}: ForgeDialog is loaded", ok)
    if not ok:
        return
    STEP[0] = "confirm round-trip"
    await p.js(SPY)
    await p.js("void ForgeDialog.confirm('Check').then((v) => { window.__r = v; })")
    await p.js("document.querySelector('.forge-dialog button.ok').click()")
    check(f"{app}: confirm round-trip", await p.wait("window.__r === true", 3))
    for bid in APPS[app]:
        STEP[0] = f"clicking #{bid}"
        await p.js(
            f"(() => {{ const b = document.getElementById({bid!r});"
            " b.disabled = false; b.classList.remove('hidden'); b.click(); })()"
        )
        ok = await p.wait("!!document.querySelector('.forge-dialog')", 3)
        native = await p.js("window.__native")
        check(
            f"{app}: #{bid} opens a ForgeDialog, not a native popup",
            ok and not native,
            native,
        )
        if ok and shots:
            await p.screenshot(shots / f"dialog-{app}-{bid}.png")
        # Cancel, so nothing the button would do actually happens.
        await p.js("document.querySelector('.forge-dialog button:not(.ok)').click()")
        check(
            f"{app}: #{bid} dialog closes on Cancel",
            await p.wait("!document.querySelector('.forge-dialog')", 3),
        )


async def drive(box: Path, shots: Path | None) -> None:
    port = free_port()
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), functools.partial(Static)
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        async with chrome_page(box, "1100,700") as page:
            for app in APPS:
                if ONLY and app not in ONLY:
                    continue
                try:
                    await asyncio.wait_for(check_app(page, port, app, shots), 40)
                except TimeoutError:
                    check(f"{app}: finished within 40 s", False, STEP[0])
    finally:
        server.shutdown()


def main() -> int:
    shots = (
        Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None
    )
    box = FORGE / "tests" / f".dialogs-{os.getpid()}"
    box.mkdir()
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
