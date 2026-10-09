"""Measure what a Forge page costs the GPU in a real WebKitGTK view.

Loads a page (the hub, the desktop particles page) in the same WebKit2 4.1
build forge.py and desktop/particles.py use, lets it settle, then reads the
render-engine time of the view's WebKitWebProcess from the kernel's DRM
fdinfo counters (tools/gpu_use.py) over a measuring window. Run it against
two trees (a copy of the files before a change, and the live tree) for a
before/after figure on the same machine in the same sitting.

    python3 tools/web_gpu_bench.py --page hub/index.html [--root DIR]
        [--seconds 12] [--warm 6] [--size 1920x1080] [--js "Ambient.toggle(true)"]
        [--levels] [--visible] [--json]

--js runs in the page once it has loaded (a mode to measure).
--levels answers the page's {"music": {"op": "levels"}} asks with cava's
levels the way forge.py does, so a system-source visualiser draws real sound.
--visible shows a real full-screen window instead of an off-screen one;
GTK cannot make a GL context for an off-screen window on Wayland, so on
GNOME this is the mode that works. With the monitors off mutter draws at a
10 fps fallback, so wake them first (PowerSaveMode 0) for real figures.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

HERE = Path(__file__).resolve().parent
FORGE = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FORGE / "shared"))
import gpu_use  # noqa: E402

COUNT_JS = """
(() => {
  const raf = window.requestAnimationFrame.bind(window);
  window.__benchFrames = 0;
  const tick = () => { window.__benchFrames++; raf(tick); };
  raf(tick);
})();
"""


def web_processes(parent: int) -> list[int]:
    out = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            stat = (p / "stat").read_text()
        except OSError:
            continue
        comm = stat[stat.index("(") + 1 : stat.rindex(")")]
        ppid = int(stat.rsplit(")", 1)[1].split()[1])
        if ppid == parent and comm.startswith("WebKitWebProces"):
            out.append(int(p.name))
    return out


def totals(pids: list[int]) -> tuple[int, int]:
    gpu = sum(gpu_use.engines(p).get("render", 0) for p in pids)
    cpu = sum(gpu_use.cpu_ticks(p) for p in pids)
    return gpu, cpu


GT = Path("/sys/class/drm/card1/gt/gt0")


def gt_read(name: str) -> int:
    """An i915 GT counter, or -1 where there is none (another GPU)."""
    try:
        return int((GT / name).read_text())
    except (OSError, ValueError):
        return -1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", default="hub/index.html")
    ap.add_argument("--root", default=str(FORGE))
    ap.add_argument("--seconds", type=float, default=12)
    ap.add_argument("--warm", type=float, default=6)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--js", default="")
    ap.add_argument("--levels", action="store_true")
    ap.add_argument("--visible", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--eval", default="", help="a JS expression printed at the end")
    ap.add_argument("--shot", default="", help="save a PNG of the page at the end")
    ap.add_argument(
        "--no-count",
        action="store_true",
        help="leave out the frame counter (its own frames can keep a page drawing)",
    )
    a = ap.parse_args()
    w, h = (int(x) for x in a.size.split("x"))

    content = WebKit2.UserContentManager()
    if not a.no_count:
        content.add_script(
            WebKit2.UserScript.new(
                COUNT_JS,
                WebKit2.UserContentInjectedFrames.TOP_FRAME,
                WebKit2.UserScriptInjectionTime.START,
                None,
                None,
            )
        )
    view = WebKit2.WebView.new_with_user_content_manager(content)
    settings = view.get_settings()
    for prop in (
        "allow-file-access-from-file-urls",
        "allow-universal-access-from-file-urls",
    ):
        settings.set_property(prop, True)

    levels = None

    def push(event: dict) -> None:
        script = f"window.forgeMusic && window.forgeMusic({json.dumps(event)});"
        GLib.idle_add(lambda: view.run_javascript(script, None, None, None))

    def desktop_push(event: dict) -> None:
        if event.get("type") == "levels":
            script = f"window.forgeDesktop && window.forgeDesktop({json.dumps({'levels': event.get('v')})});"
            GLib.idle_add(lambda: view.run_javascript(script, None, None, None))

    def on_message(_mgr, res, *_):
        nonlocal levels
        try:
            msg = json.loads(res.get_js_value().to_string())
        except (ValueError, AttributeError):
            return
        if not a.levels or not isinstance(msg, dict):
            return
        import forge_music

        # the desktop page asks {"levels": {"on", "fps"}} the way
        # desktop/particles.py answers it
        ask = msg.get("levels")
        if isinstance(ask, dict):
            levels = levels or forge_music.SystemLevels()
            if ask.get("on"):
                levels.start(desktop_push, 32, int(ask.get("fps", 30)))
            else:
                levels.stop()
            return
        music = msg.get("music")
        if not isinstance(music, dict) or music.get("op") != "levels":
            return

        levels = levels or forge_music.SystemLevels()
        if music.get("on"):
            levels.start(
                push,
                int(music.get("bars", 32)),
                int(music.get("fps", 30)),
                bool(music.get("fast")),
            )
        else:
            levels.stop()

    for name in ("forge", "desktop"):
        content.register_script_message_handler(name)
        content.connect(f"script-message-received::{name}", on_message)

    if a.visible:
        win = Gtk.Window()
        win.set_default_size(w, h)
        win.fullscreen()
    else:
        win = Gtk.OffscreenWindow()
        view.set_size_request(w, h)
    win.add(view)
    win.show_all()
    page = Path(a.root) / a.page
    view.load_uri(page.resolve().as_uri())

    result: dict = {"page": a.page, "root": a.root, "js": a.js, "size": a.size}

    def js(script: str) -> None:
        view.run_javascript(script, None, None, None)

    def frames(cb) -> None:
        def done(v, res):
            try:
                cb(int(v.run_javascript_finish(res).get_js_value().to_double()))
            except Exception:  # noqa: BLE001 - a page without the counter
                cb(-1)

        view.run_javascript("window.__benchFrames || 0", None, done)

    def snapshot(then) -> None:
        def got(v, res):
            try:
                v.get_snapshot_finish(res).write_to_png(a.shot)
            except Exception as err:  # noqa: BLE001 - reported, the run goes on
                result["shot_error"] = str(err)
            then()

        view.get_snapshot(
            WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE, None, got
        )

    def start_measure() -> bool:
        pids = web_processes(os.getpid())
        result["web_pids"] = pids
        g0, c0 = totals(pids)
        u0 = gpu_use.engines(os.getpid()).get("render", 0)
        rc0 = gt_read("rc6_residency_ms")
        t0 = time.monotonic()
        # The GPU clock floats between 100 and 1200 MHz, so busy time alone
        # flatters a light load run at a low clock; sample it alongside.
        freqs: list[int] = []

        def sample() -> bool:
            freqs.append(gt_read("rps_act_freq_mhz"))
            return "seconds" not in result

        GLib.timeout_add(100, sample)

        def got_f0(f0: int) -> None:
            def finish() -> bool:
                g1, c1 = totals(pids)
                u1 = gpu_use.engines(os.getpid()).get("render", 0)
                wall = time.monotonic() - t0

                def got_f1(f1: int) -> None:
                    result["seconds"] = round(wall, 1)
                    result["web_render_pct"] = round(100 * (g1 - g0) / (wall * 1e9), 2)
                    result["ui_render_pct"] = round(100 * (u1 - u0) / (wall * 1e9), 2)
                    result["web_cpu_pct"] = round(
                        100 * (c1 - c0) / gpu_use.CLK / wall, 1
                    )
                    result["raf_per_s"] = round((f1 - f0) / wall, 1)
                    rc1 = gt_read("rc6_residency_ms")
                    if rc0 >= 0 and freqs:
                        # whole GPU, every process: share of time awake (not in
                        # its RC6 sleep state), and the mean clock
                        awake = 1 - (rc1 - rc0) / 1000 / wall
                        result["gpu_awake_pct"] = round(100 * max(0.0, awake), 1)
                        result["gpu_mhz"] = round(sum(freqs) / len(freqs))
                        top = gt_read("rps_RP0_freq_mhz")
                        if top > 0:
                            # the page's busy time scaled to the top clock: a
                            # steadier cost figure than busy time alone
                            result["web_full_clock_pct"] = round(
                                result["web_render_pct"] * result["gpu_mhz"] / top, 2
                            )
                    if levels:
                        levels.stop()
                    if a.shot:
                        snapshot(lambda: done_or_eval())
                    else:
                        done_or_eval()

                def done_or_eval() -> None:
                    if not a.eval:
                        Gtk.main_quit()
                        return

                    def evaluated(v, res):
                        try:
                            val = v.run_javascript_finish(res).get_js_value()
                            result["eval"] = val.to_string()
                        except Exception as err:  # noqa: BLE001 - shown as is
                            result["eval"] = f"error: {err}"
                        Gtk.main_quit()

                    view.run_javascript(a.eval, None, evaluated)

                frames(got_f1)
                return False

            GLib.timeout_add(int(a.seconds * 1000), finish)

        frames(got_f0)
        return False

    def loaded(_v, event) -> None:
        if event != WebKit2.LoadEvent.FINISHED:
            return
        if a.js:
            GLib.timeout_add(1500, lambda: js(a.js) or False)
        GLib.timeout_add(int(a.warm * 1000), start_measure)

    view.connect("load-changed", loaded)
    GLib.timeout_add(int((a.warm + a.seconds + 30) * 1000), Gtk.main_quit)
    Gtk.main()
    if a.json:
        print(json.dumps(result))
    else:
        print(
            f"{a.page} [{a.js or 'as loaded'}] web render {result.get('web_render_pct')}% "
            f"ui render {result.get('ui_render_pct')}% web cpu {result.get('web_cpu_pct')}% "
            f"rAF {result.get('raf_per_s')}/s gpu awake {result.get('gpu_awake_pct')}% "
            f"at {result.get('gpu_mhz')} MHz, page at full clock "
            f"{result.get('web_full_clock_pct')}%"
        )
        if "eval" in result:
            print(result["eval"])


if __name__ == "__main__":
    main()
