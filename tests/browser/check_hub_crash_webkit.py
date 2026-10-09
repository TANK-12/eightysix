"""The hub's page crashing, in real WebKitGTK (task 63, 2026-10-07).

    /usr/bin/python3 tests/browser/check_hub_crash_webkit.py

Loads the real hub (forge.shell_url, held in the background so no music
starts) in a WebKit2 view inside a window that is never shown, wires
forge.hub_crash_reloader to it as forge.py does, then kills the page's web
process four times with terminate_web_process(). Checks: the first kill loads
the hub again normally, the second within two minutes loads it with ?safe=1
and the page really holds glass flat, 2.5D at two layers and the visualiser
off over apps, with its note showing; the fourth shows the "keeps crashing"
page. Prints PASS/FAIL lines; exit status 1 on any FAIL.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "shared")]

import forge  # noqa: E402
from gi.repository import Gtk, WebKit2  # noqa: E402

failed = 0


def check(ok: bool, what: str) -> None:
    global failed
    print(("PASS " if ok else "FAIL ") + what, flush=True)
    failed += not ok


def pump_until(cond, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if cond():
            return True
        time.sleep(0.02)
    return False


def main() -> int:
    win = Gtk.Window(title="forge-crash-check")
    view = forge.hub_webview()
    settings = view.get_settings()
    for prop in (
        "allow-file-access-from-file-urls",
        "allow-universal-access-from-file-urls",
    ):
        settings.set_property(prop, True)
    win.add(view)  # never shown: the reloader must keep the music held
    loads: list[str] = []
    terminated: list[str] = []

    def on_load(v, event):
        if event == WebKit2.LoadEvent.FINISHED:
            loads.append(v.get_uri() or "")

    view.connect("load-changed", on_load)
    view.connect(
        "web-process-terminated",
        lambda _v, r: terminated.append(getattr(r, "value_nick", str(r))),
    )
    view.connect(
        "web-process-terminated", forge.hub_crash_reloader(win, {}, {"host": None})
    )

    def run_js(script: str, timeout: float = 10):
        box: dict = {}

        def done(v, result):
            try:
                box["v"] = v.run_javascript_finish(result).get_js_value().to_string()
            except Exception as e:  # a page error comes back as the answer
                box["v"] = f"error: {e}"

        view.run_javascript(script, None, done)
        pump_until(lambda: "v" in box, timeout)
        return box.get("v")

    def page_state():
        raw = run_js(
            "JSON.stringify({safe: SAFE, glass: theme.glass_style,"
            " wall: theme.wall_3d_mode, vis: theme.visualiser_in_apps,"
            " hud: document.getElementById('fx-hud').textContent,"
            " hudShown: document.getElementById('fx-hud').classList.contains('show')})"
        )
        try:
            return json.loads(raw or "")
        except (TypeError, ValueError):
            return {"raw": raw}

    def kill_and_wait(n: int) -> str:
        before = len(loads)
        view.terminate_web_process()
        pump_until(lambda: len(loads) > before, 25)
        check(len(terminated) == n, f"kill {n}: web-process-terminated fired")
        return loads[-1] if len(loads) > before else ""

    view.load_uri(forge.shell_url(background=True))
    check(pump_until(lambda: loads, 25), "the hub loads at all")
    first = page_state()
    check(first.get("safe") is False, f"normal start is not safe mode: {first}")

    uri = kill_and_wait(1)
    check(uri == forge.shell_url(background=True), f"kill 1 reloads normally: {uri}")
    again = page_state()
    check(again.get("safe") is False and "hud" in again, f"page runs again: {again}")

    uri = kill_and_wait(2)
    check(
        uri == forge.shell_url(background=True, safe=True),
        f"kill 2 reloads in safe mode: {uri}",
    )
    pump_until(lambda: False, 1.0)  # let the page settle and show its note
    safe = page_state()
    check(safe.get("safe") is True, f"page knows it is safe: {safe}")
    check(
        safe.get("glass") == "flat"
        and safe.get("wall") == "layers"
        and safe.get("vis") is False,
        f"heavy looks held off: {safe}",
    )
    check(
        "crashed twice" in str(safe.get("hud")) and safe.get("hudShown") is True,
        "safe-mode note shows",
    )
    run_js("applyTheme({glass_style: 'liquid'}); 0")
    held = page_state()
    check(held.get("glass") == "flat", f"a looks change stays flat: {held}")

    kill_and_wait(3)
    before = len(loads)
    view.terminate_web_process()
    pump_until(lambda: len(loads) > before, 25)
    check(len(terminated) == 4, "kill 4: web-process-terminated fired")
    text = run_js("document.body.innerText")
    check("keeps crashing" in str(text), f"kill 4 shows the crash page: {text!r}")
    win.destroy()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
