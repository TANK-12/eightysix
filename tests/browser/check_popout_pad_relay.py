"""Relay task 115: does a game in a pop-out window reach forge_popout?

    /usr/bin/python3 tests/browser/check_popout_pad_relay.py

A pop-out (forge_popout.PopOuts.open) is a bare WebKitGTK view on the app's
own address, so the page is the top window and a game's
{forge: "pad", native} message, posted to window.parent, lands on the page
itself. forge_popout.relay_pad_native adds a script and a "forgepad" message
handler that pass it to set_pad_native for that window, and resets it when a
new page commits. This loads, in an off-screen view set up the same way:

1. a page that posts {forge: "pad", native: true} to window.parent: the
   window's key must be set on;
2. a page in an iframe of that page posting {native: false} to its parent:
   set off;
3. a plain page: the commit sets it off again (it was set on first).

pad-focus is written to a scratch folder, never the live one forge-pad
reads. Software only (compositing off), nothing on screen, a few seconds.
Exit status 1 on any FAIL.
"""

from __future__ import annotations

import functools
import http.server
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
sys.path[:0] = [str(ROOT)]

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

import forge_popout  # noqa: E402

KEY = "popout:probe"
PAGES = {
    "game.html": """<!doctype html><script>
addEventListener("load", () => {
  window.parent.postMessage({ forge: "pad", native: true }, "*");
  setTimeout(() => (document.title = "SENT"), 300);
});
</script>""",
    "outer.html": """<!doctype html><body><iframe src="inner.html"></iframe>
<script>addEventListener("message", (e) => {
  if (e.data === "inner-sent") setTimeout(() => (document.title = "SENT"), 300);
});</script>""",
    "inner.html": """<!doctype html><script>
window.parent.postMessage({ forge: "pad", native: false }, "*");
window.parent.postMessage("inner-sent", "*");
</script>""",
    "plain.html": """<!doctype html><script>
addEventListener("load", () => setTimeout(() => (document.title = "SENT"), 300));
</script>""",
}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def main() -> int:
    calls: list = []
    real = forge_popout.set_pad_native

    def recording(on, key=forge_popout.MAIN):
        calls.append((key, on))
        real(on, key)

    forge_popout.set_pad_native = recording
    results = {}
    with tempfile.TemporaryDirectory() as www, tempfile.TemporaryDirectory() as run:
        forge_popout.PAD_FOCUS = Path(run) / "forge" / "pad-focus"
        for name, html in PAGES.items():
            Path(www, name).write_text(html)
        handler = functools.partial(QuietHandler, directory=www)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()

        win = Gtk.OffscreenWindow()
        view = WebKit2.WebView()  # as PopOuts.open makes it
        forge_popout.relay_pad_native(view, KEY)
        win.add(view)
        win.set_default_size(320, 240)
        win.show_all()
        queue = ["game.html", "outer.html", "plain.html"]
        state: dict = {"page": None}

        def load_next():
            if not queue:
                Gtk.main_quit()
                return
            state["page"] = queue.pop(0)
            view.load_uri(f"http://127.0.0.1:{port}/{state['page']}")

        def on_title(v, _prop):
            if (v.get_title() or "") != "SENT":
                return
            results[state["page"]] = list(calls)
            calls.clear()
            GLib.idle_add(load_next)

        def on_timeout():
            Gtk.main_quit()
            return False

        view.connect("notify::title", on_title)
        GLib.timeout_add_seconds(20, on_timeout)
        load_next()
        Gtk.main()
        server.shutdown()

    print(f"webkit {WebKit2.get_major_version()}.{WebKit2.get_minor_version()}")
    for page, got in results.items():
        print(f"info {page}: {got}")
    want = {
        "game.html": [(KEY, False), (KEY, True)],
        "outer.html": [(KEY, False), (KEY, False)],
        "plain.html": [(KEY, False)],
    }
    ok = True
    for page, calls_wanted in want.items():
        good = results.get(page) == calls_wanted
        ok = ok and good
        print(
            ("PASS" if good else "FAIL")
            + f" {page}: set_pad_native calls {results.get(page)} (want {calls_wanted})"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
