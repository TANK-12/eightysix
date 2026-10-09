"""Ask a live page a question, off screen, in the same WebKit Forge uses.

WHY
    Headless Chrome photographs pages that keep a long poll open (the Claude
    app) before they finish booting, so its pictures and DOM dumps come back
    empty at random. This loads the page in WebKitGTK, optionally seeds
    localStorage and reloads, waits a fixed time, then prints the value of a
    JavaScript expression and saves a picture of the window.

HOW TO RUN
    /usr/bin/python3 tests/page_probe.py URL SEED_JS EXPR_JS WAIT_SECONDS OUT.png
    SEED_JS may be "" (no seeding). Example, the Claude app's A29 check:
      tests/page_probe.py http://127.0.0.1:18445/ \\
        "localStorage.setItem('forge.claude.tabs', JSON.stringify({tabs:[{id:ID}], current:ID}))" \\
        "document.body.innerText.includes('FIRST-UPDATE')" 6 /tmp/shot.png
"""

import json, os, sys

os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")
# WebKitGTK 2.54 on Wayland asks GDK for a GL context for its DMA-BUF renderer,
# which an offscreen window cannot give, and aborts before the page loads.
os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import GLib, Gtk, WebKit2

url, seed, expr, wait, out = (
    sys.argv[1],
    sys.argv[2],
    sys.argv[3],
    float(sys.argv[4]),
    sys.argv[5],
)
win = Gtk.OffscreenWindow()
win.set_default_size(1100, 700)
view = WebKit2.WebView(web_context=WebKit2.WebContext.new_ephemeral())
view.set_size_request(1100, 700)
win.add(view)
win.show_all()
stage = {"seeded": not seed}


def loaded(v, e):
    if e != WebKit2.LoadEvent.FINISHED:
        return
    if not stage["seeded"]:
        stage["seeded"] = True
        v.run_javascript(seed + "; location.reload();", None, None, None)
        return
    GLib.timeout_add(int(wait * 1000), ask)


def ask():
    def done(v, res, *_):
        try:
            print(v.run_javascript_finish(res).get_js_value().to_string())
        except Exception as e:
            print("error", e)
        pb = win.get_pixbuf()
        if pb:
            pb.savev(out, "png", [], [])
        Gtk.main_quit()

    view.run_javascript(expr, None, done, None)
    return False


view.connect("load-changed", loaded)
view.load_uri(url)
GLib.timeout_add_seconds(60, Gtk.main_quit)
Gtk.main()
