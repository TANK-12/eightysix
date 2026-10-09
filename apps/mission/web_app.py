"""Mission Control -- every Claude session, crew and Relay task in one place.

Combines what the Board, the Claude app's Everyone view, the Crew Room and
Relay show, by importing their readers (mc/borrow.py) rather than copying
them. Those apps keep working as they are. Reads are local files; writes
(notes, answers, Relay pause) go through the owning app's own code or API.

Every POST needs the header X-Mission: 1, which a page on another site
cannot send without a preflight this server never grants.
"""

from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from fastapi import Request  # noqa: E402
from fastapi.responses import FileResponse, Response  # noqa: E402

from mc import (
    actions,
    borrow,
    claude_proxy,
    convo,
    jan_ask,
    overview,
    relay_chat,
    replies,
)  # noqa: E402

borrow.setup()
import forge_attach  # noqa: E402  # pyright: ignore[reportMissingImports]
import forge_attach_api  # noqa: E402  # pyright: ignore[reportMissingImports]
import forge_jan  # noqa: E402  # pyright: ignore[reportMissingImports]

STATIC_DIR = os.path.join(ROOT, "static")
SESSION_ID = re.compile(r"^[0-9a-f-]{8,64}$")
AGENT_ID = re.compile(r"^[0-9a-zA-Z_-]{1,64}$")
NAME = re.compile(r"^\w[\w.-]{0,63}$")
MAX_TEXT = 4000

app = FastAPI(title="Mission Control")
# Mission Control's own Jan model (role "ask"), loaded only for a question.
jan = forge_jan.mount(app, "mission", roles=("ask",))


def same_site(x_mission: str = Header("")) -> None:
    if x_mission != "1":
        raise HTTPException(403, "Send X-Mission: 1")


guarded = [Depends(same_site)]


def _sources() -> overview.Sources:
    return overview.Sources(conversations=actions.claude_names)


def _check(pattern: re.Pattern, value: str, what: str) -> str:
    if not pattern.match(value or ""):
        raise HTTPException(400, f"That is not a {what}")
    return value


