import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared" / "pad"))
sys.path.insert(0, str(ROOT))
import forge_pad  # noqa: E402
import forge_popout  # noqa: E402


def test_every_configured_action_parses():
    cfg = json.loads(forge_pad.CONFIG.read_text())
    for action in cfg["buttons"].values():
        assert forge_pad.parse_action(action)


def test_chord_keeps_order():
    assert forge_pad.parse_action("key:KEY_LEFTALT+KEY_LEFT") == [56, 105]


def test_stick_deadzone_and_range():
    assert forge_pad.stick(128, 0.12) == 0.0
    assert forge_pad.stick(255, 0.12) == 1.0
    assert forge_pad.stick(0, 0.12) == -1.0
    assert 0 < forge_pad.stick(200, 0.12) < 1


def test_pad_found():
    """Needs the DualSense plugged in or paired; skipped when it is not."""
    if not forge_pad.find_pad("DualSense Wireless Controller"):
        pytest.skip("no DualSense connected")


class FakeWindow:
    """Just enough of a Gtk.Window for track_pad_focus."""

    def __init__(self):
        self.active = False
        self.handlers = {}

    def connect(self, signal, fn):
        self.handlers[signal] = fn

    def is_active(self):
        return self.active

    def focus(self, on=True):
        self.active = on
        self.handlers["notify::is-active"](self)


