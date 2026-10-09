"""What Mission Control can do, each through the app that already owns it:

- a note to one session: the Claude app's everyone.message (forge board);
- a note to a crew board, or an answer to a note: the Board app's post/ack;
- "go to it": the Board app's go_to_session (terminal tab or Claude app tab);
- "open in Claude": the Claude app's own HTTP API on its port;
- Relay pause and resume: the Relay page's HTTP API.

Nothing here writes a file of another app directly.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from mc import borrow

TIMEOUT = 2.0


class ActionError(Exception):
    def __init__(self, status: int, text: str):
        super().__init__(text)
        self.status = status


def manifest_port(role: str | None = None, name: str | None = None) -> int | None:
    """An app's port from its forge_app.json, found by role or folder name.
    MISSION_PORT_<NAME> (MISSION_PORT_RELAY, MISSION_PORT_CLAUDE) overrides
    it, so a scratch copy can be pointed away from the real apps."""
    import glob

    override = os.environ.get(f"MISSION_PORT_{(name or role or '').upper()}")
    if override:
        return int(override) if override.isdigit() else None

    for path in sorted(glob.glob(os.path.join(borrow.APPS, "*", "forge_app.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, ValueError):
            continue
        if (role and manifest.get("role") == role) or (
            name and manifest.get("name") == name
        ):
            port = manifest.get("port")
            return int(port) if port else None
    return None


def http_json(
    port: int, path: str, payload: dict | None = None, method: str = "POST"
) -> dict:
    data = json.dumps(payload or {}).encode() if method == "POST" else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
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
        raise ActionError(e.code, str(detail))
    except (OSError, ValueError) as e:
        raise ActionError(503, f"not reachable: {e}")


def message_session(session_id: str, text: str) -> dict:
    try:
        return borrow.everyone().message(session_id, text)
    except LookupError as e:
        raise ActionError(404, str(e))


def _board_call(fn, *args):
    board = borrow.board()
    try:
        return fn(*args)
    except board.HTTPException as e:  # the Board's own validation
        raise ActionError(e.status_code, str(e.detail))


EMERSON = "Emerson"


def check_note(crew: str, to: str | None, re: int | None) -> None:
    """A note must reach someone on that board and answer a note that exists."""
    board = borrow.crew().peek(crew)
    members = board.get("members") or {}
    if to:
        slots = {m.get("slot") for m in members.values() if m}
        if to == EMERSON:
            raise ActionError(400, "That would be a note to yourself")
        if to not in members and to not in slots:
            raise ActionError(404, f"Nobody called {to} is on the {crew} board")
    if re is not None and not any(n.get("id") == re for n in board.get("notes") or []):
        raise ActionError(404, f"There is no note {re} on the {crew} board")


def post_note(
    crew: str, text: str, to: str | None = None, re: int | None = None
) -> dict:
    board = borrow.board()
    if crew in board._crew_names():
        check_note(crew, to, re)
    return _board_call(board.post, crew, board.Post(text=text, to=to or None, re=re))


def ack_note(crew: str, note_id: int, note: str = "") -> dict:
    board = borrow.board()
    return _board_call(board.ack, crew, note_id, board.Ack(note=note))


def go_to(name: str) -> dict:
    board = borrow.board()
    return _board_call(board.go_to_session, name)


def claude_names() -> dict:
    """Claude app session id -> its tab (name, title); empty when it is closed."""
    return borrow.board().claude_names()


def open_in_claude(
    session_id: str, state: str, cwd: str, name: str, show: bool = True
) -> dict:
    """The Claude app's own Open: its tab for a session it runs, a resumed tab
    for an ended one. Then Forge is asked to show the Claude app, unless
    `show` is False (the Conversations view resumes it in place)."""
    port = manifest_port(role="claude")
    if not port:
        raise ActionError(404, "No Claude app found")
    got = http_json(
        port,
        f"/api/everyone/{session_id}/open",
        {"state": "cold" if state == "ended" else state, "cwd": cwd, "name": name},
    )
    try:
        http_json(port, f"/api/sessions/{session_id}/focus")
    except ActionError:
        pass  # the tab still opened; it just is not brought to the front
    shown = False
    if not show:
        return {"ok": True, "id": got.get("id"), "shown": False}
    try:
        borrow.setup()
        import forge_open  # pyright: ignore[reportMissingImports]

        shown = forge_open.request_open("claude") == "ok"
    except Exception:
        shown = False
    return {"ok": True, "id": got.get("id"), "shown": shown}


def _relay_post(path: str, doing: str) -> dict:
    port = manifest_port(name="relay")
    if not port:
        raise ActionError(404, "No Relay app found")
    try:
        return http_json(port, path)
    except ActionError as e:
        if e.status == 503:
            raise ActionError(
                503, f"The Relay page is not running; open Relay in Forge to {doing}"
            )
        raise


def relay(action: str) -> dict:
    if action not in ("pause", "resume"):
        raise ActionError(400, "Unknown Relay action")
    return _relay_post(f"/api/{action}", "pause or resume")


def relay_stop(number: int) -> dict:
    """Stop one Relay task and end its running session (the Stop button in
    the Conversations view, for a Relay run)."""
    return _relay_post(f"/api/tasks/{number}/stop", "stop a task")


def _claude_port() -> int:
    port = manifest_port(role="claude")
    if not port:
        raise ActionError(404, "No Claude app found")
    return port


ULTRATHINK = "ultrathink"
# What the pickers offer when the Claude app is closed (its runner.MODELS).
FALLBACK_OPTIONS = {
    "models": {
        "": "Claude Code's default",
        "opus": "Opus",
        "fable": "Fable",
        "claude-sonnet-5-5": "Sonnet 5.5",
        "haiku": "Haiku",
    },
    "efforts": {
        "": "Default",
        "low": "Low",
        "medium": "Medium",
        "high": "High",
        "xhigh": "Extra high",
        "max": "Max",
    },
}


def claude_options() -> dict:
    """The models and efforts the Claude app offers, for the composer's pickers."""
    try:
        got = http_json(_claude_port(), "/api/options", method="GET")
        return {
            "models": got.get("models") or FALLBACK_OPTIONS["models"],
            "efforts": got.get("efforts") or FALLBACK_OPTIONS["efforts"],
            "claude_app": True,
        }
    except ActionError:
        return {**FALLBACK_OPTIONS, "claude_app": False}


