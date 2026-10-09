"""Real web pages inside Forge: WebKit views laid over an app's workspace.

WHY THIS EXISTS
    An app is an iframe in the hub, and most websites refuse to be framed
    (X-Frame-Options, CSP frame-ancestors), so a browser cannot be an iframe.
    Instead forge.py owns real WebKit views and lays them over the part of the
    window where an app's page says its content area is. The app draws the
    browser chrome (tabs, address bar, bookmarks) and drives the views by
    message; this module does only the views. Nothing here names an app: any
    app may ask for views, which belong to it by `owner`.

THE MESSAGE PROTOCOL (the page -> the hub -> forge.py -> ViewHost.handle)
    {op: "create",   id, owner, url, rect, keys?, keys_first?}
                                        shortcuts the app keeps while the page
                                        has the keyboard ("ctrl+l", "f5"): keys
                                        when the page leaves them alone (a web
                                        terminal's Ctrl+L stays its own),
                                        keys_first before the page sees them
    {op: "navigate", id, url}           http, https, about:blank, data:text/html,
                                        and file:/// (never from a page's own links)
    {op: "back" | "forward" | "reload" | "stop", id}
    {op: "zoom",     id, level}         0.3 - 3.0
    {op: "rect",     id, rect}          rect = [x, y, width, height] in window pixels
    {op: "owner",    owner}             only this owner's views are shown; null hides all
    {op: "inset",    top, bottom}       keep views clear of the revealed bar and the dock
    {op: "hide" | "show", id}
    {op: "focus",    id}                give the page the keyboard (only one
                                        that shows: its owner in front, not hidden)
    {op: "read",     id, request}       page title, address, text and links
    {op: "media",    id?, cmd, value?}  a page's audio/video: cmd is state, toggle,
                                        play, pause, seek (s) or volume (0..1);
                                        no id asks every view for its state
    {op: "cookies",  cookies: [...]}    import cookies (the Browser app's Firefox import)
    {op: "close",    id}  /  {op: "close-owner", owner}

    Events go back through `emit(dict)`, each carrying `owner`:
    state (title, url, progress, loading, back, forward), open (a link that
    wanted a new window), read (the page), media (what the page plays:
    has, paused, title, current, duration, volume), download, cookies,
    key (combo: one of the create's keys was pressed in the page; the hub
    has the keyboard now), crashed (reason, reloaded: the page's process
    died; its address is loaded again once, never a form sent again, and not
    when it dies again within a minute), unshown (url, mime: a local file
    WebKit cannot show, such as a PDF, which would be a blank page).

PROFILE
    ~/.local/share/forge/browser-profile (cookies, local storage), cache in
    ~/.cache/forge/browser. Kept apart from Firefox: Firefox's own cache and
    storage formats are not readable by WebKit; cookies are imported instead.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
gi.require_version("Soup", "3.0")
from gi.repository import Gdk, GLib, Gtk, Soup, WebKit2  # noqa: E402

HOME = Path.home()
PROFILE = Path(
    os.environ.get("FORGE_BROWSER_PROFILE", HOME / ".local/share/forge/browser-profile")
)
CACHE = Path(os.environ.get("FORGE_BROWSER_CACHE", HOME / ".cache/forge/browser"))
DOWNLOADS = Path(os.environ.get("FORGE_DOWNLOADS", HOME / "Downloads"))
# A view may name a session: one of shared/accounts.json's logins, with its
# own cookies and storage, so two logins to one site can be open at once.
ACCOUNTS = Path(
    os.environ.get("FORGE_ACCOUNTS_DATA", HOME / ".local/share/forge/accounts")
)
ACCOUNTS_CACHE = Path(
    os.environ.get("FORGE_ACCOUNTS_CACHE", HOME / ".cache/forge/accounts")
)
SESSION_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
ALLOWED = ("http://", "https://", "about:blank", "data:text/html")
# A file on this computer, which only the app itself may open (a typed path,
# the Claude panel showing a doc), never a page's own new-window link.
LOCAL = "file:///"
# A page that dies again this soon after being loaded again is left down.
CRASH_AGAIN = 60.0
# The modifiers a shortcut is made of, in the order a combo names them; locks
# (Caps, Num) and the rest do not count.
MODIFIERS = (
    ("ctrl", Gdk.ModifierType.CONTROL_MASK),
    ("shift", Gdk.ModifierType.SHIFT_MASK),
    ("alt", Gdk.ModifierType.MOD1_MASK),
    ("super", Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.MOD4_MASK),
    ("altgr", Gdk.ModifierType.MOD5_MASK),
)

# The page text handed back by `read`, for the Claude panel and for search.
READ_SCRIPT = """JSON.stringify({
  title: document.title,
  url: location.href,
  text: (document.body ? document.body.innerText : "").slice(0, 200000),
  links: [...document.querySelectorAll("a[href]")].slice(0, 300)
    .map(a => ({ text: (a.innerText || "").trim().slice(0, 120), href: a.href }))
})"""

# The audio and video in a view, for the hub's Now playing: YouTube or
# Crunchyroll in Media keep playing while another app is in front, and the
# bar's music button has to pause them (Emerson, 2026-09-26). Injected into
# every frame, because Crunchyroll's player is a cross-origin iframe the main
# frame's scripts cannot reach: a command goes down the frames by postMessage
# and each frame with media reports up to the top one, which answers
# MEDIA_SCRIPT. It never plays anything by itself.
SHARED = Path(__file__).resolve().parent / "shared"


def power_script(values: dict) -> str:
    """The script every Browser page starts with: the frame-rate cap and the
    video caps (shared/forge_framecap.js, shared/forge_webcap.js), set to
    `values`, what applies now from Settings > Speed and detail."""
    parts = [
        (SHARED / name).read_text(encoding="utf-8")
        for name in ("forge_framecap.js", "forge_webcap.js")
    ]
    parts.append(f"window.ForgeWebCap.set({json.dumps(values)});")
    return "\n".join(parts)


MEDIA_AGENT = r"""(() => {
  if (window.__forgeViewMedia) return;
  const pick = () => {
    const all = [...document.querySelectorAll("video, audio")].filter((e) => e.currentSrc || e.src);
    return all.find((e) => !e.paused) || all.sort((a, b) => (b.duration || 0) - (a.duration || 0))[0] || null;
  };
  const state = (el) => {
    const meta = (navigator.mediaSession && navigator.mediaSession.metadata) || null;
    return { has: true, paused: el.paused || el.ended, title: (meta && meta.title) || document.title || "",
             artist: (meta && meta.artist) || "", current: el.currentTime || 0,
             duration: Number.isFinite(el.duration) ? el.duration : 0, volume: el.volume, video: el.tagName === "VIDEO" };
  };
  const apply = (cmd, value) => {
    const el = pick();
    if (!el) return;
    if (cmd === "toggle") el.paused ? el.play().catch(() => {}) : el.pause();
    else if (cmd === "play") el.play().catch(() => {});
    else if (cmd === "pause") el.pause();
    else if (cmd === "seek" && Number.isFinite(value)) el.currentTime = Math.max(0, value);
    else if (cmd === "volume" && Number.isFinite(value)) el.volume = Math.max(0, Math.min(1, value));
  };
  const down = (msg) => { for (let i = 0; i < window.frames.length; i++) { try { window.frames[i].postMessage(msg, "*"); } catch (e) {} } };
  let child = null; // the newest report from a frame below, at the top only
  window.__forgeViewMedia = (cmd, value) => {
    if (cmd && cmd !== "state") { apply(cmd, value); down({ forgeViewMedia: "cmd", cmd, value }); }
    const el = pick();
    if (el) return JSON.stringify(state(el));
    if (child && Date.now() - child.at < 5000) {
      const s = Object.assign({}, child.state);
      if (cmd === "toggle") s.paused = !s.paused; else if (cmd === "pause") s.paused = true; else if (cmd === "play") s.paused = false;
      return JSON.stringify(s);
    }
    return JSON.stringify({ has: false });
  };
  // Forge hears at once when something starts or stops (the hub's music
  // steps aside or comes back), instead of at its next question
  const nudge = () => { try { window.webkit.messageHandlers.forgeViewMedia.postMessage("changed"); } catch (e) {} };
  const changed = (e) => {
    if (!(e.target instanceof HTMLMediaElement)) return;
    if (window === top) return nudge();
    const el = pick();
    if (el) { try { top.postMessage({ forgeViewMedia: "state", state: state(el), now: true }, "*"); } catch (x) {} }
  };
  for (const type of ["play", "playing", "pause", "ended"]) document.addEventListener(type, changed, true);
  addEventListener("message", (e) => {
    const m = e.data;
    if (!m || typeof m !== "object" || !m.forgeViewMedia) return;
    if (m.forgeViewMedia === "cmd" && window !== top) { apply(m.cmd, Number(m.value)); down(m); }
    else if (m.forgeViewMedia === "state" && window === top) {
      child = { state: m.state, at: Date.now() };
      if (m.now) nudge();
    }
  });
  if (window !== top) setInterval(() => {
    const el = pick();
    if (el) { try { top.postMessage({ forgeViewMedia: "state", state: state(el) }, "*"); } catch (e) {} }
  }, 1000);
})();"""
MEDIA_CMDS = ("state", "toggle", "play", "pause", "seek", "volume")

SAME_SITE = {0: "NONE", 1: "LAX", 2: "STRICT"}


def media_state(raw) -> dict:
    """What a page says it plays, cut down to known fields of the right type:
    the page's own scripts can replace the agent, so nothing else gets through."""
    if not isinstance(raw, dict) or not raw.get("has"):
        return {"has": False}

    def number(key):
        try:
            value = float(raw.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0
        return value if value == value and abs(value) < 1e7 else 0.0

    return {
        "has": True,
        "paused": bool(raw.get("paused")),
        "title": str(raw.get("title") or "")[:200],
        "artist": str(raw.get("artist") or "")[:200],
        "current": number("current"),
        "duration": number("duration"),
        "volume": max(0.0, min(1.0, number("volume"))),
        "video": bool(raw.get("video")),
    }


def allowed(url, local: bool = False) -> bool:
    return isinstance(url, str) and (
        url.startswith(ALLOWED) or (local and url.startswith(LOCAL))
    )


def key_combo(event) -> str:
    """A key press as "ctrl+shift+t": modifiers in MODIFIERS order, then the
    key's own name in lower case. Letters and F keys read the same as a page's
    KeyboardEvent.key; other keys do not ("page_down", not "pagedown")."""
    keyval = Gdk.keyval_to_lower(event.keyval)
    names = [name for name, mask in MODIFIERS if event.state & mask]
    return "+".join(names + [(Gdk.keyval_name(keyval) or "").lower()])


def _keys(value) -> frozenset:
    if not isinstance(value, list):
        return frozenset()
    return frozenset(
        k.lower() for k in value[:64] if isinstance(k, str) and len(k) <= 40
    )


def _rect(value) -> tuple[int, int, int, int] | None:
    try:
        x, y, w, h = (int(round(float(v))) for v in value)
    except (TypeError, ValueError):
        return None
    return x, y, max(0, w), max(0, h)


def to_window(msg: dict, zoom: float) -> dict:
    """A view message with its CSS-pixel geometry turned into window pixels.
    The hub page is zoomed by App size, so its CSS pixels are `zoom` window
    pixels each. The caller's message is left as it was."""
    if zoom == 1:
        return msg
    out = dict(msg)
    rect = msg.get("rect")
    if isinstance(rect, (list, tuple)) and len(rect) == 4:
        try:
            out["rect"] = [float(v) * zoom for v in rect]
        except (TypeError, ValueError):
            pass
    if msg.get("op") == "inset":
        for side in ("top", "bottom"):
            try:
                out[side] = float(msg.get(side) or 0) * zoom
            except (TypeError, ValueError):
                pass
    return out


class ViewHost:
    def __init__(self, overlay: Gtk.Overlay, emit, profile=None, cache=None):
        self.overlay = overlay
        self.emit = emit
        self.views: dict[str, dict] = {}
        self.media_due: set[str] = set()
        self.owner: str | None = None
        self.inset_top = 0
        self.inset_bottom = 0
        self.stores: dict[str, tuple] = {}
        self.context, self.cookies = self._store(
            "", Path(profile or PROFILE), Path(cache or CACHE)
        )
        self.accounts = ACCOUNTS
        self.accounts_cache = ACCOUNTS_CACHE
        # What applies now from Settings > Speed and detail; the hub sends it
        # (forge.py calls set_power) and every page gets it.
        self.power: dict = {}
        overlay.connect("get-child-position", self._position)

    def _store(self, name: str, profile: Path, cache: Path) -> tuple:
        profile.mkdir(parents=True, exist_ok=True, mode=0o700)
        cache.mkdir(parents=True, exist_ok=True)
        data = WebKit2.WebsiteDataManager(
            base_data_directory=str(profile), base_cache_directory=str(cache)
        )
        context = WebKit2.WebContext.new_with_website_data_manager(data)
        cookies = data.get_cookie_manager()
        cookies.set_persistent_storage(
            str(profile / "cookies.sqlite"), WebKit2.CookiePersistentStorage.SQLITE
        )
        cookies.set_accept_policy(WebKit2.CookieAcceptPolicy.NO_THIRD_PARTY)
        context.connect("download-started", self._on_download)
        self.stores[name] = (context, cookies)
        return context, cookies

    def session(self, name) -> tuple:
        """(WebContext, CookieManager) for a session name; the Browser's own
        profile for none or a malformed one. Made the first time it is asked for."""
        name = str(name or "")
        if not SESSION_NAME.fullmatch(name):
            name = ""
        if name not in self.stores:
            self._store(
                name, self.accounts / name / "webkit", self.accounts_cache / name
            )
        return self.stores[name]

    # --- dispatch -----------------------------------------------------------

    def handle(self, msg: dict) -> None:
        op = msg.get("op")
        view_id = str(msg.get("id", ""))[:64]
        entry = self.views.get(view_id)
        if op == "create":
            self.create(
                view_id,
                str(msg.get("owner", "")),
                msg.get("url"),
                msg.get("rect"),
                msg.get("session"),
                _keys(msg.get("keys")),
                _keys(msg.get("keys_first")),
            )
        elif op == "owner":
            self.set_owner(msg.get("owner"))
        elif op == "inset":
            self.inset_top = max(0, int(msg.get("top") or 0))
            self.inset_bottom = max(0, int(msg.get("bottom") or 0))
            self.overlay.queue_resize()
        elif op == "close-owner":
            for vid in [
                v for v, e in self.views.items() if e["owner"] == msg.get("owner")
            ]:
                self.close(vid)
        elif op == "cookies":
            self.import_cookies(msg.get("cookies") or [], msg.get("session"))
        elif op == "media" and not view_id:
            for vid in list(self.views):
                self.media(vid, "state")
        elif entry is None:
            return
        elif op == "navigate" and allowed(msg.get("url"), local=True):
            entry["view"].load_uri(msg["url"])
        elif op == "back":
            entry["view"].go_back()
        elif op == "forward":
            entry["view"].go_forward()
        elif op == "reload":
            entry["view"].reload()
        elif op == "stop":
            entry["view"].stop_loading()
        elif op == "zoom":
            level = float(msg.get("level") or 1)
            entry["view"].set_zoom_level(max(0.3, min(3.0, level)))
        elif op == "rect":
            rect = _rect(msg.get("rect"))
            if rect:
                entry["rect"] = rect
                self.overlay.queue_resize()
        elif op in ("hide", "show"):
            entry["hidden"] = op == "hide"
            self._apply_visibility(entry)
        elif op == "focus" and self._shown(entry):
            entry["view"].grab_focus()
        elif op == "read":
            self.read(view_id, msg.get("request"))
        elif op == "media":
            self.media(view_id, msg.get("cmd"), msg.get("value"))
        elif op == "close":
            self.close(view_id)

    # --- views ----------------------------------------------------------------

    def create(
        self,
        view_id: str,
        owner: str,
        url,
        rect,
        session=None,
        keys=frozenset(),
        keys_first=frozenset(),
    ) -> None:
        if not view_id or view_id in self.views:
            return
        scripts = WebKit2.UserContentManager()
        scripts.add_script(
            WebKit2.UserScript(
                MEDIA_AGENT,
                WebKit2.UserContentInjectedFrames.ALL_FRAMES,
                WebKit2.UserScriptInjectionTime.END,
                None,
                None,
            )
        )
        scripts.register_script_message_handler("forgeViewMedia")
        scripts.connect(
            "script-message-received::forgeViewMedia",
            lambda *_a, v=view_id: self._media_changed(v),
        )
        view = WebKit2.WebView(
            web_context=self.session(session)[0], user_content_manager=scripts
        )
        settings = view.get_settings()
        settings.set_property("enable-developer-extras", True)
        settings.set_user_agent_with_application_details("Forge", "1")
        entry = {
            "view": view,
            "owner": owner,
            "rect": _rect(rect) or (0, 0, 0, 0),
            "hidden": False,
            "scripts": scripts,
            "power_script": None,
            "keys": keys,
            "keys_first": keys_first,
            "crashed": None,
            "uri": None,
        }
        self._power_view(entry)
        self.views[view_id] = entry
        for prop in ("title", "uri", "estimated-load-progress", "is-loading"):
            view.connect(f"notify::{prop}", lambda *_a, v=view_id: self._state(v))
        view.connect(
            "create", lambda _v, action, v=view_id: self._new_window(v, action)
        )
        view.connect("decide-policy", lambda _v, d, t, v=view_id: self._policy(v, d, t))
        view.connect(
            "web-process-terminated", lambda _v, why, v=view_id: self._crashed(v, why)
        )
        # keys_first before the page; keys only after the page left them (WebKit
        # sends a key the page did not take on to the handlers run last)
        view.connect(
            "key-press-event", lambda _v, ev, v=view_id: self._key(v, ev, True)
        )
        view.connect_after(
            "key-press-event", lambda _v, ev, v=view_id: self._key(v, ev, False)
        )
        self.overlay.add_overlay(view)
        self._apply_visibility(entry)
        view.load_uri(url if allowed(url, local=True) else "about:blank")

    def set_power(self, values: dict) -> None:
        """Speed and detail changed, or the charger was plugged in or pulled
        out: every open page follows now, and later pages start with it."""
        self.power = dict(values)
        for entry in self.views.values():
            self._power_view(entry)
            entry["view"].run_javascript(
                f"window.ForgeWebCap && window.ForgeWebCap.set({json.dumps(self.power)});",
                None,
                None,
            )

    def _power_view(self, entry: dict) -> None:
        entry["view"].get_settings().set_property(
            "enable-smooth-scrolling",
            self.power.get("smooth_scroll", True) is not False,
        )
        scripts = entry["scripts"]
        if entry["power_script"] is not None:
            scripts.remove_script(entry["power_script"])
        entry["power_script"] = WebKit2.UserScript(
            power_script(self.power),
            WebKit2.UserContentInjectedFrames.ALL_FRAMES,
            WebKit2.UserScriptInjectionTime.START,
            None,
            None,
        )
        scripts.add_script(entry["power_script"])

    def set_owner(self, owner) -> None:
        self.owner = owner if isinstance(owner, str) else None
        for entry in self.views.values():
            self._apply_visibility(entry)

    def close(self, view_id: str) -> None:
        entry = self.views.pop(view_id, None)
        if entry:
            self.overlay.remove(entry["view"])
            entry["view"].destroy()

    def _shown(self, entry: dict) -> bool:
        return entry["owner"] == self.owner and not entry["hidden"]

    def _apply_visibility(self, entry: dict) -> None:
        if self._shown(entry):
            entry["view"].show()
        else:
            entry["view"].hide()

    def _position(self, _overlay, widget, allocation) -> bool:
        entry = next((e for e in self.views.values() if e["view"] is widget), None)
        if entry is None:
            return False
        x, y, w, h = entry["rect"]
        top = max(y, self.inset_top)
        bottom = y + h
        if self.inset_bottom:
            bottom = min(
                bottom, self.overlay.get_allocated_height() - self.inset_bottom
            )
        allocation.x, allocation.y = x, top
        allocation.width, allocation.height = w, max(0, bottom - top)
        return True

    # --- events -----------------------------------------------------------------

    def _send(self, view_id: str, event: str, **data) -> None:
        entry = self.views.get(view_id)
        owner = entry["owner"] if entry else data.pop("owner", "")
        self.emit({"event": event, "id": view_id, "owner": owner, **data})

    def _state(self, view_id: str) -> None:
        entry = self.views.get(view_id)
        if not entry:
            return
        view = entry["view"]
        entry["uri"] = view.get_uri() or entry["uri"]
        self._send(
            view_id,
            "state",
            title=view.get_title() or "",
            url=view.get_uri() or "",
            progress=round(view.get_estimated_load_progress(), 2),
            loading=view.is_loading(),
            back=view.can_go_back(),
            forward=view.can_go_forward(),
        )

    def _crashed(self, view_id: str, reason) -> None:
        """The page's web process died (a crash, or it ran out of memory), and
        the view would stay blank for good: its address is loaded again (not
        reload(), which would send a form again), unless it died within
        CRASH_AGAIN of the last time. The app is told either way."""
        entry = self.views.get(view_id)
        if not entry:
            return
        now = time.monotonic()
        again = entry["crashed"] is not None and now - entry["crashed"] < CRASH_AGAIN
        entry["crashed"] = now
        uri = entry["uri"]
        if not again and allowed(uri, local=True):
            entry["view"].load_uri(uri)
        why = getattr(reason, "value_nick", str(reason))
        self._send(view_id, "crashed", reason=why, reloaded=not again)

    def _key(self, view_id: str, event, first: bool) -> bool:
        """A shortcut the app asked for, pressed while the page has the
        keyboard: the hub gets the keyboard back (so the app can put the caret
        in its address bar) and the app is told. Anything else is the page's."""
        entry = self.views.get(view_id)
        combo = key_combo(event)
        if not entry or combo not in entry["keys_first" if first else "keys"]:
            return False
        hub = self.overlay.get_child()
        if hub is not None and hub.get_can_focus():
            hub.grab_focus()
        self._send(view_id, "key", combo=combo)
        return True

    def _new_window(self, view_id: str, action):
        url = action.get_request().get_uri()
        if allowed(url):
            self._send(view_id, "open", url=url)
        return None

    def _policy(self, view_id: str, decision, decision_type) -> bool:
        if decision_type == WebKit2.PolicyDecisionType.RESPONSE:
            uri = decision.get_request().get_uri() or ""
            if (
                uri.startswith(LOCAL)
                and decision.is_main_frame_main_resource()
                and not decision.is_mime_type_supported()
            ):
                decision.ignore()
                mime = decision.get_response().get_mime_type() or ""
                self._send(view_id, "unshown", url=uri, mime=mime)
                return True
            return False
        if decision_type == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION:
            url = decision.get_navigation_action().get_request().get_uri()
            if allowed(url):
                self._send(view_id, "open", url=url)
            decision.ignore()
            return True
        return False

    def read(self, view_id: str, request) -> None:
        entry = self.views.get(view_id)
        if not entry:
            return

        def done(view, result):
            try:
                value = view.run_javascript_finish(result).get_js_value().to_string()
                page = json.loads(value)
            except Exception as e:
                page = {"error": str(e)}
            self._send(view_id, "read", request=request, page=page)

        entry["view"].run_javascript(READ_SCRIPT, None, done)

    def _media_changed(self, view_id: str) -> None:
        """A page said its media started or stopped: report it within 0.1 s.
        Bursts (play then playing) and a page calling this in a loop come
        out as one question."""
        if view_id in self.media_due:
            return
        self.media_due.add(view_id)

        def ask():
            self.media_due.discard(view_id)
            self.media(view_id, "state")
            return False

        GLib.timeout_add(100, ask)

    def media(self, view_id: str, cmd, value=None) -> None:
        """Run a media command in a view and report what it plays after."""
        entry = self.views.get(view_id)
        if not entry or cmd not in MEDIA_CMDS:
            return
        try:
            number = float(value) if value is not None else None
        except (TypeError, ValueError):
            number = None
        call = (
            f"window.__forgeViewMedia ? window.__forgeViewMedia("
            f"{json.dumps(cmd)}, {json.dumps(number)}) : '{{\"has\": false}}'"
        )

        def done(view, result):
            try:
                value = view.run_javascript_finish(result).get_js_value().to_string()
                state = json.loads(value)
            except Exception:
                state = {"has": False}
            self._send(view_id, "media", **media_state(state))

        entry["view"].run_javascript(call, None, done)

    # --- cookies and downloads -------------------------------------------------------

    def import_cookies(self, rows: list, session=None) -> None:
        """Add cookies (Firefox's moz_cookies rows, as the Browser app reads
        them) to this profile, or to a session's. Expired ones and malformed
        ones are skipped."""
        jar = self.session(session)[1]
        now = GLib.get_real_time() // 1_000_000
        count = 0
        for row in rows:
            try:
                expiry = int(row.get("expiry") or 0)
                if expiry and expiry < now:
                    continue
                cookie = Soup.Cookie.new(
                    str(row["name"]),
                    str(row["value"]),
                    str(row["host"]),
                    str(row.get("path") or "/"),
                    -1,
                )
                if expiry:
                    cookie.set_expires(GLib.DateTime.new_from_unix_utc(expiry))
                cookie.set_secure(bool(row.get("secure")))
                cookie.set_http_only(bool(row.get("http_only")))
                policy = SAME_SITE.get(int(row.get("same_site") or 0), "NONE")
                cookie.set_same_site_policy(getattr(Soup.SameSitePolicy, policy))
            except (KeyError, TypeError, ValueError):
                continue
            jar.add_cookie(cookie, None, None)
            count += 1
        self.emit(
            {
                "event": "cookies",
                "id": "",
                "owner": "",
                "count": count,
                "session": session or "",
            }
        )

    def _on_download(self, _context, download) -> None:
        def destination(dl, suggested):
            DOWNLOADS.mkdir(parents=True, exist_ok=True)
            name = Path(suggested or "download").name or "download"
            target = DOWNLOADS / name
            stem, suffix, n = target.stem, target.suffix, 1
            while target.exists():
                target = DOWNLOADS / f"{stem} ({n}){suffix}"
                n += 1
            dl.set_destination(GLib.filename_to_uri(str(target), None))
            return True

        def finished(dl):
            path = GLib.filename_from_uri(dl.get_destination())[0]
            self.emit(
                {"event": "download", "id": "", "owner": "", "file": path, "done": True}
            )

        def failed(_dl, error):
            self.emit(
                {
                    "event": "download",
                    "id": "",
                    "owner": "",
                    "error": str(error),
                    "done": False,
                }
            )

        download.connect("decide-destination", destination)
        download.connect("finished", finished)
        download.connect("failed", failed)
