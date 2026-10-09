#!/usr/bin/env python3
"""Forge -- one desktop window hosting NovelForge, MediaForge and AI Studio.

WHAT THIS IS
    A thin orchestrator. It owns no application logic at all. Each tool keeps
    its own FastAPI backend, its own virtualenv and its own port, exactly as
    it runs standalone; this launcher starts them, shows one GTK/WebKit window
    with a sidebar shell, and stops every backend again when the window
    closes.

LAYOUT
    Forge/
      forge.py            this file
      README.md           architecture + how to add or change an app
      apps/<name>/        one self-contained tool, each with a forge_app.json
      groups/<id>.json    optional: one tile standing for several apps, which
                          join it with "group": "<id>" in their manifest
      shared/             forge.css + forge.js, served by every app backend
      hub/                the sidebar shell (index.html) + generated status.js
      outputs/            per-backend logs
      backups/            pre-edit copies (there is no version control here)

ADDING AN APP
    Drop it in apps/ with a forge_app.json next to a .venv and a FastAPI app.
    Nothing in this file needs editing -- the list below is discovered, not
    declared. See README.md for the manifest fields and the frontend contract.

STARTUP
    Backends start concurrently and the window opens immediately rather than
    waiting for all three (which used to serialise up to three 180s waits).
    A workspace whose backend is not up yet shows a "starting" card and mounts
    itself as soon as the readiness poll reports it live. The window opens on
    the home screen, so nothing waits on an app page to load. Readiness is a
    TCP connect on the app's port every 0.1 s (every backend measured 0.25 to
    0.9 s to its first accepted connection), and an app's start or stop asked
    for by the hub runs on a worker thread, never on the GTK main loop.

LOOK
    hub/index.html is a Hyprland-style home screen: the wallpaper, a top bar of
    app workspaces, launcher tiles and a dock, plus optional particles over the
    wallpaper and background music from a folder (Settings > Home screen; the
    tracks reach the hub as file:// links inside theme.js). shared/forge_theme.py turns
    ~/.config/forge/settings.json into hub/theme.js at launch, and the app
    whose manifest says "role": "settings" changes it live.

CLOSING
    The window hides the moment it is closed, then every backend is sent
    SIGTERM at once. Measured: each exits 0.15-0.2 s after SIGTERM, so stopping
    them one after another kept the window on screen for about 2.2 s.
"""

import base64
import glob
import json
import os
import signal
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
# Gdk must be pinned too: with GTK4 installed system-wide, a bare Gdk import
# resolves to 4.0 and then clashes with the Gtk 3.0 we require here.
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, Gtk, WebKit2, GLib  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
APPS_DIR = os.path.join(ROOT, "apps")
GROUPS_DIR = os.path.join(ROOT, "groups")
SECTIONS_DIR = os.path.join(ROOT, "sections")
HUB_DIR = os.path.join(ROOT, "hub")
SHELL_URL = "file://" + os.path.join(HUB_DIR, "index.html")
SHARED_DIR = os.path.join(ROOT, "shared")

# App size (Settings > Look) is WebKit page zoom on the one view that holds the
# hub and every app, so pages lay out again at the new size. CSS zoom inside
# each app used to do this and stretched anything sized to the window past its
# edge: content off centre and a sideways scrollbar.
PAGE_ZOOM_MIN = 0.5
PAGE_ZOOM_MAX = 2.0


# Forge's own keys. The table of actions and default keys is
# shared/forge_theme.py HUB_KEYS (Settings shows it); this turns "Alt+F" into
# something a GTK key press can be matched against.
KEY_MODS = {
    "alt": Gdk.ModifierType.MOD1_MASK,
    "ctrl": Gdk.ModifierType.CONTROL_MASK,
    "control": Gdk.ModifierType.CONTROL_MASK,
    "shift": Gdk.ModifierType.SHIFT_MASK,
    "super": Gdk.ModifierType.SUPER_MASK,
}
KEY_MOD_MASK = int(
    Gdk.ModifierType.MOD1_MASK
    | Gdk.ModifierType.CONTROL_MASK
    | Gdk.ModifierType.SHIFT_MASK
    | Gdk.ModifierType.SUPER_MASK
)
KEY_NAMES = {
    "space": "space",
    "left": "Left",
    "right": "Right",
    "up": "Up",
    "down": "Down",
    "return": "Return",
    "enter": "Return",
    "tab": "Tab",
    "esc": "Escape",
    "escape": "Escape",
    "`": "grave",
}


def parse_key(text):
    """ "Alt+F" -> (keyval, modifier mask); None when it names no real key."""
    parts = [p.strip() for p in str(text or "").split("+")]
    if not parts[-1]:
        return None
    mods = 0
    for part in parts[:-1]:
        mod = KEY_MODS.get(part.lower())
        if mod is None:
            return None
        mods |= int(mod)
    name = parts[-1]
    name = KEY_NAMES.get(name.lower(), name if len(name) > 1 else name.lower())
    keyval = Gdk.keyval_from_name(name)
    if keyval in (0, Gdk.KEY_VoidSymbol):
        return None
    return keyval, mods


def _parse_keys(text):
    return [k for k in (parse_key(part) for part in str(text or "").split(",")) if k]


def key_table(overrides=None):
    """Every hub action and its keys: the defaults, with Settings' overrides.
    A broken override keeps the default rather than losing the action."""
    if SHARED_DIR not in sys.path:
        sys.path.insert(0, SHARED_DIR)
    import forge_theme

    overrides = overrides if isinstance(overrides, dict) else {}
    return {
        action: _parse_keys(overrides.get(action)) or _parse_keys(default)
        for action, default in forge_theme.HUB_KEYS.items()
    }


def key_action(keyval, state, table):
    """The action a key press asks for, or None. Num Lock and Caps Lock are
    ignored; any other extra modifier means it is a different key."""
    mods = int(state) & KEY_MOD_MASK
    lower = Gdk.keyval_to_lower(keyval)
    for action, keys in table.items():
        if (lower, mods) in keys:
            return action
    return None


def restore_plan(before):
    """How the window comes back from full screen: as it was before, or
    maximised when there was no before (Start full screen)."""
    if not before or before.get("maximized"):
        return ("maximize",)
    width, height = before["size"]
    return ("resize", width, height)


class FullScreen:
    """Why the window fills the screen, kept as three separate wishes.

    desktop: Start full screen, or F11 on the home screen. The window is the
             desktop and the hub keeps its bar and dock.
    app:     the open app fills the screen with no bar or dock: the bar's
             Full screen, Alt+F or F11 inside an app, or the app's own button.
    element: the page holds real element full screen (a video's own button).

    The window is full screen while any of them holds, and the hub hides its
    chrome for `app` only. These used to be one flag, so with Start full
    screen on, leaving an app's full screen took the whole window out of full
    screen, and the bar's button did nothing because the window already was.
    """

    def __init__(self, desktop=False):
        self.desktop = bool(desktop)
        self.app = False
        self.element = False

    @property
    def window(self):
        return self.desktop or self.app or self.element

    def set_app(self, on):
        self.app = bool(on)

    def set_element(self, on):
        self.element = bool(on)

    def key(self, app_open):
        """Alt+F / F11 step through three levels, then round again: a normal
        window under the desktop's top bar, the window full screen with the
        hub's bar kept, then the open app alone with the bar on hover. On the
        home screen there is no app to fill it, so only the first two."""
        if self.app or (self.desktop and not app_open):
            self.desktop = self.app = False
        elif self.desktop:
            self.app = True
        else:
            self.desktop = True

    def escape(self):
        """Whether Esc was for full screen. During element full screen it is
        the page's: WebKit leaves it and leave-fullscreen follows."""
        if self.app and not self.element:
            self.app = False
            return True
        return False

    def window_left(self):
        """The window manager took full screen away (its own key, a drag)."""
        self.desktop = self.app = self.element = False


if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)
# Whether anyone can see the window (B34, task 60): the compositor, the
# window's state and the GNOME extension's answer in one place.
from forge_seen import Seen, watch_shell  # noqa: E402

# The mic permission for a page in Forge's window or a pop-out (one rule).
from forge_popout import allow_microphone, media_request_ok  # noqa: E402,F401


def thumb_png(surface, rect=None, width=480, scale=1.0):
    """A card-sized PNG of one area of a window snapshot, for the Alt+Space
    overview. `rect` is in page pixels; `scale` turns those into the
    snapshot's (App size zoom times the screen's pixel density). Areas smaller
    than `width` are not blown up."""
    import io

    import cairo

    sw, sh = surface.get_width(), surface.get_height()
    try:
        x, y, w, h = (int(round(float(v) * scale)) for v in rect or ())
    except (TypeError, ValueError):
        x, y, w, h = 0, 0, sw, sh
    x, y = max(0, min(x, sw - 1)), max(0, min(y, sh - 1))
    w, h = max(1, min(w, sw - x)), max(1, min(h, sh - y))
    k = min(1.0, width / w)
    out = cairo.ImageSurface(
        cairo.FORMAT_ARGB32, max(1, round(w * k)), max(1, round(h * k))
    )
    ctx = cairo.Context(out)
    ctx.scale(k, k)
    ctx.set_source_surface(surface, -x, -y)
    ctx.paint()
    buf = io.BytesIO()
    out.write_to_png(buf)
    return buf.getvalue()


