"""#257: the hub's background music reaches the speakers, measured.

    /usr/bin/python3 tests/browser/check_music_webkit.py

A real WebKitGTK window (kept below, app name "forge-music-check"; off-screen
WebKit never plays media) plays a quiet tone served by forge_music's
MusicServer, through Web Audio the way the hub does (Music.graph), with no
click. Its sound stream is linked straight into a pw-record capture
(parec --monitor-stream reads nothing on this PipeWire, even for a loud app).

The control, a plain WebKit2.WebView, must stay silent: WebKitGTK's default
autoplay policy refuses play() without a click, which is what kept the music
silent. The fix, forge.hub_webview(), must make sound. Prints PASS/FAIL lines;
exit status 1 on any FAIL. The tone is -40 dB for 4 seconds.
"""

from __future__ import annotations

import array
import json
import math
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "shared")]

import forge  # noqa: E402
import forge_music  # noqa: E402
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

APP = "forge-music-check"

PAGE = """<html><body><script>
const a = new Audio();
a.crossOrigin = "anonymous";
a.src = SRC;
const ctx = new AudioContext();
let routed = false;
const route = () => {
  if (routed || ctx.state !== "running") return;
  const gain = ctx.createGain();
  ctx.createMediaElementSource(a).connect(gain);
  gain.connect(ctx.destination);
  routed = true;
};
ctx.addEventListener("statechange", route);
ctx.resume().then(route).catch(() => {});
route();
a.play().catch(() => {});
setInterval(() => { document.title = JSON.stringify(
  { playing: !a.paused, t: a.currentTime, ctx: ctx.state, routed }); }, 200);
</script></body></html>"""


def tone(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi"]
        + ["-i", "sine=frequency=440:duration=30", "-af", "volume=-40dB"]
        + ["-c:a", "libvorbis", str(path)],
        check=True,
    )


def capture(secs: float, out: Path) -> tuple[int, float]:
    """Samples and RMS of APP's output over `secs`, linked port to port."""
    rec = subprocess.Popen(
        ["pw-record", "-P", "{ node.autoconnect=false node.name=forge-s26-cap }"]
        + ["--format", "s16", "--rate", "48000", "--channels", "2", str(out)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        end = time.time() + 3
        while time.time() < end:
            ins = subprocess.run(["pw-link", "-i"], capture_output=True, text=True)
            if "forge-s26-cap:input_FL" in ins.stdout:
                break
            time.sleep(0.1)
        outs = subprocess.run(["pw-link", "-o"], capture_output=True, text=True)
        for port in outs.stdout.split():
            if port.startswith(APP + ":output_F"):
                side = port[-2:]
                subprocess.run(
                    ["pw-link", port, f"forge-s26-cap:input_{side}"],
                    capture_output=True,
                )
        time.sleep(secs)
    finally:
        rec.terminate()
        rec.wait(timeout=5)
    with wave.open(str(out)) as w:
        samples = array.array("h", w.readframes(w.getnframes()))
    rms = math.sqrt(sum(x * x for x in samples) / max(1, len(samples)))
    return len(samples), rms


def run(view: WebKit2.WebView, page: Path, tmp: Path) -> tuple[dict, float]:
    win = Gtk.Window(title=APP)
    win.set_default_size(200, 80)
    win.set_keep_below(True)
    win.add(view)
    win.show_all()
    view.load_uri(page.as_uri())
    result: dict = {}

    def measure() -> bool:
        result["state"] = json.loads(view.get_title() or "{}")
        result["samples"], result["rms"] = capture(2, tmp / "cap.wav")
        Gtk.main_quit()
        return False

    GLib.timeout_add(2000, measure)
    GLib.timeout_add(15000, Gtk.main_quit)
    Gtk.main()
    win.destroy()
    while Gtk.events_pending():
        Gtk.main_iteration()
    return result.get("state", {}), result.get("rms", 0.0)


def main() -> int:
    GLib.set_prgname(APP)
    lines = []
    with tempfile.TemporaryDirectory(prefix="forge-music-check-") as name:
        tmp = Path(name)
        tone(tmp / "tone.ogg")
        server = forge_music.MusicServer(folder=lambda: tmp)
        src = server.start() + (tmp / "tone.ogg").as_uri()
        page = tmp / "page.html"
        page.write_text(PAGE.replace("SRC", json.dumps(src)))
        try:
            for label, view, loud in (
                ("plain WebView (the control)", WebKit2.WebView(), False),
                ("forge.hub_webview()", forge.hub_webview(), True),
            ):
                state, rms = run(view, page, tmp)
                ok = (rms > 1.0) == loud and bool(state.get("playing")) == loud
                want = "sound" if loud else "silence"
                lines.append(
                    f"{'PASS' if ok else 'FAIL'} :: {label} gives {want} with no "
                    f"click: rms {rms:.1f}, page {state}"
                )
        finally:
            server.stop()
    print("\n".join(lines))
    return 0 if all(ln.startswith("PASS") for ln in lines) else 1


if __name__ == "__main__":
    sys.exit(main())
