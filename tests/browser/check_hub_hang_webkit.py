"""The hub's page hanging, in real WebKitGTK in a headless GNOME (task 63).

    tests/browser/headless_gnome.sh start
    tests/browser/headless_gnome.sh run /usr/bin/python3 \\
        tests/browser/check_hub_hang_webkit.py [--shots DIR] [--fps]
    tests/browser/headless_gnome.sh stop

Emerson's Forge froze on 2026-10-07 when he picked Frosted or Liquid glass:
live blur on every tile stalled WebKit's compositor (no frames), and with
Liquid then its main thread. That only shows in a window a compositor really
presents, hence the headless GNOME. Loads the real hub as forge.py does and
wires forge.hub_crash_reloader, forge.hub_hang_watchdog and
forge.hub_hang_ender exactly as main() does.

Checks (light, no load beyond the hub itself):
  1. a healthy hub runs 20 s in front without being ended, and the
     window's GTK frame clock moves on (the watchdog's "desktop presents"
     test);
  2. Frosted and Liquid put live blur on single panes only, counted from
     the real page's computed style (--shots DIR saves a picture of each);
  3. a page whose frames stop (requestAnimationFrame swallowed) is ended
     and comes back with ?safe=1;
  4. a page whose main thread is stuck (a busy loop) is ended likewise;
  5. a page waiting on a confirm() nobody has answered yet is not ended,
     and runs on once it is answered (the critic's case: an app's dialog
     blocks the hub's main thread too);
  6. a page that sticks right after WebKit's own confirm() dialog is
     answered is still ended (the dialog shows inside the view);
  7. a page stuck before it finished loading is ended within
     HUB_HANG_LOAD_LIMIT and comes back with ?safe=1.
--fps adds a performance run (Emerson 2026-10-07: run those last, after
other work): the frame rate for 12 s each in flat, frosted and liquid glass
with the visualiser fed; PASS when each median is at least 30.
Prints PASS/FAIL lines; exit status 1 on any FAIL.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "shared")]

import forge  # noqa: E402
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

failed = 0
GLASS = ("flat", "frosted", "liquid")


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
        time.sleep(0.01)
    return False


class FrontWindow(Gtk.Window):
    """The rig's GNOME has no seat, so it focuses no window; this one says
    it is in front, as Forge is when Emerson looks at it, so the watchdog
    watches its frames. Everything else is real."""

    def is_active(self) -> bool:
        return True


def main(argv: list[str]) -> int:
    shots = Path(argv[argv.index("--shots") + 1]) if "--shots" in argv else None
    win = FrontWindow(title="Forge")
    win.set_default_size(1600, 1000)
    view = forge.hub_webview()
    win.add(view)
    win.show_all()
    win.maximize()
    screen: dict = {}
    loads: list[str] = []
    hung: list[float] = []
    crashes: dict = {}

    def on_load(v, event):
        if event == WebKit2.LoadEvent.FINISHED:
            loads.append(v.get_uri() or "")

    view.connect("load-changed", on_load)
    view.connect(
        "web-process-terminated",
        forge.hub_crash_reloader(win, screen, {"host": None}, crashes),
    )
    ender = forge.hub_hang_ender(view, crashes)

    def on_hung():
        hung.append(time.monotonic())
        ender()

    GLib.timeout_add_seconds(
        forge.HUB_HANG_PING, forge.hub_hang_watchdog(win, view, screen, on_hung)
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

    def frame_counter() -> int:
        frame_clock = win.get_frame_clock()
        return frame_clock.get_frame_counter() if frame_clock else -1

    def snapshot(name: str) -> None:
        if shots is None:
            return
        box: dict = {}
        path = str(shots / f"{name}.png")

        def got(v, result):
            try:
                v.get_snapshot_finish(result).write_to_png(path)
                box["ok"] = True
            except GLib.Error as e:
                box["ok"] = e.message

        shots.mkdir(parents=True, exist_ok=True)
        view.get_snapshot(
            WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE, None, got
        )
        pump_until(lambda: "ok" in box, 10)
        print(f"  picture {name}: {box.get('ok')}", flush=True)

    def set_glass(kind: str) -> None:
        run_js(f"applyTheme(Object.assign({{}}, theme, {{glass_style: '{kind}'}})); 0")
        pump_until(lambda: False, 1.5)  # its stylesheet loads and applies

    def blurred() -> list[str]:
        raw = run_js(
            "JSON.stringify([...document.querySelectorAll('body *')].filter((e) =>"
            " /blur/.test(getComputedStyle(e).backdropFilter || '')"
            " && e.getClientRects().length).map((e) => e.id || e.className))"
        )
        try:
            return json.loads(raw or "")
        except ValueError:
            return [f"unreadable: {raw}"]

    def hang_and_wait(how: str, script: str, limit: float = 0, start=None) -> None:
        before_hung, before_loads = len(hung), len(loads)
        # a clean crash budget each time: four ends in two minutes rightly
        # leave the "keeps crashing" page (seen here), tested in test_hub_crash
        crashes.pop("times", None)
        start() if start else run_js(script)
        limit = (limit or forge.HUB_HANG_LIMIT) + 3 * forge.HUB_HANG_PING + 5
        pump_until(lambda: len(loads) > before_loads, limit + 25)
        check(len(hung) == before_hung + 1, f"{how}: the watchdog ended the page once")
        check(
            len(loads) > before_loads and "safe=1" in loads[-1],
            f"{how}: it came back in safe mode: {loads[-1:]}",
        )
        pump_until(lambda: False, 1.5)
        check(run_js("String(SAFE)") == "true", f"{how}: the page runs again, safe")

    view.load_uri(forge.shell_url(background=True))
    check(pump_until(lambda: loads, 30), "the hub loads at all")
    pump_until(lambda: False, 2)
    real = Gtk.Window.is_active(win)
    print(
        f"  (the desktop has {'focused' if real else 'not focused'} the window)",
        flush=True,
    )

    frames_before = frame_counter()
    pump_until(lambda: hung, 20)
    check(not hung, "a healthy hub runs 20 s without the watchdog ending it")
    check(
        frame_counter() > frames_before >= 0,
        f"the window's frame clock moved on ({frames_before} -> {frame_counter()})",
    )

    tiles = run_js("String(document.querySelectorAll('.tile').length)")
    for kind in ("frosted", "liquid"):
        set_glass(kind)
        on = blurred()
        check(
            0 < len(on) <= 8 and not any("tile" in c.split() for c in on),
            f"{kind}: live blur on {len(on)} single panes, none of {tiles} tiles: {on}",
        )
        snapshot(kind)

    held: list = []

    def hold(_view, dialog):
        held.append(dialog)  # kept unanswered, as while Emerson reads it
        return True

    holding = view.connect("script-dialog", hold)  # after the watchdog's
    before_hung, before_loads = len(hung), len(loads)
    run_js("setTimeout(() => { window.said = confirm('Delete every zip?'); }, 50); 0")
    waited = forge.HUB_HANG_LIMIT + 3 * forge.HUB_HANG_PING + 5
    pump_until(lambda: len(hung) > before_hung, waited)
    check(
        len(held) == 1 and len(hung) == before_hung and len(loads) == before_loads,
        f"a confirm() open {waited:.0f} s is not ended ({len(held)} dialog)",
    )
    view.disconnect(holding)
    for dialog in held:
        dialog.confirm_set_confirmed(True)
        dialog.close()
    check(run_js("String(window.said)") == "true", "the page runs on once answered")
    pump_until(lambda: len(hung) > before_hung, 3 * forge.HUB_HANG_PING)
    check(len(hung) == before_hung, "and is not ended after it")

    def dialog_inside() -> list:
        inside: list = []
        view.forall(inside.append)
        return [w for w in inside if type(w).__name__ == "WebKitScriptDialogImpl"]

    def buttons(widget) -> list:
        found = [widget] if isinstance(widget, Gtk.Button) else []
        if isinstance(widget, Gtk.Container):
            widget.forall(lambda w: found.extend(buttons(w)))
        return found

    shown: list = []

    def keep(_view, dialog):
        shown.append(dialog)  # kept to answer it later; WebKit still shows it
        return False

    keeping = view.connect("script-dialog", keep)

    def confirm_then_stick():
        run_js("setTimeout(() => { confirm('Delete every zip?'); for (;;) {} }, 50); 0")
        pump_until(lambda: False, 3)
        check(
            len(shown) == 1 and bool(dialog_inside()),
            "WebKit shows its dialog in the view",
        )
        pump_until(lambda: False, forge.HUB_HANG_LIMIT + 2 * forge.HUB_HANG_PING)
        check(not hung[before:], "the open dialog is not ended")
        pressed = [b.get_label() for d in dialog_inside() for b in buttons(d)]
        for b in [b for d in dialog_inside() for b in buttons(d)][-1:]:
            b.clicked()  # its last button, OK, as Emerson would press it
        print(f"  dialog buttons {pressed}, pressed the last", flush=True)
        pump_until(lambda: not dialog_inside(), 5)
        check(not dialog_inside(), "the dialog is gone once answered")

    before = len(hung)
    hang_and_wait("stuck after a dialog", "", start=confirm_then_stick)
    view.disconnect(keeping)
    hang_and_wait(
        "stuck while loading",
        "",
        forge.HUB_HANG_LOAD_LIMIT,
        lambda: view.load_html("<p>loading</p><script>for (;;) {}</script>", None),
    )

    if "--fps" in argv:
        fps_run(view, run_js, set_glass)

    hang_and_wait(
        "frames stopped",
        "window.requestAnimationFrame = () => 0; 0",
    )
    hang_and_wait("main thread stuck", "setTimeout(() => { for (;;) {} }, 50); 0")
    screen["quitting"] = True
    win.destroy()
    return 1 if failed else 0


def fps_run(view, run_js, set_glass) -> None:
    """Frames a second for 12 s in each glass kind, the visualiser fed with
    moving levels as music would. A performance run: do it last."""
    run_js(
        "window.__f = 0; (function L() { window.__f++; requestAnimationFrame(L); })(); 0"
    )

    def levels():
        t = time.time()
        v = [round(0.5 + 0.45 * math.sin(t * 6 + i * 0.4), 3) for i in range(64)]
        view.run_javascript(
            f"window.forgeMusic && forgeMusic({{type: 'levels', v: {json.dumps(v)}}})",
            None,
            None,
            None,
        )
        return True

    feeding = GLib.timeout_add(50, levels)
    for kind in GLASS:
        set_glass(kind)
        rates = []
        last = int(float(run_js("String(window.__f)", 25) or -1))
        for _ in range(12):
            pump_until(lambda: False, 1.0)
            now = int(float(run_js("String(window.__f)", 25) or -1))
            rates.append(now - last)
            last = now
        rates.sort()
        median = rates[len(rates) // 2]
        check(median >= 30, f"{kind}: median {median} fps, lowest {rates[0]}")
    GLib.source_remove(feeding)
    set_glass("flat")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
