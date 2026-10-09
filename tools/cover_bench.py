"""GPU use of Forge and the desktop while covered, minimised or elsewhere.

Relay task 60. Runs inside a GNOME Shell session (meant for a private
headless one, so the live screen is never touched; see
docs/library/forge/2026-10-07-gpu-when-covered.md for the rig) with the
Forge GNOME extension enabled and its desktop window running, and Shell.Eval
allowed (unsafe mode). It opens a stand-in for the Forge window: the real
hub page in WebKitGTK, maximised, with forge.py's resting wiring
(shared/forge_seen.py). Then it walks through:

  visible      nothing over it
  maximised    another window maximised over it
  almost       that window 97 % wide and high, Forge peeking out round it
  most         that window 90 % wide and high (19 % of Forge shows: awake)
  minimised    the cover closed, Forge minimised
  workspace    Forge back, the session on another workspace
  back         back on Forge's workspace

and for each reads the render-engine time of the stand-in's web process and
of the desktop page's (from the kernel's DRM fdinfo, tools/gpu_use.py), and
how long the page took to report itself visible again after "back".

    python3 tools/cover_bench.py [--seconds 10] [--settle 6] [--no-shell]
        [--root DIR] [--js "Ambient.toggle(true)"] [--json]

--no-shell leaves out the extension's answer (forge.py before task 60).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit2  # noqa: E402

HERE = Path(__file__).resolve().parent
FORGE = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FORGE / "shared"))

import gpu_use  # noqa: E402
from forge_seen import Seen, watch_shell  # noqa: E402
from web_gpu_bench import web_processes  # noqa: E402

COVER = """
import gi
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk
GLib.set_prgname("r60cover")
w = Gtk.Window(title="cover")
w.connect("destroy", Gtk.main_quit)
w.show_all()
Gtk.main()
"""

VISIBLE_JS = """
document.addEventListener("visibilitychange", () =>
  window.webkit.messageHandlers.bench.postMessage(document.visibilityState));