def _text(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise HTTPException(400, "Write something first")
    if len(text) > MAX_TEXT:
        raise HTTPException(400, f"Keep it under {MAX_TEXT} characters")
    return text


def _act(fn, *args):
    try:
        return fn(*args)
    except actions.ActionError as e:
        raise HTTPException(e.status, str(e))


@app.get("/api/overview")
def get_overview(sig: str = ""):
    data = overview.collect(_sources())
    if sig and sig == data["sig"]:
        return {"same": True, "sig": sig, "now": data["now"]}
    return data


def _transcript(session_id: str, agent: str | None = None) -> str:
    borrow.setup()
    from context import Context  # pyright: ignore[reportMissingImports]
    from sources import sessions as live  # pyright: ignore[reportMissingImports]

    path = live.find_transcript(Context(claude_dir=_sources().claude_dir), session_id)
    if not path:
        raise HTTPException(404, "No transcript for that session")
    if agent:
        import forge_helper_files  # pyright: ignore[reportMissingImports]

        found = forge_helper_files.transcript(
            os.path.join(os.path.dirname(path), session_id, "subagents"), agent
        )
        if not found:
            raise HTTPException(404, "No transcript for that helper")
        return found
    return path


@app.get("/api/sessions/{session_id}/conversation")
def conversation(session_id: str, before: int | None = None, agent: str = ""):
    _check(SESSION_ID, session_id, "session id")
    if before is not None and before < 0:
        raise HTTPException(400, "before must be 0 or more")
    if agent:
        _check(AGENT_ID, agent, "helper id")
    borrow.setup()
    import conversation as conv  # pyright: ignore[reportMissingImports]

    return conv.page(_transcript(session_id, agent or None), before)


@app.get("/api/sessions/{session_id}/events")
def session_events(
    session_id: str,
    before: int | None = None,
    after: int | None = None,
    agent: str = "",
):
    """The conversation as the Claude app's events (mc/convo.py): the newest
    page, an older one (before=) or what was written since (after=)."""
    _check(SESSION_ID, session_id, "session id")
    for value, what in ((before, "before"), (after, "after")):
        if value is not None and value < 0:
            raise HTTPException(400, f"{what} must be 0 or more")
    if agent:
        _check(AGENT_ID, agent, "helper id")
    return convo.page(_transcript(session_id, agent or None), before, after)


@app.get("/api/options")
def options():
    """Models and efforts for the reply box's pickers (the Claude app's own)."""
    return actions.claude_options()


def _transcript_or_none(session_id: str) -> str | None:
    try:
        return _transcript(session_id)
    except HTTPException:
        return None


@app.get("/api/messages")
def messages():
    """Messages sent from here, each with the answers that came back."""
    rows = overview.collect(_sources())["sessions"]
    return {"messages": replies.threads(rows, _transcript_or_none)}


@app.get("/api/sessions/{session_id}/where")
def where(session_id: str):
    _check(SESSION_ID, session_id, "session id")
    borrow.setup()
    import where as where_mod  # pyright: ignore[reportMissingImports]
    from context import Context  # pyright: ignore[reportMissingImports]

    info = where_mod.describe(Context.from_env(), session_id)
    if info is None:
        raise HTTPException(404, "Nothing is known about that session")
    return info


@app.get("/api/art")
def art_library():
    """The Crew Room's sprites and palette from the shared art library."""
    borrow.setup()
    import art  # pyright: ignore[reportMissingImports]

    return art.library()


class Text(BaseModel):
    text: str


class JanAsk(Text):
    agent: str = ""


class Note(BaseModel):
    text: str
    to: str | None = None
    re: int | None = None


class Say(BaseModel):
    text: str
    files: list[str] = []
    state: str = ""
    cwd: str = ""
    name: str = ""
    model: str | None = None
    effort: str | None = None
    ultrathink: bool = False


class Broadcast(BaseModel):
    text: str
    crew: str = "forge"


class Answer(BaseModel):
    note: str = ""


class Open(BaseModel):
    state: str = ""
    cwd: str = ""
    name: str = ""
    show: bool = True  # False: open it in the Claude app but stay in Mission


@app.post("/api/sessions/{session_id}/message", dependencies=guarded)
def message(session_id: str, body: Text):
    _check(SESSION_ID, session_id, "session id")
    text = _text(body.text)
    sent = _act(actions.message_session, session_id, text)
    replies.record("forge", sent["id"], text, "one", sent.get("to"), session_id)
    return sent


@app.post("/api/sessions/{session_id}/say", dependencies=guarded)
def say(session_id: str, body: Say):
    _check(SESSION_ID, session_id, "session id")
    for value, what in ((body.model, "model"), (body.effort, "effort")):
        if value is not None and value != "" and not NAME.match(value):
            raise HTTPException(400, f"That is not a {what}")
    return _act(
        lambda: actions.say(
            session_id,
            _with_files(body.text, body.files),
            state=body.state,
            cwd=body.cwd,
            name=body.name,
            model=body.model,
            effort=body.effort,
            ultrathink=body.ultrathink,
        )
    )


@app.post("/api/sessions/{session_id}/ask-jan", dependencies=guarded)
def ask_jan(session_id: str, body: JanAsk):
    _check(SESSION_ID, session_id, "session id")
    if body.agent:
        _check(AGENT_ID, body.agent, "helper id")
    question = _text(body.text)
    events = convo.page(_transcript(session_id, body.agent or None))["events"]
    return _act(jan_ask.ask, jan, question, events)


@app.post("/api/broadcast", dependencies=guarded)
def broadcast(body: Broadcast):
    """A note to everyone that asks for answers back (mc/replies.py)."""
    crew = _check(NAME, body.crew, "crew name")
    if crew not in borrow.board()._crew_names():
        raise HTTPException(404, f"There is no {crew} board")
    return _act(replies.broadcast, _text(body.text), crew)


@app.post("/api/sessions/{session_id}/open", dependencies=guarded)
def open_in_claude(session_id: str, body: Open):
    _check(SESSION_ID, session_id, "session id")
    return _act(
        actions.open_in_claude, session_id, body.state, body.cwd, body.name, body.show
    )


@app.post("/api/go/{name}", dependencies=guarded)
def go(name: str):
    return _act(actions.go_to, _check(NAME, name, "session name"))


@app.post("/api/crews/{crew}/notes", dependencies=guarded)
def note(crew: str, body: Note):
    _check(NAME, crew, "crew name")
    if body.to:
        _check(NAME, body.to, "member name")
    return _act(actions.post_note, crew, _text(body.text), body.to, body.re)


@app.post("/api/crews/{crew}/notes/{note_id}/ack", dependencies=guarded)
def ack(crew: str, note_id: int, body: Answer):
    _check(NAME, crew, "crew name")
    return _act(actions.ack_note, crew, note_id, body.note.strip()[:MAX_TEXT])


@app.post("/api/relay/{action}", dependencies=guarded)
def relay(action: str):
    return _act(actions.relay, action)


@app.post("/api/relay/tasks/{number}/stop", dependencies=guarded)
def relay_stop(number: int):
    if not 0 < number < 1_000_000:
        raise HTTPException(400, "That is not a task number")
    return _act(actions.relay_stop, number)


# --- the WhatsApp chat with Relay, mirrored live (mc/relay_chat.py)

VERSION = re.compile(r"^[0-9a-f]{0,16}$")


class RelaySay(Text):
    boss: bool = False
    files: list[str] = []


@app.get("/api/relay-chat")
def relay_chat_thread(seen: str = ""):
    return _act(relay_chat.thread, _check(VERSION, seen, "chat version"))


@app.post("/api/relay-chat/say", dependencies=guarded)
def relay_chat_say(body: RelaySay):
    return _act(relay_chat.say, _with_files(body.text, body.files), body.boss)


# --- attachments for the Relay chat and transcript chats (Relay task 118).
# Claude app chats keep using that app's own per-conversation upload
# (mc/claude_proxy.py); these land in Mission's data folder, one folder a
# day, and go to the session as "Attached files:" lines (shared/forge_attach.py).

ATTACH = forge_attach_api.Attachments(
    lambda: os.path.join(replies.data_dir(), "attachments")
)
app.include_router(ATTACH.router(dependencies=guarded))


def _with_files(text: str, files: list[str]) -> str:
    """`text` with the attached files' note (only files Mission saved)."""
    paths = ATTACH.paths(files)
    if not paths or (text or "").strip():
        text = _text(text)  # the limit is for what he typed, not the file list
    return forge_attach.with_note(text or "", paths)


# --- the Conversations view: the Claude app's own chats (mc/claude_proxy.py)


def _conv(conv_id: str) -> str:
    return _check(claude_proxy.CONV_ID, conv_id, "conversation id")


@app.get("/claude-ui/{name}")
def claude_ui(name: str):
    """The Claude app's run_controls.js, enjoy_logic.js and their css, as is."""
    path = claude_proxy.ui_file(name)
    if not path:
        raise HTTPException(404, "Not one of the Claude app's shared files")
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


@app.get("/api/claude/options")
def claude_options():
    return _act(claude_proxy.options)


@app.get("/api/claude/conversations/{conv_id}/events")
def claude_events(conv_id: str, after: int = -1, wait: float = 0, boot: str = ""):
    if not re.match(r"^[0-9a-zA-Z_-]{0,64}$", boot):
        raise HTTPException(400, "That is not a boot id")
    return _act(claude_proxy.events, _conv(conv_id), after, wait, boot)


@app.get("/api/claude/conversations/{conv_id}/files/{name}")
def claude_picture(conv_id: str, name: str):
    """A picture attached to a Claude app chat. Unguarded like the Claude
    app's own route (an <img> cannot send headers): pictures only."""
    if not claude_proxy.IMAGE_NAME.match(name):
        raise HTTPException(400, "That is not a picture name")
    data, media = _act(claude_proxy.image, _conv(conv_id), name)
    return Response(data, media_type=media, headers={"Cache-Control": "no-cache"})


class Link(BaseModel):
    url: str


@app.post("/api/claude/open-link", dependencies=guarded)
def claude_open_link(body: Link):
    return _act(claude_proxy.open_link, body.url)


@app.post("/api/claude/conversations/{conv_id}/{action}", dependencies=guarded)
async def claude_act(conv_id: str, action: str, request: Request):
    _conv(conv_id)
    if action not in claude_proxy.CONV_ACTIONS:
        raise HTTPException(404, "Not something this view can do")
    raw = await request.body()
    if len(raw) > claude_proxy.MAX_BODY:
        raise HTTPException(413, "That is too big to send")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "Send JSON")
    if not isinstance(body, dict):
        raise HTTPException(400, "Send a JSON object")
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(_act, claude_proxy.act, conv_id, action, body)


app.mount("/shared", StaticFiles(directory=borrow.SHARED), name="shared")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