@pytest.fixture
def flag(tmp_path, monkeypatch):
    """pad-focus in a scratch folder (never the live one forge-pad reads)."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))  # where forge_pad looks
    path = tmp_path / "forge" / "pad-focus"
    monkeypatch.setattr(forge_popout, "PAD_FOCUS", path)
    monkeypatch.setattr(forge_popout, "_focused", {})
    monkeypatch.setattr(forge_popout, "_pad_native", {})
    return path


def test_a_game_in_front_quiets_the_mapper(flag):
    """Exo Lab's game reads the pad itself: while the hub has it in front,
    the flag says 0 and the mapper idles, so presses are not doubled."""
    cfg = json.loads(forge_pad.CONFIG.read_text())
    main, pop = FakeWindow(), FakeWindow()
    forge_popout.track_pad_focus(main, forge_popout.MAIN)
    forge_popout.track_pad_focus(pop, "popout:notes")

    main.focus()
    assert flag.read_text() == "1" and not forge_pad.pad_should_idle(cfg)
    forge_popout.set_pad_native(True)  # the hub: the game is in front
    assert flag.read_text() == "0" and forge_pad.pad_should_idle(cfg)
    main.focus(False)
    pop.focus()  # a popped-out app that does not read the pad gets the mapper
    assert flag.read_text() == "1"
    pop.focus(False)
    main.focus()
    assert flag.read_text() == "0"
    forge_popout.set_pad_native(False)  # back on the Exo Lab page
    assert flag.read_text() == "1" and not forge_pad.pad_should_idle(cfg)
    main.handlers["destroy"](main)
    assert flag.read_text() == "0"


def test_a_popped_out_game_quiets_the_mapper_in_its_own_window(flag):
    """The game in a pop-out says it reads the pad through the pop-out's
    relay (critic F1): only that window's focus stops counting, and closing
    the window forgets it."""
    main, pop = FakeWindow(), FakeWindow()
    forge_popout.track_pad_focus(main)
    forge_popout.track_pad_focus(pop, "popout:exolab")
    pop.focus()
    assert flag.read_text() == "1"
    forge_popout.set_pad_native(True, "popout:exolab")
    assert flag.read_text() == "0"
    pop.focus(False)
    main.focus()  # the hub's app in front is not the game
    assert flag.read_text() == "1"
    main.focus(False)
    pop.focus()
    assert flag.read_text() == "0"
    pop.handlers["destroy"](pop)
    assert "popout:exolab" not in forge_popout._pad_native
    main.focus()
    assert flag.read_text() == "1"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_pop_out_relay_passes_on_pad_messages_only():
    """PAD_RELAY_JS, run in node with a fake window: {forge: "pad"} goes to
    the forgepad handler as "on" or "off", anything else is left alone."""
    harness = """
    const sent = [];
    const heard = [];
    globalThis.addEventListener = (type, fn) => type === "message" && heard.push(fn);
    globalThis.window = { webkit: { messageHandlers: { forgepad: { postMessage: (m) => sent.push(m) } } } };
    eval(process.argv[1]);
    const msgs = [
      { forge: "pad", native: true }, { forge: "visible", visible: false }, null, "pad",
      { forge: "pad", native: false }, { forge: "pad" }, { forge: "pad", native: "yes" },
    ];
    for (const data of msgs) heard.forEach((fn) => fn({ data }));
    console.log(JSON.stringify(sent));
    """
    run = subprocess.run(
        ["node", "-e", harness, forge_popout.PAD_RELAY_JS],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == ["on", "off", "off", "off"]


def test_the_hub_lets_frames_read_the_pad_and_relays_native_pages():
    hub = (ROOT / "hub" / "index.html").read_text()
    found = re.search(r'frame\.allow = "([^"]*)"', hub)
    assert found, "the hub's app frame has no allow list"
    allow = found.group(1).split("; ")
    assert "gamepad" in allow
    assert 'msg.forge === "pad"' in hub and "JSON.stringify({ pad_native: on })" in hub
    visibility = hub.split("function sendVisibility() {", 1)[1].split("\n}\n", 1)[0]
    assert "sendPadNative();" in visibility  # app switches re-send it
    src = (ROOT / "forge.py").read_text()
    assert '"pad_native" in request' in src
    assert "forge_popout.set_pad_native(" in src
    assert "track_pad_focus(win, forge_popout.MAIN)" in src


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_forge_window_focus_reaches_every_app_frame():
    """Critic 2 G5: forge.py hands the main window's focus to the hub, whose
    forgeWindowActive (run here in node on fake frames) posts
    {forge: "focus", focused} to every mounted app; Exo Lab's game pauses pad
    play on focused false (apps/exolab/tests/js/main_pad.mjs)."""
    src = (ROOT / "forge.py").read_text()
    assert 'win.connect("notify::is-active", tell_apps_focus)' in src
    assert "window.forgeWindowActive && window.forgeWindowActive(" in src
    hub = (ROOT / "hub" / "index.html").read_text()
    head = "window.forgeWindowActive = (on) => {"
    body = hub.split(head, 1)[1].split("\n};\n", 1)[0]
    harness = """
    const sent = [];
    const frame = (k) => ({ contentWindow: { postMessage: (m, o) => sent.push([k, m, o]) } });
    const part = (f) => ({ inner: { querySelector: (s) => (s === "iframe" ? f : null) } });
    globalThis.window = {};
    const order = ["notes", "exolab", "home-card", "gone"];
    const parts = { notes: part(frame("notes")), exolab: part(frame("exolab")), "home-card": part(null) };
    eval(process.argv[1]);
    window.forgeWindowActive(false);
    window.forgeWindowActive(true);
    console.log(JSON.stringify(sent));
    """
    run = subprocess.run(
        ["node", "-e", harness, head + body + "\n};"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 0, run.stderr
    said = [[k, m["focused"]] for k, m, origin in json.loads(run.stdout)]
    assert said == [
        ["notes", False],
        ["exolab", False],
        ["notes", True],
        ["exolab", True],
    ]
    assert all(m["forge"] == "focus" for _k, m, _o in json.loads(run.stdout))


def test_a_fresh_hub_page_or_frame_starts_with_the_mapper_on():
    """Critic F2 and F7: a hub reload (a crash) resets the flag in forge.py,
    a new app frame sends the hub's reset on, and closing an app forgets
    what its page said, so a reopened Exo Lab page is not left padless."""
    src = (ROOT / "forge.py").read_text()
    loaded = src.split("def on_hub_loaded(", 1)[1].split("\n\n", 1)[0]
    assert "LoadEvent.COMMITTED" in loaded
    assert "forge_popout.set_pad_native(False)" in loaded
    hub = (ROOT / "hub" / "index.html").read_text()
    mount = hub.split("function mountWorkspace(key) {", 1)[1].split("\n}\n", 1)[0]
    reset = mount.index("padNative[key] = false;")
    assert mount.index("sendPadNative();") > reset
    close = hub.split("function closeWorkspace(key) {", 1)[1].split("\n}\n", 1)[0]
    assert "padNative[key] = false;" in close