def frame_thumb(widget, rect=None, width=480, scale=1.0):
    """A card-sized picture of one area of the frame `widget` shows now, for
    the Alt+Space overview, or None when that frame is blank (the window not
    drawn yet). Drawn from the frame already on screen: WebKit's own
    get_snapshot() made the page's process repaint the whole window in
    software first, 0.25-0.32 s with the page frozen, after every app opened
    (measured 2026-10-08; drawing the frame took about 75 ms and the page
    kept running). `rect` and `scale` as in thumb_png, in widget pixels."""
    import cairo

    ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
    try:
        x, y, w, h = (int(round(float(v) * scale)) for v in rect or ())
    except (TypeError, ValueError):
        x, y, w, h = 0, 0, ww, wh
    x, y = max(0, min(x, ww - 1)), max(0, min(y, wh - 1))
    w, h = max(1, min(w, ww - x)), max(1, min(h, wh - y))
    k = min(1.0, width / w)
    out = cairo.ImageSurface(
        cairo.FORMAT_ARGB32, max(1, round(w * k)), max(1, round(h * k))
    )
    ctx = cairo.Context(out)
    ctx.scale(k, k)
    ctx.translate(-x, -y)
    widget.draw(ctx)
    out.flush()
    if not any(bytes(out.get_data())[3::64]):  # every sampled pixel see-through
        return None
    return out


def png_bytes(surface):
    """A cairo surface as PNG bytes; safe on a worker thread."""
    import io

    buf = io.BytesIO()
    surface.write_to_png(buf)
    return buf.getvalue()


def save_hub_settings(changes, path=None):
    """Save what the hub itself may change: sizes and size presets, which
    apps are hidden or archived (a tile's right-click menu), the folders made
    by dragging apps together, and the music volume (Now playing's slider)."""
    import forge_theme

    allowed = set(forge_theme.SIZE_KEYS) | {
        "size_presets",
        "hidden_apps",
        "archived_apps",
        "app_folders",
        "music_volume",
    }
    picked = {k: v for k, v in changes.items() if k in allowed}
    if picked:
        forge_theme.save(picked, path)
    return picked


def page_zoom(value):
    """The saved App size as a WebKit zoom level; 1.0 for anything unusable."""
    try:
        level = float(value)
    except (TypeError, ValueError):
        return 1.0
    if not level > 0:
        return 1.0
    return min(PAGE_ZOOM_MAX, max(PAGE_ZOOM_MIN, level))


