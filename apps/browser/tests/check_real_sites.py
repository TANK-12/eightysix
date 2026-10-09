"""Real sites in the Browser, built the way Forge builds it (Relay task 122).

WHAT IT DOES
    Builds what forge.py builds: the real hub page in a WebKit view inside a
    Gtk.Overlay, forge.py's own view_handler and forge_views.ViewHost, in a
    shown window. It starts a scratch Browser backend on --port with its
    records in a scratch folder, and gives the page views a scratch WebKit
    profile, so Emerson's records and cookies are never touched. The hub opens
    the Browser, and the rig drives it:

    1. the first page opened shows (a native view, visible, with a size);
    2. typing an address into the Browser's own address bar, then Enter,
       opens it (synthetic pointer and key events, sent through GTK);
    3. a click in a page focuses it and typed keys land in its text field;
    4. a target=_blank link opens a new tab;
    5. a local file and a bare path open as the file, not as a search;
    6. every site in SITES: load result, title, text size, crashes, and a
       picture of the native view.

    It writes report.json and the pictures into --out and prints the report.

HOW TO RUN (needs a shown window with GL: use the private headless GNOME
Shell, never Emerson's desktop unattended)
    tests/browser/headless_gnome.sh start          # from ~/Forge
    tests/browser/headless_gnome.sh run /usr/bin/python3 \\
        apps/browser/tests/check_real_sites.py --port 8923 --out /tmp/t122/run1
    tests/browser/headless_gnome.sh stop

    --sites none skips the real sites (offline checks only).
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[1]
# RIG_BROWSER_APP runs another copy of the Browser app (an older one, to see a
# check fail without the fix); the hub and forge_views stay this tree's.
APP = Path(os.environ.get("RIG_BROWSER_APP", APP))
sys.path.insert(0, str(ROOT))

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, GLib, Gtk, WebKit2  # noqa: E402

import forge  # noqa: E402
import forge_views  # noqa: E402

SITES = [
    ("duckduckgo", "https://duckduckgo.com/?q=webkitgtk"),
    ("google", "https://www.google.com/search?q=webkitgtk"),
    ("wikipedia", "https://en.wikipedia.org/wiki/WebKit"),
    ("youtube", "https://www.youtube.com/"),
    ("github", "https://github.com/"),
    ("reddit", "https://www.reddit.com/r/linux/"),
    ("google-signin", "https://accounts.google.com/"),
    ("whatsapp", "https://web.whatsapp.com/"),
    ("artstation", "https://www.artstation.com/"),
    ("x", "https://x.com/"),
    ("crunchyroll", "https://www.crunchyroll.com/"),
]

TEST_PAGE = """<!doctype html><meta charset="utf-8"><title>rig page</title>
<body style="margin:0;font:16px sans-serif;background:#fff">
<input id="q" style="position:absolute;left:40px;top:40px;width:320px;height:40px">
<a id="pop" href="/second.html" target="_blank"
   style="position:absolute;left:40px;top:120px;font-size:24px">new window link</a>
