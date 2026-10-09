"""End-to-end smoke check of the Browser inside the real hub, off screen.

WHAT IT DOES
    Builds the same arrangement forge.py does - the real hub/index.html in a
    WebKit view inside a Gtk.Overlay, the page-to-Python message channel, and
    forge_views.ViewHost - in an off-screen window, opens the Browser app
    (#app=browser), then asks the Browser to open a web page through its
    command queue (the same path the Claude panel uses), reads the page back,
    and saves a picture of the window.

    It needs the Browser backend already answering on its port (a running
    Forge provides it) and network access for the page. It shows nothing on
    screen. It is a smoke check, not a unit test: it prints what it saw and
    exits non-zero if the page never arrived.

HOW TO RUN
    /usr/bin/python3 tests/smoke_browser_window.py [out.png] [url]
"""

import json
import os
import sys
import threading
import time
import urllib.request

os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

import forge_views  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/forge-browser-smoke.png"
URL = sys.argv[2] if len(sys.argv) > 2 else "https://example.com/"
BACKEND = "http://127.0.0.1:8444"


def agent(command, timeout=40):
    body = json.dumps(dict(command, timeout=timeout - 5)).encode()
    request = urllib.request.Request(
        f"{BACKEND}/api/agent/do",
        data=body,
        headers={"Content-Type": "application/json", "X-Forge": "1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    window = Gtk.OffscreenWindow()
    window.set_default_size(1400, 900)
    overlay = Gtk.Overlay()
    hub = WebKit2.WebView()
    hub.set_size_request(1400, 900)
    for prop in (
        "allow-file-access-from-file-urls",
        "allow-universal-access-from-file-urls",
    ):
        hub.get_settings().set_property(prop, True)
    overlay.add(hub)
    window.add(overlay)

    def emit(event):
        hub.run_javascript(
            f"window.forgeViewEvent && window.forgeViewEvent({json.dumps(event)});",
            None,
            None,
            None,
        )

    host = forge_views.ViewHost(overlay, emit, profile=None, cache=None)
    seen = {"views": 0}

    def on_message(_manager, result):
        value = result.get_js_value() if hasattr(result, "get_js_value") else result
        request = json.loads(value.to_string())
        if isinstance(request, dict) and isinstance(request.get("view"), dict):
            seen["views"] += 1
            host.handle(request["view"])

    content = hub.get_user_content_manager()
    content.register_script_message_handler("forge")
    content.connect("script-message-received::forge", on_message)

    # The hub reads status.js; mark the Browser up so it mounts at once.
    status = {
        "browser": {
            "available": True,
            "state": "up",
            "label": "Browser",
            "tagline": "",
            "url": BACKEND,
            "accent": "#7cc4f0",
            "icon": "B",
            "role": "browser",
            "fullscreen": "",
        }
    }
    hub.load_uri("file://" + os.path.join(ROOT, "hub", "index.html") + "#app=browser")
    hub.connect(
        "load-changed",
        lambda v, e: e == WebKit2.LoadEvent.FINISHED
        and v.run_javascript(
            f"window.forgeSetStatus && window.forgeSetStatus({json.dumps(status)});",
            None,
            None,
            None,
        ),
    )
    window.show_all()

    report = {}

    def drive():
        time.sleep(6)  # the Browser page boots and starts its command loop
        try:
            report["open"] = agent({"op": "open", "url": URL})
            time.sleep(2)
            read = agent({"op": "read", "max_chars": 500})
            report["read_title"] = read.get("page", {}).get("title")
            report["read_text"] = (read.get("page", {}).get("text") or "")[:120]
            report["tabs"] = agent({"op": "tabs"})
        except Exception as e:
            report["error"] = repr(e)
        GLib.idle_add(finish)

    def finish():
        time.sleep(1)
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        pixbuf = window.get_pixbuf()
        if pixbuf:
            pixbuf.savev(OUT, "png", [], [])
        report["views_messages"] = seen["views"]
        report["native_views"] = {
            vid: {
                "owner": e["owner"],
                "rect": e["rect"],
                "visible": e["view"].get_visible(),
                "uri": e["view"].get_uri(),
            }
            for vid, e in host.views.items()
        }
        report["picture"] = OUT if pixbuf else None
        hold = int(os.environ.get("FORGE_SMOKE_HOLD", "0") or 0)
        if hold:
            # Keep the Browser page alive so something else (the Claude panel)
            # can drive it through the command queue.
            print(json.dumps(report), flush=True)
            GLib.timeout_add_seconds(hold, Gtk.main_quit)
        else:
            Gtk.main_quit()
        return False

    threading.Thread(target=drive, daemon=True).start()
    GLib.timeout_add_seconds(
        90 + int(os.environ.get("FORGE_SMOKE_HOLD", "0") or 0), Gtk.main_quit
    )
    Gtk.main()
    print(json.dumps(report, indent=2))
    ok = report.get("read_title") and any(
        v["visible"] and v["uri"].startswith(URL[:20])
        for v in report["native_views"].values()
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