def port_open(port, timeout=0.2):
    """True once something accepts a TCP connection on the port. Uvicorn binds
    its socket only after the app's startup has run, so a connect is the
    same readiness signal as a GET of the index page, without the page."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


class Backend:
    """One tool's FastAPI backend, run the way that tool runs standalone:
    its own venv, its own working directory, its own module target."""

    def __init__(self, manifest, root):
        self.root = root
        self.name = manifest["name"]
        self.label = manifest.get("label", self.name)
        self.tagline = manifest.get("tagline", "")
        self.port = int(manifest["port"])
        self.module = manifest["module"]
        self.src_dir = manifest.get("src_dir", ".")
        self.order = manifest.get("order", 99)
        self.ready_timeout = manifest.get("ready_timeout", 180)
        # Started at launch even when apps start on demand: work of its own
        # to pick up (the Claude app carries on cut-off conversations).
        self.start_at_launch = manifest.get("start_at_launch") is True
        # How the home screen draws it. `role` lets the hub find a special app
        # (the Settings app says "settings") without naming it anywhere.
        self.accent = manifest.get("accent", "")
        self.icon = manifest.get("icon", "")
        self.role = manifest.get("role", "")
        # "auto": the hub fills the screen with this app when the Full screen
        # setting is on Smart. Games and players say so; tools do not.
        self.fullscreen = manifest.get("fullscreen", "")
        # Optional id of a groups/<id>.json: the app's tile moves into that
        # group's chooser. An id with no file is ignored and the tile stays.
        self.group = manifest.get("group", "")
        # Optional id of a sections/<id>.json: the heading the home screen
        # sorts this tile under. None, or an id with no file, lands in "Other".
        self.section = manifest.get("section", "")
        self.url = f"http://127.0.0.1:{self.port}"
        self.proc = None
        # idle: not started, waiting to be opened (Start apps: on demand)
        self.state = "pending"  # pending | idle | starting | up | failed | missing

    @property
    def python(self):
        return os.path.join(self.root, ".venv", "bin", "python")

    def installed(self):
        return os.path.isfile(self.python) and os.path.isdir(
            os.path.join(self.root, self.src_dir)
        )

    def start(self):
        """Blocking: launch the backend and wait for it to answer. Called on a
        worker thread, one per backend, so three slow starts overlap."""
        if not self.installed():
            print(f"[forge] {self.name}: no venv or source dir, skipping ({self.root})")
            self.state = "missing"
            return False

        # A backend that is already answering on its port -- an always-on
        # user service such as Acchan's, which Nyarch and the terminal use
        # without Forge open -- is adopted instead of launched a second time
        # (the second copy could only fail to bind). proc stays None, so
        # stopping the app in Forge leaves the service running.
        if port_open(self.port):
            print(f"[forge] {self.name}: already running on {self.url}, using it")
            self.state = "up"
            return True

        self.state = "starting"
        log_dir = os.path.join(ROOT, "outputs")
        os.makedirs(log_dir, exist_ok=True)
        log = open(os.path.join(log_dir, f"{self.name}.log"), "ab")

        env = os.environ.copy()
        # Where the shared frontend kit lives, so an app can mount /shared
        # without a fragile relative hop -- needed by apps that live outside
        # apps/ (see the "root" manifest field).
        env["FORGE_SHARED_DIR"] = os.path.join(ROOT, "shared")
        # AI Studio ships its sd-server binaries in a bin/ next to its source.
        bin_dir = os.path.join(self.root, "bin")
        if os.path.isdir(bin_dir):
            env["LD_LIBRARY_PATH"] = (
                bin_dir + os.pathsep + env.get("LD_LIBRARY_PATH", "")
            )

        # `python -m uvicorn`, never `.venv/bin/uvicorn`: NovelForge's venv is
        # --system-site-packages and resolves uvicorn from system site-packages
        # with no console-script wrapper, so that path does not exist.
        proc = self.proc = subprocess.Popen(
            [
                self.python,
                "-m",
                "uvicorn",
                self.module,
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=os.path.join(self.root, self.src_dir),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        print(f"[forge] {self.name}: starting on {self.url} (pid {proc.pid})")

        # Every backend measured 0.25-0.9 s to its first accepted connection
        # (2026-09-20), so the poll is a cheap connect every 0.1 s rather than
        # a full page GET every 0.4 s: the workspace mounts as soon as the
        # app can answer instead of up to half a second later.
        deadline = time.time() + self.ready_timeout
        while time.time() < deadline:
            if self.proc is not proc:
                # Closed while it started: stop_one() ended it and set the
                # state; this start is over (it used to crash on proc None).
                return False
            if port_open(self.port):
                print(f"[forge] {self.name}: ready")
                self.state = "up"
                return True
            if proc.poll() is not None:
                if self.proc is not proc:
                    return False
                print(
                    f"[forge] {self.name}: exited early (code {proc.returncode})"
                    f" -- see outputs/{self.name}.log"
                )
                self.state = "failed"
                return False
            time.sleep(0.1)
        print(f"[forge] {self.name}: not ready within {self.ready_timeout}s")
        self.state = "failed"
        return False


def discover_backends():
    """Every apps/<dir>/forge_app.json becomes a workspace, ordered by the
    manifest's "order". This is the whole registration mechanism -- there is
    no list of apps anywhere in this file."""
    found = []
    if not os.path.isdir(APPS_DIR):
        return found
    for entry in sorted(os.listdir(APPS_DIR)):
        root = os.path.join(APPS_DIR, entry)
        manifest_path = os.path.join(root, "forge_app.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            manifest.setdefault("name", entry)
            # An app normally lives in its own apps/<name>/ folder. "root" lets
            # a thin apps/<name>/ dir (just this manifest) point at a codebase
            # kept elsewhere -- used for the codec lab, which stays a separate
            # git repo at ~/anime-codec-lab rather than being moved in here.
            app_root = (
                os.path.expanduser(manifest["root"]) if manifest.get("root") else root
            )
            found.append(Backend(manifest, app_root))
        except Exception as e:
            print(f"[forge] {entry}: bad forge_app.json, skipping ({e})")
    found.sort(key=lambda b: (b.order, b.name))
    return found


def discover_groups():
    """Every groups/<id>.json becomes a group: one tile in the hub that opens a
    chooser of the apps whose manifest says "group": "<id>". Discovered like
    apps, so neither this file nor the hub names a group."""
    found = {}
    for path in sorted(glob.glob(os.path.join(GROUPS_DIR, "*.json"))):
        group_id = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
        except Exception as e:
            print(f"[forge] group {group_id}: bad file, skipping ({e})")
            continue
        found[group_id] = {
            "id": group_id,
            "label": data.get("label", group_id),
            "tagline": data.get("tagline", ""),
            "icon": data.get("icon", ""),
            "accent": data.get("accent", ""),
            "order": data.get("order", 99),
            "section": data.get("section", ""),
        }
    return found


def discover_sections():
    """Every sections/<id>.json becomes a heading on the home screen, in the
    file's "order". Apps and groups join one with a "section" field, so
    neither this file nor the hub names a section."""
    found = []
    for path in sorted(glob.glob(os.path.join(SECTIONS_DIR, "*.json"))):
        section_id = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
        except Exception as e:
            print(f"[forge] section {section_id}: bad file, skipping ({e})")
            continue
        found.append(
            {
                "id": section_id,
                "label": data.get("label", section_id),
                "icon": data.get("icon", ""),
                "blurb": data.get("blurb", ""),
                "order": data.get("order", 99),
            }
        )
    found.sort(key=lambda s: (s["order"], s["id"]))
    return {s["id"]: s for s in found}


def attach_groups(backends, groups):
    """The groups that have members, each listing its member apps in app
    order. A group nobody joins is left out; an app naming a group that has
    no file is attached nowhere and keeps its own tile."""
    attached = {}
    for b in backends:
        if b.group in groups:
            entry = attached.setdefault(b.group, dict(groups[b.group], members=[]))
            entry["members"].append(b.name)
    return attached


class BackendManager:
    def __init__(self, backends, lazy=False):
        """`lazy` is the Start apps setting on demand: nothing starts until the
        hub asks for it with start_one(), the first time that app is opened.
        Every backend imports in under a second, so the wait is short, and a
        launch no longer starts fifteen Python processes at once."""
        self.backends = backends
        self.lazy = lazy
        self._lock = threading.Lock()
        if lazy:
            for b in backends:
                if b.state == "pending":
                    b.state = "idle"

    def start_one(self, name, on_change):
        """Start one backend the hub asked for. Returns whether a start began:
        not for an unknown name, one already starting or up, or one whose
        process is still alive (a slow start that timed out)."""
        with self._lock:
            b = next((b for b in self.backends if b.name == name), None)
            if b is None or b.state in ("starting", "up"):
                return False
            if b.proc is not None and b.proc.poll() is None:
                return False
            b.state = "starting"
        self.start_all_async(on_change, only=[b])
        return True

    def start_all_async(self, on_change, only=None):
        """Start every backend on its own thread. on_change() fires whenever
        one changes state so the UI can update without waiting for the rest.
        `only` limits the launch to a subset, which is what adopting a newly
        added app uses so the ten already running are left alone."""
        for b in only if only is not None else self.backends:

            def run(b=b):
                b.start()
                on_change()

            threading.Thread(target=run, daemon=True).start()

    def adopt_new(self, on_change):
        """Pick up apps added to apps/ since launch and start them.

        Without this, discovery happens exactly once, at startup: Foresight was
        written while a Forge window was already open and so was simply absent
        from the sidebar for the rest of that session -- it looked like the app
        had disappeared, when in truth the hub had never been told it existed.
        The manifest scan is cheap (a dozen small JSON files), so the liveness
        poll that already runs every 15 seconds carries it.

        The list is REPLACED rather than appended to, because the GTK main loop
        reads it through snapshot() at the same time this worker thread writes
        it; rebinding the attribute is atomic where mutating the list in place
        is not."""
        known = {b.name for b in self.backends}
        fresh = [b for b in discover_backends() if b.name not in known]
        if not fresh:
            return []
        merged = sorted(self.backends + fresh, key=lambda b: (b.order, b.name))
        self.backends = merged
        if self.lazy:
            for b in fresh:
                b.state = "idle"
                print(f"[forge] {b.name}: added since launch, starts when opened")
            return fresh
        for b in fresh:
            print(f"[forge] {b.name}: added since launch, starting it now")
        self.start_all_async(on_change, only=fresh)
        return fresh

    def snapshot(self):
        return {
            b.name: {
                "available": b.state == "up",
                "state": b.state,
                "label": b.label,
                "tagline": b.tagline,
                "url": b.url,
                "accent": b.accent,
                "icon": b.icon,
                "role": b.role,
                "fullscreen": b.fullscreen,
                "order": b.order,
                "group": b.group,
                "section": b.section,
            }
            for b in self.backends
        }

    def write_status(self):
        """The shell is loaded over file://, where fetch() of a sibling file is
        blocked as a cross-origin request (a file origin is opaque). A <script>
        tag has no such restriction, so the data is emitted as a plain global
        assignment and that is what the shell reads. status.json is kept beside
        it for debugging only.

        Do NOT change the shell back to fetching status.json: that was the bug
        that made every workspace claim the tool "isn't ported yet" while all
        three backends were running perfectly."""
        data = self.snapshot()
        # Groups travel beside the apps rather than inside FORGE_STATUS, whose
        # every key the hub treats as an app. They are read once at page load.
        groups = attach_groups(self.backends, discover_groups())
        os.makedirs(HUB_DIR, exist_ok=True)
        with open(os.path.join(HUB_DIR, "status.json"), "w") as f:
            json.dump(data, f, indent=2)
        with open(os.path.join(HUB_DIR, "status.js"), "w") as f:
            f.write("window.FORGE_STATUS = " + json.dumps(data) + ";\n")
            f.write("window.FORGE_GROUPS = " + json.dumps(groups) + ";\n")
            f.write(
                "window.FORGE_SECTIONS = " + json.dumps(discover_sections()) + ";\n"
            )

    def stop_one(self, name, timeout=3.0):
        """Stop one backend and leave the rest alone.

        Emerson asked for this after opening an app by accident and finding it
        had started a language model: "i dont wnat it to run jan when i only
        accidentaly went int o th app tab". Closing an app should actually
        close it, not hide it. The app starts again on demand the next time it
        is opened, exactly as a lazily-started one does.
        """
        with self._lock:
            for b in self.backends:
                if b.name != name:
                    continue
                if b.proc is None or b.proc.poll() is not None:
                    b.state = "idle"
                    return True
                try:
                    os.killpg(b.proc.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
                deadline = time.time() + timeout
                while time.time() < deadline and b.proc.poll() is None:
                    time.sleep(0.05)
                if b.proc.poll() is None:
                    try:
                        os.killpg(b.proc.pid, signal.SIGKILL)
                        b.proc.wait(timeout=1)
                    except (
                        ProcessLookupError,
                        PermissionError,
                        subprocess.TimeoutExpired,
                    ):
                        pass
                b.proc = None
                b.state = "idle"
                return True
        return False

    def stop_all(self, timeout=3.0):
        """Stop every backend at once, and give stragglers `timeout` seconds.

        Each backend runs in its own session (start_new_session=True), so its
        process group id is its pid and the whole group - uvicorn plus anything
        it spawned, such as AI Studio's sd-server - goes together.

        Measured: every backend exits 0.15-0.2 s after SIGTERM. Stopping them
        one after another added that up to about 2.2 s; all at once it is the
        slowest single one. A backend still running after `timeout` is killed.
        """
        running = [
            b for b in self.backends if b.proc is not None and b.proc.poll() is None
        ]
        for b in running:
            try:
                os.killpg(b.proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        deadline = time.time() + timeout
        while time.time() < deadline and any(b.proc.poll() is None for b in running):
            time.sleep(0.05)
        for b in running:
            if b.proc.poll() is None:
                try:
                    os.killpg(b.proc.pid, signal.SIGKILL)
                    # Reap it, so nothing is left as a zombie and poll() is
                    # truthful. SIGKILL cannot be ignored; this is brief.
                    b.proc.wait(timeout=1)
                except (ProcessLookupError, PermissionError, subprocess.TimeoutExpired):
                    pass


POWER_SUPPLY = "/sys/class/power_supply"


def system_stats(previous=None):
    """CPU, memory and battery for the top bar (shared/forge_sysinfo.py, which
    the desktop widgets use too). Returns (stats, sample); pass the sample
    back in on the next call. POWER_SUPPLY here is what tests point elsewhere."""
    if SHARED_DIR not in sys.path:
        sys.path.insert(0, SHARED_DIR)
    import forge_sysinfo

    return forge_sysinfo.system_stats(previous, POWER_SUPPLY)


class StatsPump:
    """Runs the top bar's stats read on a worker thread and hands the result
    to `deliver` on the main loop (`post`, GLib.idle_add in Forge). The read
    ran on the main loop every 3 s: temperatures alone take about 45 ms, and
    a disk read can block on a sleeping USB drive, each a hitch in
    everything Forge draws (Emerson, 2026-10-08: "things in forge keep
    spasing only a little bit"). A tick while a read is still out is
    skipped, so a stuck read never piles threads up."""

    def __init__(self, read, deliver, post=None):
        self.read, self.deliver = read, deliver
        self.post = post or GLib.idle_add
        self.busy = False

    def tick(self):
        if self.busy:
            return True
        self.busy = True
        threading.Thread(target=self._work, daemon=True).start()
        return True

    def _work(self):
        try:
            data = self.read()
        except Exception as e:  # the next tick tries again
            print(f"forge: stats not read: {e}", file=sys.stderr)
            self.busy = False
            return
        self.busy = False
        self.post(self._hand, data)

    def _hand(self, data):
        self.deliver(data)
        return False


def apply_theme():
    """Write hub/theme.js from the saved settings. A failure is not fatal: the
    hub has a plain look of its own and Forge must still open."""
    if SHARED_DIR not in sys.path:
        sys.path.insert(0, SHARED_DIR)
    try:
        import forge_theme
        from pathlib import Path

        return forge_theme.apply(Path(HUB_DIR))
    except Exception as e:
        print(f"[forge] theme not applied, using the plain look ({e})", flush=True)
        return None


def forge_music_module():
    """shared/forge_music.py: the hub's background music (add a YouTube
    link's audio to the music folder) and the visualiser's system-audio
    levels. None when it cannot load; the hub then keeps its in-page audio."""
    if SHARED_DIR not in sys.path:
        sys.path.insert(0, SHARED_DIR)
    try:
        import forge_music

        return forge_music
    except Exception as e:
        print(f"[forge] music helper not loaded ({e})", flush=True)
        return None


def forge_theme_module():
    """shared/forge_theme.py: the saved settings and the login autostart."""
    if SHARED_DIR not in sys.path:
        sys.path.insert(0, SHARED_DIR)
    import forge_theme

    return forge_theme


def forge_mpris_module():
    """shared/forge_mpris.py: media players elsewhere on the desktop, for the
    hub's Now playing. None when D-Bus bindings are missing."""
    if SHARED_DIR not in sys.path:
        sys.path.insert(0, SHARED_DIR)
    try:
        import forge_mpris
    except (ImportError, ValueError) as e:
        print(f"[forge] desktop media players unavailable ({e})", flush=True)
        return None
    return forge_mpris


def forge_open_module():
    """shared/forge_open.py: the socket other programs use to ask this window
    to show one app (Acchan's launch_app, `forge.py --app <name>`)."""
    if SHARED_DIR not in sys.path:
        sys.path.insert(0, SHARED_DIR)
    import forge_open

    return forge_open


def launch_flags(argv):
    """`forge.py --background`: start hidden (login autostart); the window
    comes up the first time Forge is opened."""
    return {"background": "--background" in argv}


def shell_url(asked="", background=False, safe=False):
    """The hub's address. ?background=1 tells it Forge started hidden, so it
    holds the background music until forgeShown() (show_window) says the
    window was really opened; ?safe=1 keeps the heavy looks off after the page
    crashed again (after_hub_crash); #app=<name> opens straight onto an app."""
    flags = [f for f, on in (("background=1", background), ("safe=1", safe)) if on]
    query = "?" + "&".join(flags) if flags else ""
    return SHELL_URL + query + (f"#app={asked}" if asked else "")


HUB_CRASH_WINDOW = 120.0  # seconds within which a second hub crash counts as "again"

HUB_CRASH_PAGE = (
    '<!doctype html><meta charset="utf-8"><body style="margin:0;height:100vh;'
    "display:grid;place-items:center;background:#0b0d11;color:#cfd6e4;"
    'font:15px system-ui,sans-serif"><div style="max-width:32em;line-height:1.6">'
    '<h2 style="font-weight:600">Forge\'s page keeps crashing</h2>'
    "<p>It stopped four times in two minutes, so Forge stopped loading it again. "
    "The apps are still running. Restart Forge to try again.</p></div></body>"
)


def after_hub_crash(state: dict, now: float, window: float = HUB_CRASH_WINDOW) -> str:
    """What to do when the hub's web page has died: "reload" it, reload it
    "safe" (?safe=1: flat glass, two-layer 2.5D and no visualiser over apps
    for the rest of this run of Forge), or "stop" reloading. A second crash
    within `window` seconds turns safe mode on for the rest of the run; a
    fourth within it is a crash loop, and reloading again would only spin.
    Without this a crashed page left the window blank until a restart (task
    63: two WebKit crashes on 2026-10-07, one inside the GPU driver). `state`
    carries the earlier crash times and the safe flag between calls."""
    recent = [t for t in state.get("times", []) if now - t < window] + [now]
    state["times"] = recent
    if len(recent) >= 4:
        return "stop"
    if len(recent) >= 2:
        state["safe"] = True
    return "safe" if state.get("safe") else "reload"


def hub_crash_reloader(win, screen: dict, view_host: dict, crashes: dict | None = None):
    """The hub WebView's web-process-terminated handler. WebKit runs the page
    in a process of its own; when that dies the window stays up with nothing
    in it, so the page is loaded again, in safe mode if it keeps happening
    (after_hub_crash). An app's real web views would float over the fresh
    home screen, so they are hidden as on any return home. Nothing happens
    while Forge is quitting. `crashes` is after_hub_crash's state, shared
    with the hang watchdog, which sets "safe" before it ends a hung page."""
    crashes = {} if crashes is None else crashes
    doing = {
        "reload": "loading it again",
        "safe": "loading it again with the heavy looks off",
        "stop": "it keeps crashing, so it stays down",
    }

    def on_crashed(webview, reason):
        if screen.get("quitting"):
            return
        action = after_hub_crash(crashes, time.monotonic())
        why = getattr(reason, "value_nick", str(reason))
        print(f"[forge] the hub page stopped ({why}); {doing[action]}", flush=True)
        if view_host.get("host") is not None:
            view_host["host"].set_owner(None)
        if action == "stop":
            webview.load_html(HUB_CRASH_PAGE, None)
            return
        background = not win.get_visible()
        webview.load_uri(shell_url(background=background, safe=action == "safe"))

    return on_crashed


def view_handler(view_host: dict, make_host, zoom):
    """forge.py's half of the real web views (forge_views.py): the hub's view
    messages go to the ViewHost in view_host["host"], which make_host() makes
    the first time an app asks for a view, so launch never pays for WebKit's
    profile and cookie store. zoom() is the hub page's App size zoom: the page
    measures in CSS pixels, the window does not.

    The hub says which app is in front ("owner") and how far views keep clear
    of the bar and the dock ("inset") when that changes, which is before the
    app's page has loaded and asked for its first view. Those two are kept
    and handed to the host first when it is made. Dropped, the host started
    with no app in front and hid the Browser's first page in every Forge
    session until another app had been opened (Emerson, 2026-10-08: the
    Browser "lowkey never works for me"). Anything else sent before the first
    view is about views that do not exist, and goes nowhere."""
    early: dict[str, dict] = {}

    def deliver(message: dict) -> None:
        import forge_views

        view_host["host"].handle(forge_views.to_window(message, zoom()))

    def handle(message: dict) -> None:
        op = message.get("op")
        if view_host["host"] is None:
            if op in ("owner", "inset"):
                early[op] = message
            if op not in ("create", "cookies"):
                return
            view_host["host"] = make_host()
            for kept in early.values():
                deliver(kept)
            early.clear()
        deliver(message)

    return handle


HUB_HANG_PING = 4  # seconds between the hang watchdog's questions to the page
HUB_HANG_LIMIT = 10.0  # seconds with no answer, or no frame, that count as hung
HUB_HANG_LOAD_LIMIT = 30.0  # the same while a page is still loading

# The hang watchdog's question. With `frames` it answers true at the page's
# next painted frame and false when JavaScript still runs but no frame came
# within `wait` ms; without, it only shows the page's main thread is free.
# A stuck main thread answers nothing at all.
HUB_HANG_ASK = (
    "if (!frames) return true;"
    " return await new Promise((done) => {"
    " const t = setTimeout(() => done(false), wait);"
    " requestAnimationFrame(() => { clearTimeout(t); done(true); }); });"
)


def hub_hang_check(
    state: dict, now: float, limit: float = HUB_HANG_LIMIT, ping: float = HUB_HANG_PING
) -> str:
    """The hang watchdog's verdict at one tick: "ping" the page, "wait" for
    the answer still out, or "hung". Hung is a question unanswered for
    `limit` seconds (the page's main thread is stuck), or `limit` seconds
    of answers saying no frame was painted while one should have been (the
    compositor is stuck). Either way the page's process is alive, so
    web-process-terminated never fires; and WebKit's own
    is-web-process-responsive only turns false after input it could not
    deliver, so a 20-second hang left it true (task 63, 2026-10-07: frosted
    and liquid glass on every tile stuck WebKit's compositor, measured in
    a headless GNOME, tests/browser/check_hub_hang_webkit.py). state["sent"] is when the
    unanswered question went out, state["frameless"] since when no frame
    came; both None when all is well.

    Two waits are no hang. A tick more than two pings after the last one
    means Forge's own main loop stood still, so the page's answer may be
    sitting in its queue unread: the page gets one more `ping` seconds,
    once per question (state["graced"]), so a hang that also stalls Forge
    is still caught a ping later. And while the page shows a dialog
    (alert, confirm, prompt; state["dialog"]) its main thread waits for
    Emerson, rightly, so nothing counts until it answers again."""
    last, state["ticked"] = state.get("ticked"), now
    if last is not None and now - last > 2 * ping and not state.get("graced"):
        state["graced"] = True
        for key in ("sent", "frameless"):
            if state.get(key) is not None:
                state[key] = max(state[key], now - limit + ping)
    sent = state.get("sent")
    if state.get("dialog"):
        return "ping" if sent is None else "wait"
    if sent is not None:
        return "hung" if now - sent >= limit else "wait"
    frameless = state.get("frameless")
    if frameless is not None and now - frameless >= limit:
        return "hung"
    return "ping"


def hub_hang_answer(state: dict, sent: float, painted, watched: bool) -> None:
    """Note the page's answer to the question sent at `sent`. No frame
    counts only while one was `watched` for (Forge the active window, the
    page drawn): a page out of sight paints nothing, rightly. An answer
    also ends any grace (hub_hang_check) and any dialog: the page runs."""
    state.update(sent=None, graced=False, dialog=False)
    if painted is False and watched:
        if state.get("frameless") is None:
            state["frameless"] = sent
    else:
        state["frameless"] = None


def hub_hang_watchdog(win, webview, screen: dict, on_hung, clock=time.monotonic):
    """Ask the hub's page every HUB_HANG_PING seconds whether it still runs
    and paints (HUB_HANG_ASK), and call on_hung() once hub_hang_check says
    it is hung. Quiet while Forge quits and until a page is committed (its
    JavaScript can run); until the page has finished loading the limit is
    HUB_HANG_LOAD_LIMIT, as a start or a reload is where a stuck look shows
    first, and only whether it runs is asked: a page still loading may
    rightly paint nothing (a safe reload was ended mid-load in the rig, 2026-10-07).
    A missing page frame counts only when the window itself got one
    meanwhile: each question that waits for a frame also asks GTK to draw
    the window, and its frame clock moving on shows the desktop is still
    presenting it. With the screen blanked the desktop sends no frames at
    all, and that is no fault of the page.

    A dialog the page waits on pauses the count: alert, confirm and prompt
    (script-dialog) and print. WebKit draws its own script dialogs inside
    the view (WebKitScriptDialogImpl); once that is gone the count starts
    afresh, so a page stuck right after a dialog is still caught. Any other
    dialog pauses it until the page answers again, so a page stuck right
    after a print dialog is not caught, a known gap. A page that crashed
    is no longer asked anything. Returns the tick (for tests); main()
    drives it with GLib.timeout_add_seconds."""
    state: dict = {"page": 0}
    fresh: dict = {"sent": None, "frameless": None, "phase": None, "ticked": None}
    fresh.update(graced=False, dialog=False, shown=False, calm=None)
    state.update(fresh)

    def watched():
        return bool(win.is_active() and webview.get_mapped())

    def window_frames():
        frame_clock = win.get_frame_clock()
        return None if frame_clock is None else frame_clock.get_frame_counter()

    def dialog_shown():
        inside: list = []
        webview.forall(inside.append)
        return any(type(w).__name__ == "WebKitScriptDialogImpl" for w in inside)

    def restart():
        state.update(fresh)
        state["page"] += 1  # answers still out belong to the old page

    def on_load(_view, event):
        if event == WebKit2.LoadEvent.STARTED:
            restart()
        elif event == WebKit2.LoadEvent.COMMITTED:
            state["phase"] = "loading"
        elif event == WebKit2.LoadEvent.FINISHED:
            state["phase"] = "loaded"

    def on_dialog(_view, _dialog):
        state["dialog"] = True
        return False  # WebKit still shows it as usual

    def ask():
        page, sent = state["page"], clock()
        frames = state["phase"] == "loaded" and watched()
        state["sent"] = sent
        before = window_frames() if frames else None
        if frames:
            webview.queue_draw()

        def answered(view, result):
            if page != state["page"]:
                return  # a question to a page that has since been replaced
            try:
                value = view.call_async_javascript_function_finish(result)
                painted = value.to_boolean()
            except GLib.Error as e:
                painted = None  # an error is no sign of a hang; say so once
                if not state.get("told"):
                    state["told"] = True
                    print(
                        f"[forge] the hang watchdog's question failed: {e.message}",
                        flush=True,
                    )
            now = window_frames()
            drawn = before is not None and now is not None and now > before
            calm = state.get("calm")
            if state.get("dialog") or (calm is not None and sent < calm):
                painted = None  # it waited on a dialog, not on a stuck compositor
            hub_hang_answer(state, sent, painted, frames and drawn and watched())

        # WebKit takes only numbers, strings and dictionaries here: a
        # boolean is refused ("Invalid parameter"), so frames is 1 or 0
        args = GLib.Variant(
            "a{sv}",
            {
                "frames": GLib.Variant("d", 1.0 if frames else 0.0),
                "wait": GLib.Variant("d", HUB_HANG_PING * 1000.0),
            },
        )
        webview.call_async_javascript_function(
            HUB_HANG_ASK, -1, args, None, None, None, answered
        )

    def tick():
        if screen.get("quitting"):
            return False
        if state["phase"] is None:
            return True
        now = clock()
        if state["dialog"]:
            if dialog_shown():
                state["shown"] = True
            elif state["shown"]:  # WebKit's own dialog is gone: count afresh
                state.update(dialog=False, shown=False, calm=now, frameless=None)
                if state["sent"] is not None:
                    state["sent"] = now
        loaded = state["phase"] == "loaded"
        limit = HUB_HANG_LIMIT if loaded else HUB_HANG_LOAD_LIMIT
        verdict = hub_hang_check(state, now, limit)
        if verdict == "hung":
            restart()
            on_hung()
        elif verdict == "ping":
            ask()
        return True

    webview.connect("load-changed", on_load)
    webview.connect("script-dialog", on_dialog)
    webview.connect("print", on_dialog)
    webview.connect("web-process-terminated", lambda *_: restart())
    return tick


def hub_hang_ender(webview, crashes: dict):
    """hub_hang_watchdog's on_hung: the page is alive but stuck, so its
    process is ended, and the web-process-terminated handler
    (hub_crash_reloader, sharing `crashes`) loads it again with the heavy
    looks off."""

    def on_hung():
        print(
            "[forge] the hub page stopped answering; ending it and loading it"
            " again with the heavy looks off",
            flush=True,
        )
        crashes["safe"] = True
        webview.terminate_web_process()

    return on_hung


def hub_webview():
    """The hub's WebView, allowed to start sound without a click. WebKitGTK's
    default autoplay policy refuses play() on an element with sound until the
    page has been clicked, so the background music sat silent after every
    start unless a click happened to land on the hub itself (#257; measured
    2026-10-01, tests/browser/check_music_webkit.py)."""
    try:
        policies = WebKit2.WebsitePolicies(autoplay=WebKit2.AutoplayPolicy.ALLOW)
    except (AttributeError, TypeError):
        return WebKit2.WebView()  # older WebKit2 build
    return WebKit2.WebView(website_policies=policies)


def asked_app(argv):
    """`forge.py --app <name>` opens straight onto that app (the hub's
    #app=<name> link); an unsafe name is ignored."""
    if "--app" not in argv or argv.index("--app") + 1 >= len(argv):
        return ""
    name = argv[argv.index("--app") + 1]
    return name if name and all(c.isalnum() or c in "_.:-" for c in name) else ""


def launch_now(backends, lazy: bool, archived: set) -> list:
    """The backends to start when Forge launches: all but the archived ones,
    or with apps starting on demand, only those whose manifest says
    start_at_launch."""
    return [
        b
        for b in backends
        if b.name not in archived and (not lazy or b.start_at_launch)
    ]


def restart_argv(python: str, argv: list[str]) -> list[str]:
    """How Restart Forge runs Forge again: the same script, shown on screen
    (a restart asked for from the window is never a hidden --background one)."""
    return [python, os.path.abspath(argv[0])] + [
        a for a in argv[1:] if a != "--background"
    ]


def main():
    GLib.set_prgname("Forge")
    asked = asked_app(sys.argv[1:])
    flags = launch_flags(sys.argv[1:])
    opener_mod = forge_open_module()
    if asked and opener_mod.request_open(asked) is not None:
        return  # the Forge already open has switched to it
    if not asked and flags["background"]:
        if opener_mod.request_open("") is not None:
            return  # already running; nothing to start at login
    elif not asked:
        # Opening Forge while it waits in the background: show that window
        # rather than starting a second Forge. The launcher's activation
        # token goes along so the desktop lets it take the focus.
        token = os.environ.get("XDG_ACTIVATION_TOKEN") or os.environ.get(
            "DESKTOP_STARTUP_ID", ""
        )
        if opener_mod.request_show(token) is not None:
            return

    # Cached after the first run: the wallpaper copy, its blurred copy and its
    # palette are rendered once per picture (about 0.4 s) and reused after.
    theme_data = apply_theme() or {}
    # Start at login (Settings): keep the autostart entry in step with it.
    try:
        forge_theme_module().set_autostart(theme_data.get("start_at_login", True))
    except OSError as e:
        print(f"[forge] could not update the login autostart entry: {e}", flush=True)

    lazy = theme_data.get("start_apps", "demand") == "demand"
    backends = BackendManager(discover_backends(), lazy=lazy)
    if not backends.backends:
        print(f"[forge] no apps found in {APPS_DIR} -- each needs a forge_app.json")
    # Write the initial (all-pending) status before the shell loads, so the
    # sidebar renders the right workspaces immediately.
    backends.write_status()

    win = Gtk.Window(title="Forge")
    win.set_default_size(1400, 900)
    if not theme_data.get("start_fullscreen"):
        # the first of Alt+F's three levels: the screen under the desktop's
        # top bar, not a small window in the middle of it
        win.maximize()

    webview = hub_webview()
    settings = webview.get_settings()
    settings.set_property("enable-developer-extras", True)
    allow_microphone(webview)
    # The shell lives on file://; without these, anything it fetches from a
    # sibling file is rejected as cross-origin.
    for prop in (
        "allow-file-access-from-file-urls",
        "allow-universal-access-from-file-urls",
    ):
        try:
            settings.set_property(prop, True)
        except TypeError:
            pass  # older WebKit2 build
    webview.set_zoom_level(page_zoom(theme_data.get("ui_scale")))
    webview.load_uri(shell_url(asked, flags["background"]))
    # An overlay, so real web views (forge_views.py) can sit over an app's
    # workspace. The view host, its WebKit profile and its cookie store are
    # made the first time an app asks for a view, so launch never pays for them.
    overlay = Gtk.Overlay()
    overlay.add(webview)
    win.add(overlay)
    view_host: dict = {"host": None}
    power_now: dict = {}

    def emit_view_event(event):
        webview.run_javascript(
            f"window.forgeViewEvent && window.forgeViewEvent({json.dumps(event)});",
            None,
            None,
            None,
        )

    def make_view_host():
        import forge_views

        host = forge_views.ViewHost(overlay, emit_view_event)
        host.set_power(power_now)
        return host

    handle_view = view_handler(view_host, make_view_host, webview.get_zoom_level)

    # --- links that leave the app -----------------------------------------
    #
    # A link with target="_blank" does not navigate in WebKit. It asks the view
    # to create a *second* view, and with nothing connected to `create` the
    # click is swallowed in silence - no error, no navigation. That is why
    # every source link in Dossier looked dead. There is no sensible second
    # view to make here, because this window has no tabs, so the address goes
    # to the real browser instead - which is where you want a source you might
    # keep open anyway.

    def open_externally(uri):
        if not uri or not uri.startswith(("http://", "https://")):
            return  # never hand an arbitrary scheme to the desktop
        try:
            Gtk.show_uri_on_window(win, uri, Gdk.CURRENT_TIME)
        except Exception as e:
            print(f"[forge] could not open {uri}: {e}", flush=True)

    def on_create(_view, navigation_action):
        open_externally(navigation_action.get_request().get_uri())
        return None  # no new view is coming; WebKit must not wait for one

    def on_decide_policy(_view, decision, decision_type):
        # window.open() arrives here rather than through `create`.
        if decision_type == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION:
            open_externally(decision.get_navigation_action().get_request().get_uri())
            decision.ignore()
            return True
        return False

    webview.connect("create", on_create)
    webview.connect("decide-policy", on_decide_policy)

    # --- pop-out windows (A22) --------------------------------------------
    #
    # The hub's app menu can pop an app out into its own window, which goes
    # to a monitor Forge is not on (forge_popout.py). Its backend is the
    # hub's; one the hub never opened is started first and the window waits
    # for it (up to 30 s).
    import forge_popout

    forge_popout.track_pad_focus(win, forge_popout.MAIN)

    def tell_apps_focus(w, _param=None):
        # The apps hear when Forge's window gains or loses focus: an unfocused
        # window gets no new pad state, so a game reading the PS5 pad pauses
        # (its own blur does not fire when the focus was in the hub, not in
        # its frame).
        webview.run_javascript(
            "window.forgeWindowActive && window.forgeWindowActive("
            f"{json.dumps(w.is_active())});",
            None,
            None,
            None,
        )

    win.connect("notify::is-active", tell_apps_focus)

    def popped_back(name):
        webview.run_javascript(
            f"window.forgePoppedBack && window.forgePoppedBack({json.dumps(name)});",
            None,
            None,
            None,
        )
        win.present()

    popouts = forge_popout.PopOuts(
        win, popped_back, open_externally, webview.get_zoom_level()
    )

    def pop_out(name):
        backend = next((b for b in backends.backends if b.name == name), None)
        if backend is None:
            return
        if backends.start_one(name, on_change):
            GLib.idle_add(on_change)
        waited = {"s": 0.0}

        def when_up():
            if backend.state == "up":
                popouts.open(name, backend.label, backend.url)
                return False
            waited["s"] += 0.25
            if backend.state not in ("starting", "pending") or waited["s"] > 30:
                print(f"[forge] {name} did not start, so it was not popped out")
                return False
            return True

        if when_up():
            GLib.timeout_add(250, when_up)

    # --- fullscreen --------------------------------------------------------
    #
    # F11 fills the screen, Esc gives it back. The sidebar goes with it: a
    # fullscreen window that still has a sidebar in it is not what anyone means
    # by fullscreen. The shell already knows how to hide its own chrome - any
    # workspace can ask for that by postMessage - so this only asks on the
    # keyboard's behalf, and the shell decides when the sidebar comes back.
    # Why the window is full screen lives in `fs` (FullScreen: the desktop,
    # the app, a video's element full screen); `screen` is what the window
    # and the hub are showing right now, and sync_fullscreen() brings them in
    # line. Start full screen is the window being the desktop, not a mode to
    # escape from: Esc stays with the apps (Wallpapers closes its panel with
    # it) and only F11 on the home screen leaves.
    fs = FullScreen(desktop=bool(theme_data.get("start_fullscreen")))
    screen: dict = {"full": False, "app": False, "owner": None, "before": None}

    # How the window was before full screen, so leaving puts it back rather
    # than dropping it as a bare window in the middle of the screen.
    window_state = {"maximized": False}

    def on_window_state(_win, event):
        window_state["maximized"] = bool(
            event.new_window_state & Gdk.WindowState.MAXIMIZED
        )
        left = (
            event.changed_mask & Gdk.WindowState.FULLSCREEN
            and not event.new_window_state & Gdk.WindowState.FULLSCREEN
        )
        if left and screen["full"]:
            # Taken away by the window manager, not by us: forget every wish
            # so the next F11 starts from a windowed Forge.
            if fs.element:
                leave_element_fullscreen()
            fs.window_left()
            screen["full"] = False
            screen.pop("before", None)
            GLib.idle_add(sync_fullscreen)
        if seen.window_state(event.new_window_state & Gdk.WindowState.ICONIFIED):
            apply_seen()
        return False

    win.connect("window-state-event", on_window_state)

    # Rest while nobody can see the window (B34, see Seen). Unmapping the
    # window's child is what WebKit reads as hidden: document.hidden turns
    # true in the hub and every app frame and view, animation frames stop,
    # timers slow to once a second, and music keeps playing. The hub's own
    # visibilitychange listeners stop the particles, the visualiser and cava.
    seen = Seen()
    pause_hidden = {"on": theme_data.get("pause_when_hidden", True) is not False}

    def apply_seen():
        page = win.get_child()
        show = seen.seen or not pause_hidden["on"]
        if page is not None and page.get_child_visible() != show:
            page.set_child_visible(show)
        return False

    def on_visibility(_win, event):
        obscured = event.state == Gdk.VisibilityState.FULLY_OBSCURED
        if seen.visibility(obscured):
            apply_seen()
        return False

    def on_touched(*_args):
        if seen.touched():
            apply_seen()
        return False

    def on_mapped(on):
        if seen.mapped(on):
            apply_seen()
        return False

    win.add_events(
        Gdk.EventMask.VISIBILITY_NOTIFY_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK
    )
    win.connect("visibility-notify-event", on_visibility)
    for signal_name in ("focus-in-event", "enter-notify-event", "button-press-event"):
        win.connect(signal_name, on_touched)
    win.connect("map-event", lambda *_a: on_mapped(True))
    win.connect("unmap-event", lambda *_a: on_mapped(False))
    # Mostly covered, minimised or on another workspace, as the GNOME
    # extension sees it (task 60): GNOME's own fully-obscured needs every
    # pixel covered, so a window over almost all of Forge never counted.
    # How much of it shows picks the effects' tier in the hub
    # (shared/forge_power.js): mostly covered draws the reduced effects.
    shown = {"share": 1.0}

    def send_share():
        webview.run_javascript(
            f"window.forgeShare && window.forgeShare({shown['share']});",
            None,
            None,
            None,
        )

    def on_share(share):
        shown["share"] = share
        send_share()

    # the first answer can come before the page has loaded: say it again then
    def on_hub_loaded(_view, event):
        if event == WebKit2.LoadEvent.COMMITTED:
            # A fresh hub page (first load, a crash reload) has no app in
            # front that reads the PS5 pad, whatever the old one last said.
            forge_popout.set_pad_native(False)
        if event == WebKit2.LoadEvent.FINISHED and shown["share"] < 1:
            send_share()

    webview.connect("load-changed", on_hub_loaded)
    shell_monitor = watch_shell(  # noqa: F841 (kept alive)
        seen, apply_seen, on_share=on_share
    )

    def leave_element_fullscreen():
        # The hub document owns the iframe, so exiting there exits for both.
        webview.run_javascript(
            "document.exitFullscreen && document.fullscreenElement"
            " && document.exitFullscreen();",
            None,
            None,
            None,
        )

    def sync_fullscreen():
        """Bring the window and the hub in line with `fs`."""
        if fs.window and not screen["full"]:
            screen["full"] = True
            screen["before"] = {
                "maximized": window_state["maximized"],
                "size": tuple(win.get_size()),
            }
            win.fullscreen()
        elif not fs.window and screen["full"]:
            screen["full"] = False
            win.unfullscreen()
            plan = restore_plan(screen.pop("before", None))
            if plan[0] == "maximize":
                win.maximize()
            else:
                win.unmaximize()
                win.resize(plan[1], plan[2])
        if fs.app != screen["app"]:
            screen["app"] = fs.app
            webview.run_javascript(
                "window.forgeSetFullscreen && window.forgeSetFullscreen("
                + ("true" if fs.app else "false")
                + ");",
                None,
                None,
                None,
            )
        return False

    # An app inside a workspace can ask for real fullscreen itself -- the
    # "Full screen" button in every app does, through
    # shared/forge_chrome.js. WebKit grants that request inside the WebView
    # and stops there: the element fills the WebView, but the GTK window keeps
    # its decorations and its size, so from the user's side the button looked
    # like it had done nothing but hide the sidebar. Take the window with it.
    def on_enter_fullscreen(_view):
        fs.set_element(True)
        sync_fullscreen()
        return False  # False: WebKit still does its own half

    def on_leave_fullscreen(_view):
        fs.set_element(False)
        sync_fullscreen()
        return False

    webview.connect("enter-fullscreen", on_enter_fullscreen)
    webview.connect("leave-fullscreen", on_leave_fullscreen)

    # Workspace shortcuts are caught here, before the page sees the key. The
    # hub's own keydown listener only hears keys while the hub has focus, and
    # once an app is open its iframe has it - so Ctrl+1 used to do nothing from
    # inside an app.
    shortcut_mods = (
        Gdk.ModifierType.MOD1_MASK
        | Gdk.ModifierType.SUPER_MASK
        | Gdk.ModifierType.META_MASK
    )

    hub_keys = key_table(theme_data.get("hub_keys"))  # updated in place

    # --- overview pictures (Alt+Space) ----------------------------------------
    #
    # The hub asks a moment after an app comes to the front; the picture goes
    # back as a data URL. One snapshot per switch, nothing on a timer.
    def take_snap(request):
        key = str(request.get("key") or "")
        rect = request.get("rect")
        if not key:
            return

        def send(png):
            url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
            webview.run_javascript(
                f"window.forgeSnap && window.forgeSnap({json.dumps(key)}, {json.dumps(url)});",
                None,
                None,
                None,
            )
            return False

        def encode(surface):  # off the main loop: the PNG is the slow part
            try:
                png = png_bytes(surface)
            except Exception as e:  # a snapshot is a nicety, never an error
                print(f"[forge] overview picture skipped ({e})", flush=True)
                return
            GLib.idle_add(send, png)

        def done(view, result):
            try:
                surface = view.get_snapshot_finish(result)
                density = surface.get_width() / max(1, view.get_allocated_width())
                png = thumb_png(surface, rect, scale=view.get_zoom_level() * density)
            except Exception as e:  # a snapshot is a nicety, never an error
                print(f"[forge] overview picture skipped ({e})", flush=True)
                return
            send(png)

        # The frame on screen first (frame_thumb); WebKit's full repaint only
        # when that frame is blank.
        try:
            shown = frame_thumb(webview, rect, scale=webview.get_zoom_level())
        except Exception as e:
            print(f"[forge] overview picture from the screen failed ({e})", flush=True)
            shown = None
        if shown is not None:
            threading.Thread(target=encode, args=(shown,), daemon=True).start()
            return
        webview.get_snapshot(
            WebKit2.SnapshotRegion.VISIBLE,
            WebKit2.SnapshotOptions.NONE,
            None,
            done,
        )

    def workspace_shortcut(event):
        if not event.state & Gdk.ModifierType.CONTROL_MASK:
            return None
        if event.state & shortcut_mods:
            return None
        name = Gdk.keyval_name(event.keyval) or ""
        if name == "0":
            return "home"
        if name.isdigit():
            return name
        if name == "Tab":
            return "prev" if event.state & Gdk.ModifierType.SHIFT_MASK else "next"
        if name == "ISO_Left_Tab":
            return "prev"
        return None

    def on_key(_win, event):
        on_touched()
        action = workspace_shortcut(event)
        if action:
            webview.run_javascript(
                f"window.forgeKey && window.forgeKey({json.dumps(action)});",
                None,
                None,
                None,
            )
            return True
        hub_action = key_action(event.keyval, event.state, hub_keys)
        if hub_action == "fullscreen":
            fs.key(app_open=bool(screen["owner"]))
            sync_fullscreen()
            return True
        if hub_action == "quit":
            quit_forge()
            return True
        if hub_action == "restart":
            # Quit cleanly (every backend stops, so the Claude app marks what
            # it was doing), then main() runs Forge again in this process.
            screen["restart"] = True
            quit_forge()
            return True
        if hub_action:
            if hub_action in ("pulse", "ambient", "zen", "widgets"):
                # these hide the apps: the hub's page takes the keys back from
                # a Browser view that held them, or Alt+V's arrows go nowhere
                webview.grab_focus()
            webview.run_javascript(
                f"window.forgeKey && window.forgeKey({json.dumps(hub_action)});",
                None,
                None,
                None,
            )
            return True
        if event.keyval == Gdk.KEY_Escape and fs.escape():
            # During element full screen fs leaves Esc to the page: WebKit
            # leaves it and leave-fullscreen brings the window back. Handling
            # it here as well would leave the page stretched in the window.
            sync_fullscreen()
            return True
        return False  # every other key belongs to the page

    win.connect("key-press-event", on_key)

    def push_status():
        """Hand the current backend states to the page. The shell cannot work
        this out for itself: a cross-origin fetch from file:// is blocked, and
        an <img> probe cannot tell a refused connection from a 404."""
        payload = json.dumps(backends.snapshot())
        webview.run_javascript(
            f"window.forgeSetStatus && window.forgeSetStatus({payload});",
            None,
            None,
            None,
        )
        return False

    def on_change():
        backends.write_status()
        GLib.idle_add(push_status)

    # The page asks for an app's backend the first time it is opened, through
    # WebKit's script message channel: window.webkit.messageHandlers.forge.
    content = webview.get_user_content_manager()
    content.register_script_message_handler("forge")

    def push_music(event):
        """An event from shared/forge_music.py (levels, a finished download)
        to the hub's window.forgeMusic; called from worker threads."""
        script = f"window.forgeMusic && window.forgeMusic({json.dumps(event)});"
        GLib.idle_add(lambda: webview.run_javascript(script, None, None, None))

    def handle_media(req):
        mpris = forge_mpris_module()
        if mpris is None:
            return
        op = str(req.get("op") or "")
        bus = str(req.get("bus") or "")
        value = req.get("value")
        value = float(value) if isinstance(value, (int, float)) else None

        def work():
            if op != "list":
                mpris.control(bus, op, value)
            players = mpris.players()
            script = (
                f"window.forgeMediaSys && window.forgeMediaSys({json.dumps(players)});"
            )
            GLib.idle_add(lambda: webview.run_javascript(script, None, None, None))

        threading.Thread(target=work, daemon=True).start()

    def on_page_message(_manager, result):
        value = result.get_js_value() if hasattr(result, "get_js_value") else result
        try:
            request = json.loads(value.to_string())
        except (TypeError, ValueError):
            return
        if isinstance(request, dict) and isinstance(request.get("settings"), dict):
            # The hub's Aa panel: sizes and size presets, saved to the same
            # file Settings writes. Only those keys; the rest stay Settings'.
            save_hub_settings(request["settings"])
            return
        if isinstance(request, dict) and isinstance(request.get("snap"), dict):
            take_snap(request["snap"])
            return
        if isinstance(request, dict) and "pause_hidden" in request:
            # "Rest while Forge is hidden" changed in Settings; the hub relays it.
            pause_hidden["on"] = request["pause_hidden"] is not False
            apply_seen()
            return
        if isinstance(request, dict) and "pad_native" in request:
            # The app in front reads the PS5 pad itself (its page told the
            # hub): shared/pad sends no mouse or keys while it does.
            forge_popout.set_pad_native(request["pad_native"] is True)
            return
        if isinstance(request, dict) and isinstance(request.get("keys"), dict):
            # Forge keys changed in Settings; the hub relays them.
            hub_keys.clear()
            hub_keys.update(key_table(request["keys"]))
            return
        if isinstance(request, dict) and "zoom" in request:
            # App size changed in Settings; the hub relays it.
            level = page_zoom(request["zoom"])
            webview.set_zoom_level(level)
            popouts.set_zoom(level)
            return
        if isinstance(request, dict) and isinstance(request.get("power"), dict):
            # What applies now from Settings > Speed and detail; the hub works
            # it out from the settings and the plug and sends it on each
            # change. Scrolling here and in the Browser's pages, the frame and
            # video caps in the Browser's pages (the apps get theirs from the
            # hub's theme message).
            power = request["power"]
            power_now.clear()
            power_now.update(power)
            settings.set_property(
                "enable-smooth-scrolling", power.get("smooth_scroll", True) is not False
            )
            if view_host["host"] is not None:
                view_host["host"].set_power(power)
            return
        if isinstance(request, dict) and isinstance(request.get("view"), dict):
            if request["view"].get("op") == "owner":
                # The app in front (None on the home screen), for F11.
                screen["owner"] = request["view"].get("owner")
            handle_view(request["view"])
            return
        if isinstance(request, dict) and isinstance(request.get("media"), dict):
            # The hub's Now playing: list the desktop's other players, or
            # send one a command. D-Bus calls run off the main loop.
            handle_media(request["media"])
            return
        if isinstance(request, dict) and isinstance(request.get("popout"), str):
            # The app menu's Pop out: the app in its own window (A22).
            pop_out(request["popout"])
            return
        if isinstance(request, dict) and isinstance(request.get("music"), dict):
            music = forge_music_module()
            if music:
                music.handle(request["music"], push_music)
            return
        if not isinstance(request, dict):
            return
        if request.get("forge") == "quit":
            # The bar's power menu: Quit Forge, or Hide to the background.
            GLib.idle_add(quit_forge)
            return
        if request.get("forge") == "hide":
            GLib.idle_add(win.hide)
            return
        if isinstance(request.get("window"), bool):
            # The bar's Full screen, or an app's own button relayed by the hub.
            fs.set_app(request["window"])
            GLib.idle_add(sync_fullscreen)
            return
        name = request.get("start")
        closing = request.get("stop")
        # Both run off the main loop. A stop waits for the process to exit
        # (0.2 s, up to 3 s) and used to freeze the window for that long; a
        # start may have to wait for a stop of the same app that is still in
        # flight, which the manager's lock serialises.
        if isinstance(name, str):

            def start_then_refresh(name=name):
                if backends.start_one(name, on_change):
                    GLib.idle_add(on_change)

            threading.Thread(target=start_then_refresh, daemon=True).start()
        if isinstance(closing, str):

            def stop_then_refresh(name=closing):
                if backends.stop_one(name):
                    GLib.idle_add(on_change)

            threading.Thread(target=stop_then_refresh, daemon=True).start()

    content.connect("script-message-received::forge", on_page_message)

    # Start everything concurrently, unless apps start on demand (then only
    # the ones whose manifest asks to start at launch); either way the window
    # is already on screen.
    first = launch_now(
        backends.backends, backends.lazy, set(theme_data.get("archived_apps") or [])
    )
    if first:
        backends.start_all_async(on_change, only=first)

    # Steady-state liveness poll, so a backend that dies later turns its dot
    # red. Runs off the main loop so a hung port never freezes the window.
    def poll_liveness():
        def work():
            # An app added to apps/ since launch joins here rather than
            # waiting for the next restart. on_change pushes the new sidebar.
            backends.adopt_new(on_change)
            for b in backends.backends:
                if b.state in ("up", "failed"):
                    b.state = "up" if port_open(b.port, timeout=1) else "failed"
            GLib.idle_add(push_status)

        threading.Thread(target=work, daemon=True).start()
        return True

    GLib.timeout_add_seconds(15, poll_liveness)

    # CPU, memory and battery for the top bar. A few tiny /proc reads.
    cpu: dict = {"sample": None}  # plus the widgets' net meter and slow reads

    def read_stats():
        """On StatsPump's worker thread: nothing here may touch GTK."""
        top, cpu["sample"] = system_stats(cpu["sample"])
        stats: dict = dict(top)  # plus the widgets' dicts and lists below
        # other programs' GPU load (shared/forge_gpuload.py): the hub eases
        # its effects off while a game, a model or a render is busy
        try:
            if "gpu" not in cpu:
                import forge_gpuload

                cpu["gpu"] = forge_gpuload.GpuLoad()
            stats["gpu"] = cpu["gpu"].read()
        except Exception as e:
            print(f"forge: GPU load not read: {e}", file=sys.stderr)
        # the home widgets' network, disk and Jan cards (S25); the slow two
        # are read every 30 s
        try:
            import forge_sysinfo

            if "net" not in cpu:
                cpu["net"] = forge_sysinfo.NetMeter()
                cpu["slow_at"] = 0.0
            stats["net"] = cpu["net"].read()
            if time.monotonic() - cpu["slow_at"] > 30:
                cpu["slow_at"] = time.monotonic()
                cpu["slow"] = {
                    "disks": forge_sysinfo.disks(),
                    "jan": forge_sysinfo.jan_status(),
                    "temps": forge_sysinfo.temperatures(),
                }
            stats.update(cpu["slow"])
        except Exception as e:  # the top bar's own numbers still go out
            print(f"forge: widget stats failed: {e}", file=sys.stderr)
        return stats

    def send_stats(stats):
        webview.run_javascript(
            f"window.forgeSetStats && window.forgeSetStats({json.dumps(stats)});",
            None,
            None,
            None,
        )

    GLib.timeout_add_seconds(3, StatsPump(read_stats, send_stats).tick)

    # 2.5D (S23): a wallpaper's layers are made in the background after its
    # theme went out, and shared/forge_layers.py rewrites hub/theme.js when
    # they are done. Nothing told the running hub, so 2.5D waited for a
    # restart (Emerson, 2026-09-29). Only the layer keys are passed on.
    layer_keys = (
        "wallpaper_fg",
        "wallpaper_bg",
        "wallpaper_subject",
        "wallpaper_depth",
    )
    layers_sent = {k: theme_data.get(k, "") for k in layer_keys}
    layers_wait = {"id": 0}

    def push_layers():
        layers_wait["id"] = 0
        try:
            with open(os.path.join(HUB_DIR, "theme.js"), encoding="utf-8") as f:
                text = f.read()
            fresh = json.loads(text[text.index("{") : text.rindex("}") + 1])
        except (OSError, ValueError):
            return False
        now = {k: fresh.get(k, "") for k in layer_keys}
        if now != layers_sent:
            layers_sent.update(now)
            webview.run_javascript(
                f"window.applyTheme && applyTheme({json.dumps(now)});",
                None,
                None,
                None,
            )
        return False

    def on_theme_file(*_args):
        # theme.js is replaced by a rename; let a burst of events settle
        if not layers_wait["id"]:
            layers_wait["id"] = GLib.timeout_add(400, push_layers)

    from gi.repository import Gio

    theme_monitor = Gio.File.new_for_path(
        os.path.join(HUB_DIR, "theme.js")
    ).monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, None)
    theme_monitor.connect("changed", on_theme_file)

    def on_delete(*_args):
        # Closing the window only hides it while "Closing the window" says to
        # keep Forge in the background (read now: Settings may have changed
        # it since launch). The apps, and any music, keep going.
        if forge_theme_module().load().get("close_action") != "quit":
            win.hide()
            return True
        quit_forge()
        return True

    def quit_forge():
        # Hide first, and let the compositor actually unmap it, so the window
        # is gone the instant it is closed. The backends stop behind it.
        if screen.get("quitting"):
            return  # the key and a SIGTERM can both arrive
        screen["quitting"] = True
        win.hide()
        popouts.close_all()
        while Gtk.events_pending():
            Gtk.main_iteration()
        backends.stop_all()
        if opener is not None:
            opener.close()
            forge_open_module().SOCKET.unlink(missing_ok=True)
        Gtk.main_quit()

    win.connect("delete-event", on_delete)

    # the hub's page dying (a GPU driver crash, out of memory) loads it again
    hub_crashes: dict = {}
    webview.connect(
        "web-process-terminated",
        hub_crash_reloader(win, screen, view_host, hub_crashes),
    )

    # a hung page (alive, but its main thread or its painting stuck) is
    # ended, and the reloader above brings it back with the heavy looks off
    GLib.timeout_add_seconds(
        HUB_HANG_PING,
        hub_hang_watchdog(win, webview, screen, hub_hang_ender(webview, hub_crashes)),
    )

    def show_window(token=""):
        # show_all, not show: a window started --background has never shown
        # its children. The token is the launcher's xdg-activation token.
        win.show_all()
        if token:
            win.set_startup_id(token)
        win.present()
        # A window started --background holds its music until it is first
        # seen; the hub's forgeShown lets it go (and ignores later calls).
        webview.run_javascript("window.forgeShown && forgeShown()", None, None, None)
        return False

    def show_app(name):
        show_window()
        webview.run_javascript(
            f"selectWorkspace({json.dumps(name)});", None, None, None
        )
        return False

    def on_open(name):
        # Runs on forge_open's thread; the window work goes to the main loop.
        known = {b.name for b in backends.backends}
        known |= {"group:" + g for g in discover_groups()}
        # An archived app is put away until Settings restores it.
        known -= set(forge_theme_module().load().get("archived_apps") or [])
        if name not in known:
            return False
        GLib.idle_add(show_app, name)
        return True

    def on_show(token):
        # Runs on forge_open's thread, like on_open.
        GLib.idle_add(show_window, token)

    # None when another Forge already answers; that one keeps the socket.
    opener = opener_mod.serve(on_open, on_show=on_show)

    def handle_sigterm(*_args):
        # Logout or kill: really quit, whatever closing the window does.
        GLib.idle_add(quit_forge)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    if not flags["background"]:
        win.show_all()
    # Start full screen: the window only; the hub keeps its bar and dock. A
    # hidden window takes it as its first state when it is shown.
    sync_fullscreen()
    Gtk.main()
    if screen.get("restart"):
        sys.stdout.flush()
        os.execv(sys.executable, restart_argv(sys.executable, sys.argv))


if __name__ == "__main__":
    sys.exit(main())