</body>"""
SECOND_PAGE = (
    '<!doctype html><meta charset="utf-8"><title>second page</title><p>second</p>'
)

# Tells the rig where the Browser's address bar is inside its frame: the hub
# page cannot reach into the app's frame (another origin), a user script can.
ADDRESS_PROBE = """(() => {
  if (!document.getElementById("address")) return;
  const tell = () => {
    const r = document.getElementById("address").getBoundingClientRect();
    try { window.webkit.messageHandlers.rig.postMessage(JSON.stringify(
      {address: [r.left, r.top, r.width, r.height]})); } catch (e) {}
  };
  tell();
  setInterval(tell, 1000);
  // what the address bar hears, in order, for a failed check's detail
  const box = document.getElementById("address");
  const log = (e) => {
    try { window.webkit.messageHandlers.rig.postMessage(JSON.stringify({log: [e.type,
      e.target === box ? "address" : e.target === window ? "window" : String(e.target.nodeName),
      document.activeElement && document.activeElement.id, box.selectionStart, box.selectionEnd,
      Math.round(performance.now())]})); } catch (err) {}
  };
  for (const t of ["focus", "blur", "mousedown", "mouseup"]) box.addEventListener(t, log);
  for (const t of ["focus", "blur"]) window.addEventListener(t, log);
})();"""


class Rig:
    def __init__(self, args):
        self.args = args
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.scratch = self.out / "scratch"
        shutil.rmtree(self.scratch, ignore_errors=True)
        self.scratch.mkdir()
        self.backend_url = f"http://127.0.0.1:{args.port}"
        self.page_url = f"http://127.0.0.1:{args.port + 1}"
        self.report: dict = {"checks": {}, "sites": {}}
        self.events: dict[str, list] = {}
        self.address_rect: list | None = None
        self.frame_log: list = []
        self.keep = []  # synthetic events stay alive: freeing one unrefs its window

    # --- the window, as forge.py makes it -----------------------------------

    def build(self):
        self.win = Gtk.Window()
        self.win.set_default_size(self.args.width, self.args.height)
        self.hub = forge.hub_webview()
        # never a page or script cached by an earlier run
        self.hub.get_context().set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)
        settings = self.hub.get_settings()
        for prop in (
            "allow-file-access-from-file-urls",
            "allow-universal-access-from-file-urls",
        ):
            settings.set_property(prop, True)
        overlay = Gtk.Overlay()
        overlay.add(self.hub)
        self.win.add(overlay)
        self.box: dict = {"host": None}
        self.view_events: list = []
        rig = self

        class WatchedHost(forge_views.ViewHost):
            def create(
                self,
                view_id,
                owner,
                url,
                rect,
                session=None,
                keys=frozenset(),
                keys_first=frozenset(),
            ):
                super().create(view_id, owner, url, rect, session, keys, keys_first)
                entry = self.views.get(view_id)
                if entry:
                    rig.watch(view_id, entry["view"])

        def emit(event):
            self.view_events.append(event)
            self.hub.run_javascript(
                f"window.forgeViewEvent && window.forgeViewEvent({json.dumps(event)});",
                None,
                None,
                None,
            )

        self.handle = forge.view_handler(
            self.box,
            lambda: WatchedHost(
                overlay,
                emit,
                profile=self.scratch / "profile",
                cache=self.scratch / "cache",
            ),
            self.hub.get_zoom_level,
        )
        status = {
            "browser": {
                "available": True,
                "state": "up",
                "label": "Browser",
                "tagline": "",
                "url": self.backend_url,
                "accent": "#7cc4f0",
                "icon": "B",
                "role": "browser",
                "fullscreen": "",
            }
        }

        content = self.hub.get_user_content_manager()
        content.register_script_message_handler("forge")
        content.connect("script-message-received::forge", self.on_forge)
        content.register_script_message_handler("rig")
        content.connect("script-message-received::rig", self.on_rig)
        # The hub reads status.js, which forge.py writes with the live ports:
        # it must only ever see the scratch Browser, never Emerson's backend.
        content.add_script(
            WebKit2.UserScript(
                "if (window === top) Object.defineProperty(window, 'FORGE_STATUS',"
                f" {{value: {json.dumps(status)}, writable: false}});",
                WebKit2.UserContentInjectedFrames.TOP_FRAME,
                WebKit2.UserScriptInjectionTime.START,
                None,
                None,
            )
        )
        content.add_script(
            WebKit2.UserScript(
                ADDRESS_PROBE,
                WebKit2.UserContentInjectedFrames.ALL_FRAMES,
                WebKit2.UserScriptInjectionTime.END,
                None,
                None,
            )
        )

        def loaded(view, event):
            if event == WebKit2.LoadEvent.FINISHED:
                view.run_javascript(
                    f"window.forgeSetStatus && window.forgeSetStatus({json.dumps(status)});",
                    None,
                    None,
                    None,
                )

        self.hub.connect("load-changed", loaded)
        self.hub.load_uri((ROOT / "hub" / "index.html").as_uri() + "#app=browser")
        self.win.show_all()
        # focus events only fire in the active window, as on his desktop
        self.win.present()

    def on_forge(self, _manager, result):
        value = result.get_js_value() if hasattr(result, "get_js_value") else result
        try:
            request = json.loads(value.to_string())
        except ValueError:
            return
        if isinstance(request, dict) and isinstance(request.get("view"), dict):
            self.handle(request["view"])

    def on_rig(self, _manager, result):
        value = result.get_js_value() if hasattr(result, "get_js_value") else result
        try:
            said = json.loads(value.to_string())
            if "log" in said:
                self.frame_log.append(said["log"])
            else:
                self.address_rect = said.get("address")
        except ValueError:
            pass

    def watch(self, view_id, view):
        log = self.events.setdefault(view_id, [])

        def failed(_v, _event, uri, error):
            log.append(f"load-failed {uri[:100]}: {error.message}")
            return False

        def tls(_v, uri, _cert, flags):
            log.append(f"tls-error {uri[:100]}: {flags}")
            return False

        view.connect("load-failed", failed)
        view.connect("load-failed-with-tls-errors", tls)
        view.connect(
            "web-process-terminated",
            lambda _v, reason: log.append(f"web process ended: {reason}"),
        )

    # --- helpers that run on the GTK thread ---------------------------------

    def on_main(self, fn, timeout=20) -> Any:
        """Run fn(done) on the GTK thread; fn calls done(value) when finished."""
        box: dict = {}
        ready = threading.Event()

        def done(value=None):
            box["v"] = value
            ready.set()

        def start():
            try:
                fn(done)
            except Exception as e:  # reported, never left hanging
                done({"error": repr(e)})
            return False

        GLib.idle_add(start)
        if not ready.wait(timeout):
            return {"error": "timed out on the GTK thread"}
        return box.get("v")

    def view_of(self, view_id):
        host = self.box["host"]
        entry = host.views.get(view_id) if host else None
        return entry["view"] if entry else None

    def view_facts(self, view_id):
        def fn(done):
            view = self.view_of(view_id)
            if view is None:
                return done({"exists": False})
            # an overlay child's allocation is inside its own GDK window
            a = view.get_allocation()
            x, y = view.translate_coordinates(self.win, 0, 0) or (a.x, a.y)
            done(
                {
                    "exists": True,
                    "visible": view.get_visible() and view.get_mapped(),
                    "rect": [x, y, a.width, a.height],
                    "uri": view.get_uri(),
                    "has_focus": view.has_focus(),
                    "window_active": self.win.is_active(),
                }
            )

        return self.on_main(fn)

    def snapshot(self, view_id, name):
        path = self.out / f"{name}.png"

        def fn(done):
            view = self.view_of(view_id)
            if view is None:
                return done(None)

            def got(v, result):
                try:
                    surface = v.get_snapshot_finish(result)
                    surface.write_to_png(str(path))
                    done(str(path))
                except Exception as e:
                    done(f"no picture: {e}")

            view.get_snapshot(
                WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE, None, got
            )

        return self.on_main(fn)

    def window_picture(self, name):
        """The hub and every shown native view, painted where GTK put them."""
        import cairo

        path = self.out / f"{name}.png"

        def fn(done):
            alloc = self.win.get_allocation()
            canvas = cairo.ImageSurface(cairo.FORMAT_ARGB32, alloc.width, alloc.height)
            cr = cairo.Context(canvas)
            layers = [(self.hub, 0, 0)]
            host = self.box["host"]
            for entry in host.views.values() if host else []:
                view = entry["view"]
                if view.get_visible() and view.get_mapped():
                    a = view.get_allocation()
                    x, y = view.translate_coordinates(self.win, 0, 0) or (a.x, a.y)
                    layers.append((view, x, y))
            pending = {"n": len(layers), "shots": [None] * len(layers)}

            def paint():
                for shot, (_v, x, y) in zip(pending["shots"], layers):
                    if shot is not None:
                        cr.set_source_surface(shot, x, y)
                        cr.paint()
                canvas.write_to_png(str(path))
                done(str(path))

            for i, (view, _x, _y) in enumerate(layers):

                def got(v, result, i=i):
                    try:
                        pending["shots"][i] = v.get_snapshot_finish(result)
                    except Exception:
                        pass
                    pending["n"] -= 1
                    if pending["n"] == 0:
                        paint()

                view.get_snapshot(
                    WebKit2.SnapshotRegion.VISIBLE,
                    WebKit2.SnapshotOptions.NONE,
                    None,
                    got,
                )

        return self.on_main(fn, timeout=30)

    def run_js(self, view_id, script):
        def fn(done):
            view = self.view_of(view_id)
            if view is None:
                return done({"error": "no view"})

            def got(v, result):
                try:
                    done(
                        json.loads(
                            v.run_javascript_finish(result).get_js_value().to_string()
                        )
                    )
                except Exception as e:
                    done({"error": str(e)})

            view.run_javascript(script, None, got)

        return self.on_main(fn)

    # --- synthetic input, sent through GTK the way a real event arrives -------

    def activate(self):
        """Make the window the active one, as his is while he uses Forge: the
        headless shell never focuses a new window, and in an inactive window
        WebKit fires no focus events, so the address bar never hears one."""

        def fn(done):
            ev = Gdk.Event.new(Gdk.EventType.FOCUS_CHANGE)
            ev.focus_change.window = self.win.get_window()
            ev.focus_change.in_ = 1
            ev.focus_change.send_event = 1
            self.keep.append(ev)
            Gtk.main_do_event(ev)
            done(self.win.is_active())

        return self.on_main(fn)

    def click(self, widget_fn, x, y):
        def fn(done):
            widget = widget_fn()
            gdkwin = widget.get_window()
            seat = Gdk.Display.get_default().get_default_seat()
            ox, oy = gdkwin.get_root_origin()
            for kind, state in (
                (Gdk.EventType.BUTTON_PRESS, 0),
                (Gdk.EventType.BUTTON_RELEASE, Gdk.ModifierType.BUTTON1_MASK),
            ):
                ev = Gdk.Event.new(kind)
                ev.button.window = gdkwin
                ev.button.x, ev.button.y = float(x), float(y)
                ev.button.x_root, ev.button.y_root = float(ox + x), float(oy + y)
                ev.button.button = 1
                ev.button.state = state
                ev.button.time = Gtk.get_current_event_time() or int(
                    GLib.get_monotonic_time() / 1000
                )
                ev.set_device(seat.get_pointer())
                self.keep.append(ev)
                Gtk.main_do_event(ev)
            done(True)

        return self.on_main(fn)

    def type_text(self, text):
        return self.press(
            [
                Gdk.KEY_Return if ch == "\n" else Gdk.unicode_to_keyval(ord(ch))
                for ch in text
            ]
        )

    def press(self, keyvals, state=0):
        """Key presses sent to whatever has the keyboard, with `state`'s
        modifiers held."""

        def fn(done):
            gdkwin = self.win.get_window()
            seat = Gdk.Display.get_default().get_default_seat()
            keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
            for keyval in keyvals:
                ok, keys = keymap.get_entries_for_keyval(keyval)
                code = keys[0].keycode if ok and keys else 0
                for kind in (Gdk.EventType.KEY_PRESS, Gdk.EventType.KEY_RELEASE):
                    ev = Gdk.Event.new(kind)
                    ev.key.window = gdkwin
                    ev.key.keyval = keyval
                    ev.key.hardware_keycode = code
                    ev.key.state = Gdk.ModifierType(state)
                    ev.key.time = int(GLib.get_monotonic_time() / 1000)
                    if seat.get_keyboard() is not None:
                        ev.set_device(seat.get_keyboard())
                    self.keep.append(ev)
                    Gtk.main_do_event(ev)
            done(True)

        return self.on_main(fn)

    # --- the Browser's command queue (the Claude panel's path) ---------------

    def agent(self, command, timeout=40):
        body = json.dumps(dict(command, timeout=timeout - 5)).encode()
        request = urllib.request.Request(
            f"{self.backend_url}/api/agent/do",
            data=body,
            headers={"Content-Type": "application/json", "X-Forge": "1"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as r:
            return json.loads(r.read())

    def check(self, name, ok, detail):
        self.report["checks"][name] = {"ok": bool(ok), "detail": detail}
        print(
            f"{'PASS' if ok else 'FAIL'} {name}: {json.dumps(detail)[:300]}", flush=True
        )

    # --- the run ------------------------------------------------------------

    def start_servers(self):
        env = dict(
            os.environ,
            FORGE_BROWSER_DATA=str(self.scratch / "data"),
            FORGE_SHARED_DIR=str(ROOT / "shared"),
        )
        log = open(self.scratch / "backend.log", "wb")
        self.backend = subprocess.Popen(
            [str(APP / ".venv/bin/python"), "-m", "uvicorn", "web_app:app"]
            + ["--host", "127.0.0.1", "--port", str(self.args.port)],
            cwd=APP,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        pages = {"/": TEST_PAGE, "/second.html": SECOND_PAGE}

        class Pages(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = pages.get(self.path.split("?")[0], "missing").encode()
                self.send_response(200 if self.path.split("?")[0] in pages else 404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):  # noqa: A002 (the base's name)
                pass

        self.pages = http.server.ThreadingHTTPServer(
            ("127.0.0.1", self.args.port + 1), Pages
        )
        threading.Thread(target=self.pages.serve_forever, daemon=True).start()
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{self.backend_url}/api/state", timeout=1)
                return
            except OSError:
                time.sleep(0.2)
        raise SystemExit("the scratch Browser backend did not start")

    def drive(self):
        try:
            self.drive_checks()
        except Exception as e:
            self.report["error"] = repr(e)
            print("ERROR", repr(e), flush=True)
        GLib.idle_add(Gtk.main_quit)

    def wait_for_loop(self):
        until = time.time() + 40
        while time.time() < until:
            try:
                if self.agent({"op": "tabs"}, timeout=8).get("ok"):
                    return True
            except Exception:
                time.sleep(1)
        return False

    def hub_state(self):
        def fn(done):
            def got(v, result):
                try:
                    done(
                        json.loads(
                            v.run_javascript_finish(result).get_js_value().to_string()
                        )
                    )
                except Exception as e:
                    done({"error": str(e)})

            self.hub.run_javascript(
                "JSON.stringify({frames: [...document.querySelectorAll('iframe')]"
                ".map((f) => f.src), hash: location.hash,"
                " status: typeof window.forgeSetStatus,"
                " body: document.body ? document.body.className : null})",
                None,
                got,
            )

        return self.on_main(fn)

    def drive_checks(self):
        time.sleep(2)
        self.check("window is active", self.activate(), {})
        hub = self.hub_state()
        for _ in range(3):  # the GTK thread can be busy with the first load
            if "error" not in hub:
                break
            time.sleep(2)
            hub = self.hub_state()
        frames = hub.get("frames") or []
        if not frames or any(f":{self.args.port}/" not in f for f in frames):
            self.check("hub uses only the scratch Browser", False, hub)
            return  # never drive a live backend
        answers = self.wait_for_loop()
        self.check("browser page answers", answers, hub)
        if not answers:
            return
        time.sleep(1)

        # 1. the first page opened shows
        r = self.agent({"op": "open", "url": f"{self.page_url}/"})
        tab = r.get("tab", {})
        time.sleep(1)
        facts = self.view_facts(tab.get("id", ""))
        self.check(
            "first page shows",
            facts.get("visible") and facts["rect"][2] > 100 and facts["rect"][3] > 100,
            facts,
        )
        self.window_picture("01-first-page")

        # 3. a click in the page focuses it and keys land in its field
        first = tab.get("id", "")
        self.click(lambda: self.view_of(first), 60, 60)
        time.sleep(0.5)
        self.type_text("hello")
        time.sleep(1)
        got = self.run_js(
            first,
            "JSON.stringify({value: document.getElementById('q').value,"
            " active: document.activeElement && document.activeElement.id})",
        )
        self.check(
            "click and type into a page",
            isinstance(got, dict) and got.get("value") == "hello",
            {"page": got, "view": self.view_facts(first)},
        )

        # 4. a target=_blank link opens a new tab
        before = len(self.agent({"op": "tabs"}).get("tabs", []))
        self.run_js(first, "document.getElementById('pop').click(); 'null'")
        time.sleep(2)
        tabs = self.agent({"op": "tabs"}).get("tabs", [])
        self.check(
            "new-window link opens a tab",
            len(tabs) == before + 1 and tabs[-1]["url"].endswith("/second.html"),
            [t["url"] for t in tabs],
        )
        for t in tabs[1:]:
            self.agent({"op": "close", "tab": t["id"]})

        # 2. typing into the Browser's own address bar, then Enter
        until = time.time() + 10
        while self.address_rect is None and time.time() < until:
            time.sleep(0.3)
        frame = self.hub_frame_rect()
        if self.address_rect and frame:
            x = frame[0] + self.address_rect[0] + 40
            y = frame[1] + self.address_rect[1] + self.address_rect[3] / 2
            self.click(lambda: self.hub, x, y)
            time.sleep(0.4)
            self.type_text(f"{self.page_url}/second.html\n")
            time.sleep(2.5)
            tabs = self.agent({"op": "tabs"}).get("tabs", [])
            front = next((t for t in tabs if t["active"]), {})
            facts = self.view_facts(front.get("id", ""))
            self.check(
                "address bar opens what is typed",
                str(front.get("url", "")).endswith("/second.html")
                and facts.get("visible"),
                {"front": front, "view": facts, "address heard": self.frame_log[-12:]},
            )
        else:
            self.check(
                "address bar opens what is typed",
                False,
                {"address": self.address_rect, "frame": frame},
            )
        self.window_picture("02-address-bar")

        # 5. a local file and a bare path open as the file
        note = self.scratch / "note.md"
        note.write_text("# Rig note\n\nlocal file text 7341\n", encoding="utf-8")
        for name, text in (("file url", note.as_uri()), ("bare path", str(note))):
            r = self.agent({"op": "open", "url": text, "new_tab": True})
            time.sleep(1.5)
            tab = r.get("tab", {})
            page = self.agent({"op": "read", "tab": tab.get("id", "")})
            words = (page.get("page") or {}).get("text") or ""
            self.check(
                f"local {name} opens the file",
                "local file text 7341" in words,
                {"tab": tab, "text": words[:120]},
            )
            if tab.get("id"):
                self.agent({"op": "close", "tab": tab["id"]})

        # 7. a shortcut pressed while a page has the keyboard: Ctrl+L puts
        # the caret in the address bar, what is typed opens, and the page
        # gets the keyboard back
        tabs = self.agent({"op": "tabs"}).get("tabs", [])
        front = next((t for t in tabs if t["active"]), {})
        fid = front.get("id", "")
        self.click(lambda: self.view_of(fid), 60, 60)
        time.sleep(0.5)
        focused = self.view_facts(fid).get("has_focus")
        heard = len(self.frame_log)
        self.press([Gdk.KEY_l], Gdk.ModifierType.CONTROL_MASK)
        time.sleep(0.6)
        self.type_text(f"{self.page_url}/?shortcut=1\n")
        time.sleep(2.5)
        tabs = self.agent({"op": "tabs"}).get("tabs", [])
        front = next((t for t in tabs if t["active"]), {})
        facts = self.view_facts(front.get("id", ""))
        keys = [e for e in self.view_events if e.get("event") == "key"]
        self.check(
            "Ctrl+L inside a page reaches the address bar",
            focused
            and front.get("url") == f"{self.page_url}/?shortcut=1"
            and facts.get("has_focus"),
            {
                "page had focus": focused,
                "front": front,
                "view": facts,
                "keys": keys,
                "address heard": self.frame_log[heard:][:12],
            },
        )

        # 8. a page whose process dies comes back by itself
        fid = front.get("id", "")

        def end_process(done):
            view = self.view_of(fid)
            done(view.terminate_web_process() if view else None)

        self.on_main(end_process)
        time.sleep(4)
        crashed = [e for e in self.view_events if e.get("event") == "crashed"]
        alive = self.run_js(fid, "JSON.stringify(document.title)")
        facts = self.view_facts(fid)
        self.check(
            "a crashed page is loaded again",
            bool(crashed)
            and crashed[-1].get("reloaded") is True
            and isinstance(alive, str)
            and facts.get("visible"),
            {"crashed": crashed, "title": alive, "view": facts},
        )
        self.window_picture("08-after-crash")

        # 6. real sites
        for name, url in self.sites():
            self.site(name, url)
        self.window_picture("99-end")

    def hub_frame_rect(self):
        def fn(done):
            def got(v, result):
                try:
                    done(
                        json.loads(
                            v.run_javascript_finish(result).get_js_value().to_string()
                        )
                    )
                except Exception:
                    done(None)

            self.hub.run_javascript(
                "(() => { const f = [...document.querySelectorAll('iframe')]"
                ".find((x) => x.offsetWidth > 0 && (x.src || '').includes(':%d'));"
                " if (!f) return 'null'; const r = f.getBoundingClientRect();"
                " return JSON.stringify([r.left, r.top]); })()" % self.args.port,
                None,
                got,
            )

        return self.on_main(fn)

    def sites(self):
        if self.args.sites == "none":
            return []
        if self.args.sites == "all":
            return SITES
        wanted = self.args.sites.split(",")
        return [s for s in SITES if s[0] in wanted]

    def site(self, name, url):
        started = time.time()
        row: dict = {"url": url}
        try:
            r = self.agent({"op": "open", "url": url, "new_tab": True}, timeout=45)
            row["open_s"] = round(time.time() - started, 1)
            tab = r.get("tab", {})
            time.sleep(self.args.settle)
            page = self.agent(
                {"op": "read", "tab": tab.get("id", ""), "max_chars": 4000}
            )
            p = page.get("page") or {}
            row.update(
                title=p.get("title"),
                final_url=p.get("url"),
                text_chars=len(p.get("text") or ""),
                text=(p.get("text") or "")[:300],
                read_ok=page.get("ok"),
                read_error=p.get("error"),
                view=self.view_facts(tab.get("id", "")),
                events=self.events.get(tab.get("id", ""), []),
                picture=self.snapshot(tab.get("id", ""), f"site-{name}"),
            )
            if tab.get("id"):
                self.agent({"op": "close", "tab": tab["id"]})
        except Exception as e:
            row["error"] = repr(e)
        self.report["sites"][name] = row
        print(
            f"SITE {name}: {row.get('open_s')}s title={row.get('title')!r} "
            f"chars={row.get('text_chars')} events={row.get('events')} "
            f"error={row.get('error') or row.get('read_error')}",
            flush=True,
        )

    def run(self):
        self.start_servers()
        try:
            self.build()
            threading.Thread(target=self.drive, daemon=True).start()
            GLib.timeout_add_seconds(self.args.limit, Gtk.main_quit)
            Gtk.main()
        finally:
            self.backend.terminate()  # a held long-poll would keep it 25 s
            try:
                self.backend.wait(3)
            except subprocess.TimeoutExpired:
                self.backend.kill()
                self.backend.wait(5)
            self.pages.shutdown()
        (self.out / "report.json").write_text(json.dumps(self.report, indent=1))
        failed = [k for k, v in self.report["checks"].items() if not v["ok"]]
        print(
            f"{len(self.report['checks']) - len(failed)}/{len(self.report['checks'])} checks pass"
        )
        return 1 if failed or "error" in self.report else 0


def main():
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--port", type=int, default=8923)
    parser.add_argument("--out", default="/tmp/forge-browser-real")
    parser.add_argument(
        "--sites", default="all", help="all, none or names, comma separated"
    )
    parser.add_argument(
        "--settle", type=float, default=4.0, help="seconds after a load"
    )
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument(
        "--limit", type=int, default=600, help="seconds before giving up"
    )
    sys.exit(Rig(parser.parse_args()).run())


if __name__ == "__main__":
    main()