"""


def shell_eval(code: str) -> str:
    """Run JavaScript in GNOME Shell (needs unsafe mode)."""
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    ok, out = bus.call_sync(
        "org.gnome.Shell",
        "/org/gnome/Shell",
        "org.gnome.Shell",
        "Eval",
        GLib.Variant("(s)", (code,)),
        GLib.VariantType("(bs)"),
        Gio.DBusCallFlags.NONE,
        5000,
        None,
    ).unpack()
    if not ok:
        raise RuntimeError(f"Shell.Eval refused or failed: {out}")
    return out


def win_js(pid: int) -> str:
    return (
        "global.get_window_actors().map(a => a.meta_window)"
        f".find(w => w.get_pid() === {pid})"
    )


def pump(seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.005)


def desktop_pids() -> list[int]:
    """The desktop page's web processes (children of desktop/particles.py
    started in this session)."""
    me = os.environ.get("XDG_RUNTIME_DIR", "")
    out = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            cmd = (p / "cmdline").read_bytes().split(b"\0")
            env = (p / "environ").read_bytes().split(b"\0")
        except OSError:
            continue
        if any(c.endswith(b"desktop/particles.py") for c in cmd) and (
            f"XDG_RUNTIME_DIR={me}".encode() in env
        ):
            out += web_processes(int(p.name))
    return out


def render(pids: list[int]) -> int:
    return sum(gpu_use.engines(p).get("render", 0) for p in pids)


def cpu(pids: list[int]) -> int:
    return sum(gpu_use.cpu_ticks(p) for p in pids)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(FORGE))
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--settle", type=float, default=6)
    ap.add_argument("--js", default="")
    ap.add_argument("--no-shell", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    GLib.set_prgname("Forge")
    content = WebKit2.UserContentManager()
    content.add_script(
        WebKit2.UserScript.new(
            VISIBLE_JS,
            WebKit2.UserContentInjectedFrames.TOP_FRAME,
            WebKit2.UserScriptInjectionTime.START,
            None,
            None,
        )
    )
    shown_at: list[float] = []
    content.register_script_message_handler("bench")
    content.connect(
        "script-message-received::bench",
        lambda _m, res: (
            shown_at.append(time.monotonic())
            if res.get_js_value().to_string() == "visible"
            else None
        ),
    )
    view = WebKit2.WebView.new_with_user_content_manager(content)
    settings = view.get_settings()
    for prop in (
        "allow-file-access-from-file-urls",
        "allow-universal-access-from-file-urls",
    ):
        settings.set_property(prop, True)
    win = Gtk.Window(title="Forge")
    win.set_default_size(1600, 900)
    win.add(view)

    # forge.py's wiring (B34 + task 60), see main() there
    seen = Seen()

    def apply_seen():
        page = win.get_child()
        if page is not None and page.get_child_visible() != seen.seen:
            page.set_child_visible(seen.seen)
        return False

    def on_visibility(_w, event):
        if seen.visibility(event.state == Gdk.VisibilityState.FULLY_OBSCURED):
            apply_seen()
        return False

    def on_state(_w, event):
        if seen.window_state(event.new_window_state & Gdk.WindowState.ICONIFIED):
            apply_seen()
        return False

    win.add_events(Gdk.EventMask.VISIBILITY_NOTIFY_MASK)
    win.connect("visibility-notify-event", on_visibility)
    win.connect("window-state-event", on_state)
    win.connect("map-event", lambda *_a: seen.mapped(True) and apply_seen())
    win.connect("unmap-event", lambda *_a: seen.mapped(False) and apply_seen())
    monitor = None if a.no_shell else watch_shell(seen, apply_seen)

    view.load_uri((Path(a.root) / "hub" / "index.html").resolve().as_uri())
    win.show_all()
    win.maximize()
    pump(4)
    if a.js:
        view.run_javascript(a.js, None, None, None)
    me = os.getpid()
    hub = web_processes(me)
    desk = desktop_pids()
    cover: subprocess.Popen | None = None

    def measure(name: str) -> dict:
        pump(a.settle)
        g0, d0, c0, t0 = render(hub), render(desk), cpu(hub), time.monotonic()
        pump(a.seconds)
        wall = time.monotonic() - t0
        row = {
            "phase": name,
            "hub_render_pct": round(100 * (render(hub) - g0) / 1e9 / wall, 1),
            "desktop_render_pct": round(100 * (render(desk) - d0) / 1e9 / wall, 1),
            "hub_cpu_pct": round(100 * (cpu(hub) - c0) / gpu_use.CLK / wall, 1),
            "seen": seen.seen,
            "under": (
                Path(os.environ["XDG_RUNTIME_DIR"], "forge-desktop-under.json")
                .read_text()
                .strip()
                if Path(
                    os.environ["XDG_RUNTIME_DIR"], "forge-desktop-under.json"
                ).exists()
                else ""
            ),
        }
        if not a.json:
            print(
                f"{name:10} hub {row['hub_render_pct']:5}% (cpu {row['hub_cpu_pct']}%)"
                f"  desktop {row['desktop_render_pct']:5}%  seen={row['seen']}"
                f"  under={row['under']}",
                flush=True,
            )
        return row

    def cover_js(code: str) -> None:
        assert cover is not None
        shell_eval(
            f"{{ const Meta = imports.gi.Meta; const c = {win_js(cover.pid)}; {code} }}"
        )

    # GNOME Shell starts in the overview, where every window shows
    shell_eval("Main.overview.hide();")
    rows = [measure("visible")]
    cover = subprocess.Popen([sys.executable, "-c", COVER])
    pump(2)
    cover_js("c.maximize(Meta.MaximizeFlags.BOTH);")
    rows.append(measure("maximised"))
    for name, share in (("almost", 0.97), ("most", 0.90)):
        cover_js(
            "c.unmaximize(Meta.MaximizeFlags.BOTH);"
            "const m = global.display.get_monitor_geometry(c.get_monitor());"
            f"const w = Math.round(m.width * {share}), h = Math.round(m.height * {share});"
            "c.move_resize_frame(true, m.x + (m.width - w) / 2,"
            " m.y + (m.height - h) / 2, w, h);"
        )
        rows.append(measure(name))
    cover.terminate()
    cover.wait()
    pump(1)
    shell_eval(f"{win_js(me)}.minimize();")
    rows.append(measure("minimised"))
    shell_eval(f"{win_js(me)}.unminimize();")
    pump(1)
    shell_eval(
        "{ const wm = global.workspace_manager;"
        " if (wm.n_workspaces < 2) wm.append_new_workspace(false, global.get_current_time());"
        " wm.get_workspace_by_index(1).activate(global.get_current_time()); }"
    )
    rows.append(measure("workspace"))
    shown_at.clear()
    t_back = time.monotonic()
    shell_eval(
        "global.workspace_manager.get_workspace_by_index(0)"
        ".activate(global.get_current_time());"
    )
    rows.append(measure("back"))
    wake = round(1000 * (shown_at[0] - t_back)) if shown_at else None
    if a.json:
        print(json.dumps({"rows": rows, "wake_ms": wake, "no_shell": a.no_shell}))
    else:
        print(f"page visible again {wake} ms after switching back")
    del monitor


if __name__ == "__main__":
    main()
