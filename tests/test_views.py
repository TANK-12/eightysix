"""forge_views.ViewHost: real WebKit views laid over the window, off screen.

HOW TO RUN
    WEBKIT_DISABLE_COMPOSITING_MODE=1 /usr/bin/python3 tests/test_views.py

    The system python, like the other hub tests (PyGObject lives there). An
    off-screen GTK window has no GL context, so WebKit's compositing is turned
    off; this file sets that itself before WebKit loads. Needs a desktop
    session (WAYLAND_DISPLAY or DISPLAY) but shows nothing on screen.
"""

import json
import os
import sys
import tempfile
import time

os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")
# WebKitGTK 2.54 on Wayland aborts in an offscreen window without this (no GL
# context for its DMA-BUF renderer); tests/page_probe.py says more.
os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

import forge_views  # noqa: E402

PAGE = "data:text/html,<title>Hello</title><p>page text</p><a href='https://example.com/x'>a link</a>"


def spin(until, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if until():
            return True
        time.sleep(0.02)
    return False


def setup():
    tmp = tempfile.mkdtemp()
    window = Gtk.OffscreenWindow()
    overlay = Gtk.Overlay()
    base = Gtk.Label(label="hub")
    base.set_size_request(800, 600)
    overlay.add(base)
    window.add(overlay)
    window.show_all()
    events = []
    host = forge_views.ViewHost(
        overlay,
        events.append,
        profile=os.path.join(tmp, "p"),
        cache=os.path.join(tmp, "c"),
    )
    host.accounts = forge_views.Path(tmp, "accounts")
    host.accounts_cache = forge_views.Path(tmp, "accounts-cache")
    return host, events, overlay


def test_views_open_position_hide_read_and_close():
    host, events, overlay = setup()
    host.handle({"op": "owner", "owner": "browser"})
    host.handle(
        {
            "op": "create",
            "id": "t1",
            "owner": "browser",
            "url": PAGE,
            "rect": [10, 20, 300, 200],
        }
    )
    assert spin(
        lambda: any(e["event"] == "state" and e["title"] == "Hello" for e in events)
    ), events[-3:]
    view = host.views["t1"]["view"]

    def box():
        # Overlay children get their own GDK window in GTK3, so the widget's
        # allocation is relative to that window; where it really sits is its
        # offset inside the overlay.
        a = view.get_allocation()
        x, y = view.translate_coordinates(overlay, 0, 0)
        return (x, y, a.width, a.height)

    assert spin(lambda: box() == (10, 20, 300, 200)), box()

    host.handle({"op": "rect", "id": "t1", "rect": [0, 40, 500, 300]})
    assert spin(lambda: box() == (0, 40, 500, 300)), box()

    # The hub's bar comes down over the app: views move below it.
    host.handle({"op": "inset", "top": 90})
    assert spin(lambda: box() == (0, 90, 500, 250)), box()
    # The dock peeks up from the bottom of the 600 px window: views end above it.
    host.handle({"op": "inset", "top": 0, "bottom": 300})
    assert spin(lambda: box() == (0, 40, 500, 260)), box()
    host.handle({"op": "inset", "top": 0})

    host.handle({"op": "owner", "owner": "settings"})
    assert spin(
        lambda: not view.get_visible()
    ), "another app is in front; the page must hide"
    host.handle({"op": "owner", "owner": "browser"})
    assert spin(lambda: view.get_visible())

    host.handle({"op": "read", "id": "t1", "request": "r1"})
    assert spin(lambda: any(e["event"] == "read" for e in events))
    page = next(e for e in events if e["event"] == "read")
    assert page["owner"] == "browser" and page["request"] == "r1"
    assert "page text" in page["page"]["text"]
    assert page["page"]["links"][0]["href"] == "https://example.com/x"

    # Anything but a web page or a local file is refused, and the page stays
    # where it was.
    host.handle({"op": "navigate", "id": "t1", "url": "javascript:alert(1)"})
    host.handle({"op": "navigate", "id": "t1", "url": "ftp://example.com/"})
    spin(lambda: False, timeout=0.5)
    assert view.get_uri().startswith("data:text/html")

    # The app may open a file on this computer (a typed path, the Claude
    # panel showing a doc).
    doc = forge_views.Path(tempfile.mkdtemp(), "a note.md")
    doc.write_text("# Local words\n")
    host.handle({"op": "navigate", "id": "t1", "url": doc.as_uri()})
    assert spin(
        lambda: view.get_uri() == doc.as_uri() and not view.is_loading()
    ), view.get_uri()
    host.handle({"op": "read", "id": "t1", "request": "r2"})
    assert spin(lambda: any(e.get("request") == "r2" for e in events))
    page = next(e for e in events if e.get("request") == "r2")
    assert "Local words" in page["page"]["text"]

    host.handle({"op": "close", "id": "t1"})
    assert "t1" not in host.views and view not in overlay.get_children()


def test_imported_cookies_are_in_the_profile_and_expired_ones_are_not():
    host, events, _overlay = setup()
    future = int(time.time()) + 86400
    host.handle(
        {
            "op": "cookies",
            "cookies": [
                {
                    "name": "session",
                    "value": "abc",
                    "host": ".example.com",
                    "path": "/",
                    "expiry": future,
                    "secure": True,
                    "http_only": True,
                    "same_site": 1,
                },
                {
                    "name": "old",
                    "value": "x",
                    "host": ".example.com",
                    "path": "/",
                    "expiry": 1000,
                },
                {"value": "no name"},
            ],
        }
    )
    assert events[-1] == {
        "event": "cookies",
        "id": "",
        "owner": "",
        "count": 1,
        "session": "",
    }

    got = {}

    def done(manager, result):
        got["cookies"] = [c.get_name() for c in manager.get_cookies_finish(result)]

    host.cookies.get_cookies("https://example.com/", None, done)
    assert spin(lambda: "cookies" in got), "cookie manager never answered"
    assert got["cookies"] == ["session"]


def test_each_session_has_its_own_cookies():
    host, events, _overlay = setup()
    cookie = {
        "name": "sid",
        "value": "a",
        "host": ".example.com",
        "path": "/",
        "expiry": int(time.time()) + 86400,  # WebKit keeps no session cookies
        "secure": True,  # SameSite=None cookies must be Secure
    }
    host.handle({"op": "cookies", "session": "claude-a", "cookies": [cookie]})
    assert events[-1]["session"] == "claude-a" and events[-1]["count"] == 1
    for view_id, session in (("va", "claude-a"), ("vb", "claude-b"), ("vc", "../x")):
        host.handle(
            {
                "op": "create",
                "id": view_id,
                "owner": "logins",
                "url": "about:blank",
                "rect": [0, 0, 10, 10],
                "session": session,
            }
        )
    assert host.views["va"]["view"].get_context() is host.session("claude-a")[0]
    assert host.views["vb"]["view"].get_context() is host.session("claude-b")[0]
    # A malformed session name falls back to the Browser's own profile.
    assert host.views["vc"]["view"].get_context() is host.context
    assert (host.accounts / "claude-a" / "webkit").is_dir()

    got = {}

    def reader(name):
        def done(manager, result):
            got[name] = [c.get_name() for c in manager.get_cookies_finish(result)]

        return done

    for name in ("claude-a", "claude-b", ""):
        host.session(name)[1].get_cookies("https://example.com/", None, reader(name))
    assert spin(lambda: len(got) == 3), "cookie managers never answered"
    assert got == {"claude-a": ["sid"], "claude-b": [], "": []}, got


def test_a_view_is_never_created_twice_or_without_an_id():
    host, _events, overlay = setup()
    host.handle(
        {
            "op": "create",
            "id": "a",
            "owner": "x",
            "url": "about:blank",
            "rect": [0, 0, 10, 10],
        }
    )
    host.handle(
        {
            "op": "create",
            "id": "a",
            "owner": "x",
            "url": "about:blank",
            "rect": [0, 0, 10, 10],
        }
    )
    host.handle(
        {
            "op": "create",
            "id": "",
            "owner": "x",
            "url": "about:blank",
            "rect": [0, 0, 10, 10],
        }
    )
    assert list(host.views) == ["a"] and len(overlay.get_children()) == 2
    host.handle({"op": "close-owner", "owner": "x"})
    assert host.views == {}


def _media_site():
    """A tiny local site: /top.html frames /child.html from the other host
    name (localhost vs 127.0.0.1, so a cross-origin frame, like Crunchyroll's
    player), and /direct.html plays in the page itself. The audio is muted:
    the check needs it playing, not heard. Off-screen WebKit never loads the
    clip (no source), but play() and pause() still flip `paused`, which is
    what the button acts on."""
    import http.server
    import threading
    import wave

    root = tempfile.mkdtemp()
    with wave.open(os.path.join(root, "tone.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(8000)
        w.writeframes(bytes(128 for _ in range(8000 * 30)))
    clip = "<audio muted loop autoplay src='tone.wav'></audio>"
    pages = {
        "child.html": f"<title>Child</title>{clip}",
        "direct.html": f"<title>Direct</title>{clip}",
        # plays and pauses by itself, as when the user clicks the page's player
        "self.html": "<title>Self</title><audio muted loop src='tone.wav'></audio><script>"
        "const a = document.querySelector('audio');"
        "setTimeout(() => a.play().catch(() => {}), 1000);"
        "setTimeout(() => a.pause(), 2500);</script>",
    }
    for name, body in pages.items():
        with open(os.path.join(root, name), "w") as f:
            f.write(body)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=root, **k)

        def log_message(self, format, *args):
            pass

    handler = Quiet
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    with open(os.path.join(root, "top.html"), "w") as f:
        f.write(
            f"<title>Top</title><iframe src='http://localhost:{port}/child.html'></iframe>"
        )
    with open(os.path.join(root, "selftop.html"), "w") as f:
        f.write(
            f"<title>SelfTop</title><iframe src='http://localhost:{port}/self.html'></iframe>"
        )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def _media(host, events, view_id, cmd, want):
    """Send a media command and wait for a report that matches `want`."""
    start = len(events)

    def seen():
        for e in events[start:]:
            if e["event"] == "media" and e["id"] == view_id and want(e):
                return True
        host.handle({"op": "media", "id": view_id, "cmd": "state"})
        return False

    host.handle({"op": "media", "id": view_id, "cmd": cmd})
    return spin(seen, timeout=10)


def test_the_music_button_can_pause_what_a_view_plays():
    server, port = _media_site()
    try:
        host, events, _overlay = setup()
        host.handle({"op": "owner", "owner": "media"})
        for vid, page in (("direct", "direct.html"), ("framed", "top.html")):
            host.handle(
                {
                    "op": "create",
                    "id": vid,
                    "owner": "media",
                    "url": f"http://127.0.0.1:{port}/{page}",
                    "rect": [0, 0, 400, 300],
                }
            )
        for vid in ("direct", "framed"):
            # the page (and its frame) loads first; then the button starts it
            assert _media(host, events, vid, "state", lambda e: e["has"]), vid
            assert _media(
                host, events, vid, "play", lambda e: e["has"] and not e["paused"]
            ), f"{vid} never reported playing: {[e for e in events if e['event'] == 'media'][-2:]}"
            assert _media(host, events, vid, "pause", lambda e: e["paused"]), vid
            assert _media(host, events, vid, "toggle", lambda e: not e["paused"]), vid
            assert _media(host, events, vid, "toggle", lambda e: e["paused"]), vid
        last = [e for e in events if e["event"] == "media" and e["id"] == "direct"][-1]
        assert last["owner"] == "media" and last["title"] == "Direct"

        # no id asks every view
        start = len(events)
        host.handle({"op": "media", "cmd": "state"})
        assert spin(
            lambda: {e["id"] for e in events[start:] if e["event"] == "media"}
            == {"direct", "framed"}
        )
    finally:
        server.shutdown()


def test_a_page_that_plays_or_pauses_reports_it_at_once():
    """Emerson 2026-09-27: the background music stepped aside too slowly for
    YouTube in a view, because the hub only asked views every 3 s. A view now
    says so itself the moment its media plays or pauses, in a frame too."""
    server, port = _media_site()
    try:
        host, events, _overlay = setup()
        host.handle({"op": "owner", "owner": "media"})
        for vid, page in (("self", "self.html"), ("selfframed", "selftop.html")):
            host.handle(
                {
                    "op": "create",
                    "id": vid,
                    "owner": "media",
                    "url": f"http://127.0.0.1:{port}/{page}",
                    "rect": [0, 0, 400, 300],
                }
            )

        def reports(vid):
            return [
                e["paused"]
                for e in events
                if e["event"] == "media" and e["id"] == vid and e["has"]
            ]

        # nobody asks: every report here was pushed by the page
        for vid in ("self", "selfframed"):
            assert spin(
                lambda: False in reports(vid) and reports(vid)[-1] is True, timeout=10
            ), f"{vid}: {reports(vid)}"
    finally:
        server.shutdown()


def test_a_page_cannot_report_more_than_media_fields():
    faked = forge_views.media_state(
        {
            "has": 1,
            "owner": "settings",
            "id": "x",
            "title": 5,
            "volume": 9,
            "current": "nan",
        }
    )
    assert set(faked) == {
        "has",
        "paused",
        "title",
        "artist",
        "current",
        "duration",
        "volume",
        "video",
    }
    assert faked["volume"] == 1.0 and faked["current"] == 0.0 and faked["title"] == "5"
    assert forge_views.media_state("nope") == {"has": False}


def run_js(view, script):
    """A script's result in the page, as a string (None if it failed)."""
    out = {}

    def done(v, result):
        try:
            out["v"] = v.run_javascript_finish(result).get_js_value().to_string()
        except GLib.Error:
            out["v"] = None

    view.run_javascript(script, None, done)
    spin(lambda: "v" in out)
    return out.get("v")


def test_speed_and_detail_reaches_the_pages():
    """Settings > Speed and detail: the frame cap, the video caps and smooth
    scrolling apply to a page already open and to one opened afterwards."""
    host, events, _overlay = setup()
    host.handle({"op": "owner", "owner": "browser"})
    host.handle({"op": "create", "id": "p1", "owner": "browser", "url": PAGE})
    assert spin(
        lambda: any(e["event"] == "state" and e["title"] == "Hello" for e in events)
    )
    view = host.views["p1"]["view"]
    assert run_js(view, "String(window.ForgeFrameCap.fps)") == "60"
    assert view.get_settings().get_property("enable-smooth-scrolling") is True

    host.set_power(
        {"max_fps": 24, "video_fps": 30, "video_height": "720", "smooth_scroll": False}
    )
    assert spin(lambda: run_js(view, "String(window.ForgeFrameCap.fps)") == "24")
    sixty = 'video/webm; codecs="vp9"; width=1280; height=720; framerate=60'
    assert (
        run_js(view, f"String(window.ForgeWebCap.allowed({json.dumps(sixty)}))")
        == "false"
    )
    assert view.get_settings().get_property("enable-smooth-scrolling") is False

    host.handle(
        {
            "op": "create",
            "id": "p2",
            "owner": "browser",
            "url": PAGE.replace("Hello", "Two"),
        }
    )
    assert spin(
        lambda: any(e["event"] == "state" and e["title"] == "Two" for e in events)
    )
    later = host.views["p2"]["view"]
    assert run_js(later, "String(window.ForgeFrameCap.fps)") == "24"
    host.handle({"op": "close", "id": "p1"})
    host.handle({"op": "close", "id": "p2"})


def test_the_first_view_shows_for_the_app_the_hub_already_put_in_front():
    """forge.py's view_handler. Opening an app, the hub sends owner and inset
    before the app's page has asked for its first view, so before there is a
    ViewHost. They reach the host when it is made, and the first page shows at
    once; dropped, it stayed hidden until another app was opened (the Browser
    that "never works", 2026-10-08)."""
    import forge

    tmp = tempfile.mkdtemp()
    window = Gtk.OffscreenWindow()
    overlay = Gtk.Overlay()
    base = Gtk.Label(label="hub")
    base.set_size_request(800, 600)
    overlay.add(base)
    window.add(overlay)
    window.show_all()
    events = []
    view_host: dict = {"host": None}

    def make():
        return forge_views.ViewHost(
            overlay,
            events.append,
            profile=os.path.join(tmp, "p"),
            cache=os.path.join(tmp, "c"),
        )

    handle = forge.view_handler(view_host, make, lambda: 2.0)
    handle({"op": "owner", "owner": None})
    handle({"op": "owner", "owner": "browser"})
    handle({"op": "inset", "top": 30, "bottom": 0})
    handle({"op": "rect", "id": "t1", "rect": [0, 0, 10, 10]})
    assert view_host.get("host") is None, "no WebKit profile before a view is asked for"

    handle(
        {
            "op": "create",
            "id": "t1",
            "owner": "browser",
            "url": PAGE,
            "rect": [10, 20, 300, 200],
        }
    )
    host = view_host["host"]
    assert host.owner == "browser"
    view = host.views["t1"]["view"]
    assert spin(lambda: view.get_visible() and view.get_allocated_width() == 600)
    # rect and inset are CSS pixels, doubled by the zoom: the view starts at
    # y 40 but keeps clear of the 60 px inset
    x, y = view.translate_coordinates(overlay, 0, 0)
    where = (x, y, view.get_allocated_width(), view.get_allocated_height())
    assert where == (20, 60, 600, 380), where

    handle({"op": "owner", "owner": None})
    assert not view.get_visible()
    handle({"op": "owner", "owner": "browser"})
    assert view.get_visible()
    handle({"op": "close", "id": "t1"})
    assert not host.views
    window.destroy()


def test_only_the_app_may_open_a_local_file_never_a_page():
    assert forge_views.allowed("file:///tmp/a.md", local=True)
    # a page's own new-window links go through allowed() without local
    assert not forge_views.allowed("file:///tmp/a.md")
    assert not forge_views.allowed("javascript:alert(1)", local=True)
    assert not forge_views.allowed("file://host/share/a", local=True)
    assert forge_views.allowed("https://a.org/")


def test_a_page_whose_process_dies_is_loaded_again_once_then_left_down():
    host, events, _overlay = setup()
    host.handle({"op": "owner", "owner": "browser"})
    host.handle(
        {
            "op": "create",
            "id": "c",
            "owner": "browser",
            "url": PAGE,
            "rect": [0, 0, 200, 100],
        }
    )
    view = host.views["c"]["view"]
    assert spin(lambda: view.get_title() == "Hello" and not view.is_loading())

    def crashes():
        return [e for e in events if e["event"] == "crashed"]

    view.terminate_web_process()
    assert spin(lambda: len(crashes()) == 1), events[-3:]
    assert crashes()[0]["reloaded"] is True and crashes()[0]["owner"] == "browser"
    # it comes back by itself
    assert spin(lambda: view.get_title() == "Hello" and not view.is_loading())
    assert run_js(view, "document.title") == "Hello"

    # A second death soon after is not chased: the app says so instead.
    view.terminate_web_process()
    assert spin(lambda: len(crashes()) == 2), events[-3:]
    assert crashes()[1]["reloaded"] is False
    assert crashes()[1]["reason"] == "terminated-by-api"


KEYS_PAGE = (
    "data:text/html,<title>keys</title><input id=i autofocus><script>"
    "window.seen=[];addEventListener('keydown',e=>{seen.push((e.ctrlKey?'ctrl+':'')+e.key);"
    "if(e.ctrlKey&&e.key==='d')e.preventDefault();})</script>"
)


def press(window, keyval, state=0):
    """A real key press and release through GTK, to whatever has the keyboard."""
    from gi.repository import Gdk

    seat = Gdk.Display.get_default().get_default_seat()
    for kind in (Gdk.EventType.KEY_PRESS, Gdk.EventType.KEY_RELEASE):
        event = Gdk.Event.new(kind)
        event.key.window = window.get_window()
        event.key.keyval = keyval
        event.key.state = Gdk.ModifierType(state)
        event.key.time = int(GLib.get_monotonic_time() / 1000)
        if seat.get_keyboard() is not None:
            event.set_device(seat.get_keyboard())
        Gtk.main_do_event(event)
        spin(lambda: False, timeout=0.15)


def test_an_apps_shortcuts_reach_it_while_a_page_has_the_keyboard():
    from gi.repository import Gdk

    host, events, overlay = setup()
    window = overlay.get_toplevel()
    host.handle({"op": "owner", "owner": "browser"})
    host.handle(
        {
            "op": "create",
            "id": "k",
            "owner": "browser",
            "url": KEYS_PAGE,
            "rect": [0, 0, 300, 200],
            "keys": ["ctrl+l", "ctrl+d", "f5", 7, "x" * 99],
            "keys_first": ["Ctrl+Shift+T", "ctrl+w"],
        }
    )
    view = host.views["k"]["view"]
    assert spin(lambda: view.get_title() == "keys" and not view.is_loading())
    focus_in = Gdk.Event.new(Gdk.EventType.FOCUS_CHANGE)
    focus_in.focus_change.window = window.get_window()
    focus_in.focus_change.in_ = 1
    focus_in.focus_change.send_event = 1
    Gtk.main_do_event(focus_in)
    view.grab_focus()
    assert spin(lambda: window.get_focus() is view)
    ctrl, shift = Gdk.ModifierType.CONTROL_MASK, Gdk.ModifierType.SHIFT_MASK

    press(window, Gdk.KEY_T, ctrl | shift)  # first: the page never sees it
    press(window, Gdk.KEY_l, ctrl)  # the page leaves it: the app's
    # Num Lock and other locks do not change what was pressed
    press(window, Gdk.KEY_F5, Gdk.ModifierType.MOD2_MASK)
    press(window, Gdk.KEY_d, ctrl)  # the page takes it: stays the page's
    press(window, Gdk.KEY_F5, Gdk.ModifierType.SUPER_MASK)  # not plain F5
    press(window, Gdk.KEY_a)  # typing is the page's
    keys = [e["combo"] for e in events if e["event"] == "key"]
    assert keys == ["ctrl+shift+t", "ctrl+l", "f5"], keys
    assert all(e["id"] == "k" for e in events if e["event"] == "key")
    seen = json.loads(run_js(view, "JSON.stringify(window.seen)") or "[]")
    assert "ctrl+T" not in seen and "ctrl+d" in seen, seen
    assert key_names(Gdk.KEY_F5, Gdk.ModifierType.SUPER_MASK) == "super+f5"
    assert key_names(Gdk.KEY_l, ctrl | Gdk.ModifierType.MOD5_MASK) == "ctrl+altgr+l"

    # The app hands the keyboard back to the page, but only to one that shows.
    window.set_focus(None)
    host.handle({"op": "hide", "id": "k"})
    host.handle({"op": "focus", "id": "k"})
    host.handle({"op": "show", "id": "k"})
    host.handle({"op": "owner", "owner": "settings"})
    host.handle({"op": "focus", "id": "k"})
    spin(lambda: False, timeout=0.3)
    assert window.get_focus() is not view
    host.handle({"op": "owner", "owner": "browser"})
    host.handle({"op": "focus", "id": "k"})
    assert spin(lambda: window.get_focus() is view), window.get_focus()


def key_names(keyval, state):
    from gi.repository import Gdk

    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.key.keyval = keyval
    event.key.state = Gdk.ModifierType(state)
    return forge_views.key_combo(event)


def test_a_crashed_page_is_never_sent_as_a_form_again():
    import http.server
    import threading

    posts = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.reply(
                b"<title>form</title><form method=post><button id=b>go</button></form>"
            )

        def do_POST(self):
            posts.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.reply(b"<title>sent</title>sent")

        def reply(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/f"
    host, events, _overlay = setup()
    host.handle({"op": "owner", "owner": "browser"})
    host.handle(
        {
            "op": "create",
            "id": "p",
            "owner": "browser",
            "url": url,
            "rect": [0, 0, 200, 100],
        }
    )
    view = host.views["p"]["view"]
    assert spin(lambda: view.get_title() == "form" and not view.is_loading())
    run_js(view, "document.getElementById('b').click(); 'ok'")
    assert spin(lambda: view.get_title() == "sent" and not view.is_loading())
    assert len(posts) == 1
    view.terminate_web_process()
    assert spin(lambda: any(e["event"] == "crashed" for e in events))
    assert spin(lambda: view.get_title() == "form" and not view.is_loading())
    assert len(posts) == 1, posts
    server.shutdown()


def test_a_local_file_webkit_cannot_show_says_so_and_is_not_copied():
    host, events, _overlay = setup()
    host.handle({"op": "owner", "owner": "browser"})
    host.handle(
        {
            "op": "create",
            "id": "u",
            "owner": "browser",
            "url": "about:blank",
            "rect": [0, 0, 200, 100],
        }
    )
    # (a PDF shows: WebKit has its own viewer) left alone, a zip would be
    # copied into Downloads, which is no way to open a file
    archive = forge_views.Path(tempfile.mkdtemp(), "a.zip")
    archive.write_bytes(b"PK\x05\x06" + bytes(18))
    host.handle({"op": "navigate", "id": "u", "url": archive.as_uri()})
    assert spin(lambda: any(e["event"] == "unshown" for e in events)), events[-3:]
    said = next(e for e in events if e["event"] == "unshown")
    assert said["url"] == archive.as_uri() and said["mime"] == "application/zip"
    assert not any(e["event"] == "download" for e in events)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS :: {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL :: {name} :: {e}")
    print()
    print("ALL PASS" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
