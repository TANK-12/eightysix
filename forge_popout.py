"""Pop an app out of Forge into its own window, on another screen (A22).

Emerson has one screen most of the time and two or three more some days. An
app in the hub is an iframe in Forge's one window, so it can only ever be on
the screen Forge is on. A pop-out is a second Gtk window with its own WebKit
view on the app's own address (the same backend the hub uses), so the app
can sit on a second monitor while Forge stays on the first.

Where it goes: with more than one monitor, the pop-out fills a monitor Forge
is not on, the pointer's first if the pointer is on one, else the next one
along. With one monitor it opens as a normal window beside Forge. F11
toggles its full screen, Esc leaves it, and "Back into Forge" in its title
bar closes it and brings the app to the front in the hub.

`pick_monitor` is the pure choice (tested); `PopOuts` does the Gtk side.
"""

import os
import urllib.parse
from pathlib import Path


def local_page(uri: str | None) -> bool:
    """A Forge page: a file, or a server on this laptop."""
    u = urllib.parse.urlsplit(uri or "")
    if u.scheme == "file":
        return True
    host = u.hostname or ""
    return u.scheme in ("http", "https") and host in ("127.0.0.1", "localhost", "::1")


def media_request_ok(
    audio: bool, video: bool, display: bool = False, uri: str | None = None
) -> bool:
    """A page in a Forge window asked for a microphone, camera or screen. The
    microphone alone is allowed (Acchan's voice button, 2026-09-27), and only
    while the window shows a Forge page (`uri`): a pop-out that followed a
    link to a website gets no microphone. The camera and the screen never.
    Sites in the Browser app are separate views and are not affected."""
    return audio and not video and not display and local_page(uri)


def allow_microphone(view):
    """Let the pages in a WebKit view ask for the microphone, answered by
    media_request_ok. Forge's window and every pop-out call this; a pop-out
    without it refused its app's mic button (Relay task 120)."""
    import gi

    gi.require_version("WebKit2", "4.1")
    from gi.repository import WebKit2

    view.get_settings().set_property("enable-media-stream", True)

    def on_permission(_view, request):
        if isinstance(request, WebKit2.UserMediaPermissionRequest):
            props = request.props
            # WebKit 2.54 has no is-for-display-device property, only this
            screen = getattr(
                WebKit2, "user_media_permission_is_for_display_device", None
            )
            ok = media_request_ok(
                bool(props.is_for_audio_device),
                bool(props.is_for_video_device),
                bool(screen(request)) if screen else False,
                _view.get_uri(),
            )
            request.allow() if ok else request.deny()
            return True
        return False

    view.connect("permission-request", on_permission)
    return on_permission


def pick_monitor(count, home, pointer=None):
    """Which monitor a pop-out goes to, and whether it fills it.

    `count` monitors, Forge on monitor `home`, the pointer on `pointer`
    (None when unknown: Wayland only tells a window where the pointer is while
    it is over that window). Returns (monitor index, fill).
    """
    if count <= 1:
        return 0, False
    home = home if isinstance(home, int) and 0 <= home < count else 0
    if isinstance(pointer, int) and 0 <= pointer < count and pointer != home:
        return pointer, True
    return (home + 1) % count, True


def window_title(label):
    return f"{label} - Forge"


def _monitor_index(display, monitor):
    for i in range(display.get_n_monitors()):
        if display.get_monitor(i) == monitor:
            return i
    return None


PAD_FOCUS = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "forge" / "pad-focus"
MAIN = "main"  # the main window's key; a pop-out's is "popout:<app>"
_focused = {}  # id(window) -> that window's key, while it has focus
_pad_native = {}  # window key -> True while its page reads the pad itself


def _write_pad_focus():
    # A focused Forge window counts unless the page in it reads the pad
    # itself (a game): then shared/pad sends no mouse or keys, so a press is
    # not done twice.
    on = any(not _pad_native.get(key) for key in _focused.values())
    PAD_FOCUS.parent.mkdir(parents=True, exist_ok=True)
    PAD_FOCUS.write_text("1" if on else "0")


def set_pad_native(on, key=MAIN):
    """Whether the page in window `key` reads the PS5 pad itself (for the
    main window, the hub's app in front); shared/pad goes quiet while it
    does."""
    _pad_native[key] = bool(on)
    _write_pad_focus()


def track_pad_focus(win, key=MAIN):
    """Keep PAD_FOCUS at 1 while any Forge window has focus (shared/pad reads
    it), but not a window whose page reads the pad itself."""

    def changed(w, _param=None, gone=False):
        if w.is_active() and not gone:
            _focused[id(w)] = key
        else:
            _focused.pop(id(w), None)
        if gone:
            _pad_native.pop(key, None)
        _write_pad_focus()

    win.connect("notify::is-active", changed)
    win.connect("destroy", lambda w: changed(w, gone=True))


