"""Relay task 115: can an app frame in the Forge window call getGamepads()?

    /usr/bin/python3 tests/browser/check_gamepad_webkit.py

An off-screen WebKitGTK view made by forge.hub_webview(), with the window's
file-access settings, loads a file:// page (the hub lives on file://) holding
three iframes on http://127.0.0.1:<port> (every Forge app is such a frame):
the hub's allow list ("fullscreen; microphone; gamepad", set in the hub's
order: src, then allow, then append), the hub's old list without gamepad, and
none. Each frame reports isSecureContext and what getGamepads() did.

PASS needs the hub's frame to be a secure context and get a list back. The
other two are printed for the record: with no pad plugged in, WebKitGTK
2.54.1 answered all three (measured 2026-10-08), so whether it refuses a frame
without the allow once a pad is connected is still open; run this with the
pad plugged in to see. Software only (compositing off), nothing on screen,
a few seconds. Exit status 1 on any FAIL.
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

# before WebKit starts: no GPU, and a display to talk to when run headless
os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")
os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
_run = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
if not os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
    if (_run / "wayland-0").exists():
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "shared")]

import forge  # noqa: E402
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

HUB_ALLOW = "fullscreen; microphone; gamepad"
FRAMES = {"hub": HUB_ALLOW, "old_hub": "fullscreen; microphone", "no_allow": None}

PROBE = """<!doctype html><script>
const r = { secure: window.isSecureContext, has: typeof navigator.getGamepads };
try {
  const g = Array.from(navigator.getGamepads());
  r.ok = true; r.slots = g.length; r.pads = g.filter(Boolean).map((p) => p.id);
} catch (e) { r.ok = false; r.err = e.name + ": " + e.message; }
parent.postMessage({ probe: location.search.slice(1), r }, "*");
</script>"""

TOP = """<!doctype html><body><script>
const frames = %s, got = {};
addEventListener("message", (e) => {
  if (!e.data || !e.data.probe) return;
  got[e.data.probe] = e.data.r;
  if (Object.keys(got).length === Object.keys(frames).length)
    document.title = "DONE " + JSON.stringify(got);
});
for (const [name, allow] of Object.entries(frames)) {
  const f = document.createElement("iframe");
  f.src = "http://127.0.0.1:%d/probe.html?" + name;
  if (allow !== null) f.allow = allow;
  document.body.appendChild(f);
}
</script>"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def run_probe(top: Path) -> dict | None:
    """Load the file:// page in the hub's kind of view; the frames' reports."""
    result: dict = {}
    win = Gtk.OffscreenWindow()
    view = forge.hub_webview()
    settings = view.get_settings()
    for prop in (
        "allow-file-access-from-file-urls",
        "allow-universal-access-from-file-urls",
    ):
        settings.set_property(prop, True)  # as forge.py sets them for the hub
    win.add(view)
    win.set_default_size(320, 240)
    win.show_all()

    def on_title(v, _prop):
        title = v.get_title() or ""
        if title.startswith("DONE "):
            result.update(json.loads(title[5:]))
            Gtk.main_quit()

    def on_timeout():
        Gtk.main_quit()
        return False

    view.connect("notify::title", on_title)
    GLib.timeout_add_seconds(20, on_timeout)
    view.load_uri(top.as_uri())
    Gtk.main()
    return result or None


def main() -> int:
    with tempfile.TemporaryDirectory() as www, tempfile.TemporaryDirectory() as tmp:
        Path(www, "probe.html").write_text(PROBE)
        handler = functools.partial(QuietHandler, directory=www)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        top = Path(tmp, "hub.html")
        top.write_text(TOP % (json.dumps(FRAMES), port))
        print(
            "webkit",
            ".".join(
                str(n)
                for n in (
                    WebKit2.get_major_version(),
                    WebKit2.get_minor_version(),
                    WebKit2.get_micro_version(),
                )
            ),
        )
        got = run_probe(top)
        server.shutdown()
    if got is None:
        print("FAIL no answer from the frames in 20 s")
        return 1
    for name in FRAMES:
        print(f"info {name} ({FRAMES[name]!r}): {json.dumps(got.get(name))}")
    hub = got.get("hub") or {}
    ok = bool(hub.get("secure") and hub.get("ok"))
    print(
        ("PASS" if ok else "FAIL")
        + " the hub's app frame is a secure context and getGamepads() answers"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
