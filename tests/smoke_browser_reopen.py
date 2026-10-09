"""The Browser's native views follow its page, off screen, in real WebKit.

WHAT IT CHECKS (Browser A8, 2026-09-26)
    Opens the real hub with the Browser, loads a page through the command
    queue, then closes and reopens the Browser workspace and reloads its frame
    from inside. After each step there must be exactly one native view (none
    after closing). Before the fix the old pages stayed alive and visible,
    stacking 1 -> 2 -> 3 views over the new page.

HOW TO RUN
    Needs a Browser backend on $PORT (default 18444) and network for
    example.com. Use scratch data so Emerson's records and profile are not
    touched:
      S=$(mktemp -d); cd apps/browser && FORGE_BROWSER_DATA=$S/d \\
        .venv/bin/python -m uvicorn web_app:app --port 18444 &
      FORGE_BROWSER_PROFILE=$S/p FORGE_BROWSER_CACHE=$S/c \\
        /usr/bin/python3 tests/smoke_browser_reopen.py $S/shot.png
    Prints what it saw; exits 1 if a step left the wrong views.
"""

import json, os, sys, threading, time, urllib.request

os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import GLib, Gtk, WebKit2
import forge_views

PORT = int(os.environ.get("PORT", "18444"))
BACKEND = f"http://127.0.0.1:{PORT}"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/forge-browser-reopen.png"
T0 = time.time()
log = []


def agent(cmd, timeout=30):
    req = urllib.request.Request(
        f"{BACKEND}/api/agent/do",
        data=json.dumps(dict(cmd, timeout=timeout - 5)).encode(),
        headers={"Content-Type": "application/json", "X-Forge": "1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


window = Gtk.OffscreenWindow()
window.set_default_size(1400, 900)
overlay = Gtk.Overlay()
hub = WebKit2.WebView()
hub.set_size_request(1400, 900)
for p in ("allow-file-access-from-file-urls", "allow-universal-access-from-file-urls"):
    hub.get_settings().set_property(p, True)
overlay.add(hub)
window.add(overlay)


def emit(ev):
    hub.run_javascript(
        f"window.forgeViewEvent && window.forgeViewEvent({json.dumps(ev)});",
        None,
        None,
        None,
    )


host = forge_views.ViewHost(overlay, emit)


def on_message(_m, result):
    v = result.get_js_value() if hasattr(result, "get_js_value") else result
    req = json.loads(v.to_string())
    if isinstance(req, dict) and isinstance(req.get("view"), dict):
        m = req["view"]
        log.append(
            (round(time.time() - T0, 2), m.get("op"), m.get("id", m.get("owner")))
        )
        host.handle(m)


cm = hub.get_user_content_manager()
cm.register_script_message_handler("forge")
cm.connect("script-message-received::forge", on_message)
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
hub.load_uri("file://" + ROOT + "/hub/index.html#app=browser")
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


def views():
    return [
        {
            "id": vid[-6:],
            "owner": e["owner"],
            "visible": e["view"].get_visible(),
            "rect": e["rect"],
            "uri": (e["view"].get_uri() or "")[:40],
        }
        for vid, e in host.views.items()
    ]


def snap(name):
    ev = threading.Event()
    box = {}

    def f():
        box["v"] = views()
        ev.set()
        return False

    GLib.idle_add(f)
    ev.wait(5)
    report[name] = box.get("v")


def js(code):
    GLib.idle_add(lambda: (hub.run_javascript(code, None, None, None), False)[1])


def drive():
    time.sleep(6)
    try:
        report["open"] = agent({"op": "open", "url": "https://example.com/"}).get(
            "ok", "?"
        )
        time.sleep(3)
        snap("1_after_open")
        js("closeWorkspace('browser')")
        time.sleep(1.5)
        snap("2_after_close")
        js("selectWorkspace('browser')")
        time.sleep(7)
        snap("3_after_reopen")
        js(
            "parts.browser.inner.querySelector('iframe').contentWindow.location.reload()"
        )
        time.sleep(7)
        snap("4_after_frame_reload")
    except Exception as e:
        report["error"] = repr(e)
    GLib.idle_add(finish)


def finish():
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)
    pb = window.get_pixbuf()
    if pb:
        pb.savev(OUT, "png", [], [])
    report["messages"] = log
    Gtk.main_quit()
    return False


threading.Thread(target=drive, daemon=True).start()
GLib.timeout_add_seconds(80, Gtk.main_quit)
Gtk.main()
print(json.dumps(report, indent=1))
want = {
    "1_after_open": 1,
    "2_after_close": 0,
    "3_after_reopen": 1,
    "4_after_frame_reload": 1,
}
bad = [k for k, n in want.items() if report.get(k) is None or len(report[k]) != n]
print(
    "FAIL :: " + ", ".join(bad)
    if bad
    else "PASS :: one view per page after open, close, reopen, reload"
)
sys.exit(1 if bad else 0)
