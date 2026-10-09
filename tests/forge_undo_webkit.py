"""Real WebKitGTK check for shared/forge_undo.js: real key presses into an
off-screen WebView, in a textarea on the page and in one inside an iframe
(Forge apps run in the hub's iframes). Prints one JSON object of results.

Run by tests/test_forge_undo.py in a child process with compositing off
(off-screen WebKit has no GL here). With FORGE_UNDO_BARE=1 the script is not
loaded, which shows the bug: WebKitGTK binds no key to undo."""

import html
import json
import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, GLib, Gtk, WebKit2  # noqa: E402

SCRIPT = (Path(__file__).parent.parent / "shared" / "forge_undo.js").read_text()
TAG = "" if os.environ.get("FORGE_UNDO_BARE") else f"<script>{SCRIPT}</script>"
INNER = f"<textarea id=t></textarea>{TAG}"
PAGE = (
    f"<textarea id=t></textarea>{TAG}"
    f'<iframe id=f srcdoc="{html.escape(INNER, quote=True)}"></iframe>'
)
CTRL = int(Gdk.ModifierType.CONTROL_MASK)
SHIFT = int(Gdk.ModifierType.SHIFT_MASK)

win = Gtk.OffscreenWindow()
view = WebKit2.WebView()
win.add(view)
win.set_default_size(500, 400)
win.show_all()
results: dict = {}


def press(keyval, state=0):
    keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
    ok, keys = keymap.get_entries_for_keyval(keyval)
    for kind in (Gdk.EventType.KEY_PRESS, Gdk.EventType.KEY_RELEASE):
        event = Gdk.Event.new(kind)
        event.key.window = view.get_window()
        event.key.keyval = keyval
        event.key.state = Gdk.ModifierType(state)
        if ok and keys:
            event.key.hardware_keycode = keys[0].keycode
        seat = Gdk.Display.get_default().get_default_seat()
        event.set_device(seat.get_keyboard())
        win.event(event)


def run_js(code, then):
    def done(v, res):
        value = v.evaluate_javascript_finish(res)
        then(value.to_string() if value else "")

    view.evaluate_javascript(code, -1, None, None, None, done)


VALUE = (
    "(document.activeElement.id === 'f'"
    " ? document.getElementById('f').contentDocument.getElementById('t')"
    " : document.getElementById('t')).value"
)
STEPS = []
for where, focus in (
    ("page", "document.getElementById('t').focus()"),
    (
        "iframe",
        "document.getElementById('f').contentWindow.focus();"
        "document.getElementById('f').contentDocument.getElementById('t').focus()",
    ),
):
    STEPS += [
        (f"{where} focus", lambda f=focus: run_js(f + ";0", lambda _: None)),
        (f"{where} typed", lambda: [press(Gdk.KEY_a), press(Gdk.KEY_b)]),
        (f"{where} ctrl+z", lambda: press(Gdk.KEY_z, CTRL)),
        (f"{where} ctrl+shift+z", lambda: press(Gdk.KEY_Z, CTRL | SHIFT)),
        (f"{where} ctrl+z again", lambda: press(Gdk.KEY_z, CTRL)),
        (f"{where} ctrl+y", lambda: press(Gdk.KEY_y, CTRL)),
    ]
index = [0]


def step():
    if index[0] >= len(STEPS):
        Gtk.main_quit()
        return False
    name, act = STEPS[index[0]]
    index[0] += 1
    act()

    def read():
        run_js(VALUE, lambda v: (results.__setitem__(name, v), step()))
        return False

    GLib.timeout_add(250, read)
    return False


def loaded(_view, event):
    if event == WebKit2.LoadEvent.FINISHED:
        GLib.timeout_add(400, step)


view.connect("load-changed", loaded)
view.load_html(PAGE, "http://localhost/")
GLib.timeout_add(20000, Gtk.main_quit)
Gtk.main()
sys.stdout.write(json.dumps(results) + "\n")