# In a pop-out the app's page is the top window, so a game's
# {forge: "pad", native} (posted to window.parent, which is the page itself
# there) has no hub to hear it. This script hears it in the pop-out's top
# frame and hands it to forge_popout through the "forgepad" handler.
PAD_RELAY_JS = """
addEventListener("message", (e) => {
  const d = e.data;
  if (!d || d.forge !== "pad") return;
  try {
    window.webkit.messageHandlers.forgepad.postMessage(d.native === true ? "on" : "off");
  } catch (err) {}
});
"""


def _js_text(result):
    value = result.get_js_value() if hasattr(result, "get_js_value") else result
    return value.to_string()


def relay_pad_native(view, key):
    """Let a page in `view` (a pop-out window) say it reads the pad, as a
    game in the hub does; each new page starts as not reading it."""
    from gi.repository import WebKit2

    content = view.get_user_content_manager()
    content.add_script(
        WebKit2.UserScript.new(
            PAD_RELAY_JS,
            WebKit2.UserContentInjectedFrames.TOP_FRAME,
            WebKit2.UserScriptInjectionTime.START,
            None,
            None,
        )
    )
    content.register_script_message_handler("forgepad")
    content.connect(
        "script-message-received::forgepad",
        lambda _m, result: set_pad_native(_js_text(result) == "on", key),
    )

    def on_load(_view, event):
        if event == WebKit2.LoadEvent.COMMITTED:
            set_pad_native(False, key)

    view.connect("load-changed", on_load)


class PopOuts:
    """One pop-out window per app, made on demand.

    `on_back(name)` runs when "Back into Forge" is pressed; `open_link(uri)`
    takes links that want a new window (same rule as the main window).
    """

    def __init__(self, home_window, on_back, open_link, zoom=1.0):
        self.home = home_window
        self.on_back = on_back
        self.open_link = open_link
        self.zoom = zoom
        self.windows = {}

    def open(self, name, label, url):
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("WebKit2", "4.1")
        from gi.repository import Gdk, Gtk, WebKit2

        if name in self.windows:
            self.windows[name].present()
            return self.windows[name]
        win = Gtk.Window()
        key = f"popout:{name}"
        track_pad_focus(win, key)
        win.set_default_size(1200, 800)
        bar = Gtk.HeaderBar(show_close_button=True)  # shows the window title
        back = Gtk.Button(label="Back into Forge")
        back.set_tooltip_text("Close this window and show the app in Forge")
        bar.pack_start(back)
        win.set_titlebar(bar)
        win.set_title(window_title(label))  # set_titlebar clears it
        view = WebKit2.WebView()
        view.set_zoom_level(self.zoom)
        allow_microphone(view)
        relay_pad_native(view, key)

        def on_create(_view, action):
            self.open_link(action.get_request().get_uri())
            return None

        def on_policy(_view, decision, kind):
            if kind == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION:
                self.open_link(decision.get_navigation_action().get_request().get_uri())
                decision.ignore()
                return True
            return False

        view.connect("create", on_create)
        view.connect("decide-policy", on_policy)
        view.load_uri(url)
        win.add(view)
        state = {"full": False}

        def on_state(_w, event):
            state["full"] = bool(event.new_window_state & Gdk.WindowState.FULLSCREEN)
            return False

        def on_key(_w, event):
            if event.keyval == Gdk.KEY_F11:
                win.unfullscreen() if state["full"] else win.fullscreen()
                return True
            if event.keyval == Gdk.KEY_Escape and state["full"]:
                win.unfullscreen()
                return True
            return False

        def on_back(_b):
            win.destroy()
            self.on_back(name)

        win.connect("window-state-event", on_state)
        win.connect("key-press-event", on_key)
        win.connect("destroy", lambda _w: self.windows.pop(name, None))
        back.connect("clicked", on_back)
        self.windows[name] = win
        win.show_all()
        self._place(win)
        return win

    def _place(self, win):
        from gi.repository import Gdk

        display = Gdk.Display.get_default()
        count = display.get_n_monitors()
        home = None
        if self.home is not None and self.home.get_window() is not None:
            home = _monitor_index(
                display, display.get_monitor_at_window(self.home.get_window())
            )
        pointer = None
        try:
            _screen, x, y = display.get_default_seat().get_pointer().get_position()
            pointer = _monitor_index(display, display.get_monitor_at_point(x, y))
        except Exception:
            pass  # no pointer position (Wayland, pointer elsewhere)
        index, fill = pick_monitor(count, home, pointer)
        if fill:
            win.fullscreen_on_monitor(win.get_screen(), index)

    def set_zoom(self, zoom):
        self.zoom = zoom
        for win in self.windows.values():
            win.get_child().set_zoom_level(zoom)

    def close_all(self):
        for win in list(self.windows.values()):
            win.destroy()
