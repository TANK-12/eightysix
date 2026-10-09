"""Mission's door to the Claude app's conversations, for the Conversations
view (static/convos.js, a copy of the Claude app's Enjoy task view).

The Claude app (port from its forge_app.json, role "claude") only answers
requests carrying X-Forge: 1, which a page cannot send it cross-site; so the
page asks Mission, and Mission forwards a short allowlist of the Claude
app's own routes. Nothing else of the Claude app is reachable through here.

It also passes on the pictures attached to a chat (image(), images only)
and opens a reply's links in Forge's Browser (open_link(), web addresses
only), both through the Claude app.

Its static files that the view reuses (run_controls.js, enjoy_logic.js and
their css) are served read-only from apps/claude/static, by name, from
CLAUDE_UI, so both apps load the same file.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from mc import actions, borrow

CONV_ID = re.compile(r"^[0-9A-Za-z_-]{1,64}$")
# POST /api/conversations/{id}/<action> the view may use
CONV_ACTIONS = ("send", "settings", "stop", "seen", "files", "paste-image")
# The Claude app's static files the view loads, as they are in its folder.
CLAUDE_UI = ("run_controls.js", "run_controls.css", "enjoy_logic.js", "enjoy.css")
CLAUDE_STATIC = os.path.join(borrow.APPS, "claude", "static")
# events?wait= holds the request for up to 25 s on the Claude app's side
TIMEOUT = 35.0
MAX_BODY = 40 * 1024 * 1024  # an attached picture arrives as base64
# a picture attached to a chat, by file name (no folders), for thumbnails
IMAGE_NAME = re.compile(r"^[^/\\]{1,200}\.(png|jpe?g|gif|webp)$", re.IGNORECASE)
MAX_IMAGE = 40 * 1024 * 1024
MAX_URL = 4000
DOWN = "The Claude app is not running; open it in Forge first"


def ui_file(name: str) -> str | None:
    """Path of one of the Claude app's shared static files, or None."""
    if name not in CLAUDE_UI:
        return None
    path = os.path.join(CLAUDE_STATIC, name)
    return path if os.path.isfile(path) else None


def _base() -> str:
    port = actions.manifest_port(role="claude")
    if not port:
        raise actions.ActionError(404, "No Claude app found")
    return f"http://127.0.0.1:{port}"


def call(method: str, path: str, query: dict | None = None, body=None) -> dict:
    """One request to the Claude app; ActionError with its status on failure."""
    url = _base() + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body if body is not None else {}).encode()
    req = urllib.request.Request(
        url,
        data=data if method == "POST" else None,
        method=method,
        headers={"Content-Type": "application/json", "X-Forge": "1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as reply:
            return json.load(reply)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e).get("detail") or str(e)
        except ValueError:
            detail = str(e)
        raise actions.ActionError(e.code, str(detail))
    except (OSError, ValueError):
        raise actions.ActionError(503, DOWN)


def options() -> dict:
    return call("GET", "/api/options")


def events(conv: str, after: int, wait: float, boot: str) -> dict:
    query = {"after": after, "wait": max(0.0, min(25.0, wait))}
    if boot:
        query["boot"] = boot
    return call("GET", f"/api/conversations/{conv}/events", query)


def act(conv: str, action: str, body: dict) -> dict:
    if action not in CONV_ACTIONS:
        raise actions.ActionError(404, "Not something this view can do")
    return call("POST", f"/api/conversations/{conv}/{action}", body=body)


def image(conv: str, name: str) -> tuple[bytes, str]:
    """A picture attached to one of the Claude app's chats, as (bytes, media
    type). The Claude app serves these unguarded (an <img> sends no
    headers); Mission passes on pictures only, and only up to MAX_IMAGE."""
    url = (
        f"{_base()}/api/conversations/{conv}/files/{urllib.parse.quote(name, safe='')}"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as reply:
            media = reply.headers.get_content_type()
            data = reply.read(MAX_IMAGE + 1)
    except urllib.error.HTTPError as e:
        raise actions.ActionError(e.code, "No such picture in that chat")
    except (OSError, ValueError):
        raise actions.ActionError(503, DOWN)
    if not media.startswith("image/") or len(data) > MAX_IMAGE:
        raise actions.ActionError(502, "The Claude app did not send a picture")
    return data, media


def open_link(url: str) -> dict:
    """A web address from a reply, opened in Forge's Browser the way the
    Claude app's own chats open it (its POST /api/open-link)."""
    if not url.startswith(("http://", "https://")) or len(url) > MAX_URL:
        raise actions.ActionError(400, "Only web addresses open in the Browser")
    return call("POST", "/api/open-link", body={"url": url})