def say(
    session_id: str,
    text: str,
    *,
    state: str = "",
    cwd: str = "",
    name: str = "",
    model: str | None = None,
    effort: str | None = None,
    ultrathink: bool = False,
) -> dict:
    """A message from the conversation view's reply box.

    A session running in a Claude app tab gets it straight into that chat
    (model and effort set first, through the Claude app's own settings); an
    ended session is resumed in the Claude app and then sent it; any other
    live session (a terminal, a Relay run) gets it as a board note, the same
    as Message. Ultrathink adds the keyword Claude Code reads."""
    from mc import replies

    if ultrathink and ULTRATHINK not in text.lower():
        text = f"{ULTRATHINK}. {text}"
    tab = claude_names().get(session_id)
    if tab or state == "ended":
        port = _claude_port()
        if tab:
            conv, via = tab.get("id"), "claude"
        else:
            got = http_json(
                port,
                f"/api/everyone/{session_id}/open",
                {"state": "cold", "cwd": cwd, "name": name},
            )
            conv, via = got.get("id"), "resumed"
        if not conv:
            raise ActionError(502, "The Claude app did not say which chat it is")
        settings = {
            k: v for k, v in (("model", model), ("effort", effort)) if v is not None
        }
        if settings:
            http_json(port, f"/api/conversations/{conv}/settings", settings)
        http_json(port, f"/api/conversations/{conv}/send", {"text": text})
        return {"ok": True, "via": via, "conversation": conv}
    sent = message_session(session_id, text)
    replies.record("forge", sent["id"], text, "one", sent["to"], session_id)
    return {"ok": True, "via": "board", **sent}
