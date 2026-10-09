"""Acchan's backend: the Forge page, the terminal client, and Nyarch all talk
to this one process.

    /api/chat              POST {text, conversation?, tier?} -> server-sent events
    /api/voice/command     POST {text, use_model?, source?} -> one short spoken answer
    /api/stop              POST {conversation}
    /api/conversations     GET list; GET/DELETE /api/conversations/{id}
    /api/status            Jan, desktop, models, tool count
    /api/tools             the tool catalogue
    /api/jan/settings      per-tier model choice (shared/forge_jan.py)
    /api/tabs              the other Forge apps shown as tabs (Claude, Study)
    /v1/models, /v1/chat/completions
                           OpenAI-compatible, so Nyarch Assistant (or anything
                           that speaks the OpenAI API) gets the whole agent --
                           tools, fast path, escalation -- as if it were a model.

Standalone:
    cd ~/Forge/apps/acchan && FORGE_SHARED_DIR=~/Forge/shared \\
        .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8451
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from acchan import llm, registry, settings, voice, voice_command
from acchan.agent import Agent
from acchan.conversation import Conversation, valid_id
from acchan.desktop import current

import forge_jan  # on sys.path via acchan.llm

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
SHARED = Path(os.environ.get("FORGE_SHARED_DIR", ROOT.parent.parent / "shared"))
APPS = ROOT.parent

app = FastAPI(title="Acchan")
llm.JAN = forge_jan.mount(app, "acchan", roles=llm.TIERS)
forge_jan.long_entries(list(llm.BASE_MODELS.values()))
registry.load_all()

RUNNING: dict[str, Agent] = {}
RUN_LOCK = threading.Lock()  # one agent run at a time: one Jan lane


def _conversation(cid: str | None, source: str) -> Conversation:
    """The stored chat, or a new one. An id that is not a plain name (a path,
    a number, a dict) starts a fresh chat with an id of its own."""
    if not valid_id(cid):
        cid = None
    if cid:
        try:
            return Conversation.load(cid)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return Conversation(cid, source=str(source)[:40])


def _events(agent: Agent, text: str):
    """Run the agent in a thread and hand its events over a queue, so a slow
    client never blocks the model and a closed tab stops the run."""
    out: queue.Queue = queue.Queue()

    def work():
        if not RUN_LOCK.acquire(timeout=600):
            out.put(
                {"type": "error", "message": "Acchan is busy with another request."}
            )
            out.put(None)
            return
        try:
            if agent.stop_event.is_set():
                return  # the client left while this waited its turn
            RUNNING[agent.conv.id] = agent
            for event in agent.run(text):
                out.put(event)
        except Exception as exc:  # report, never hang the client
            out.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            RUNNING.pop(agent.conv.id, None)
            RUN_LOCK.release()
            out.put(None)

    threading.Thread(target=work, daemon=True, name="acchan-run").start()
    return out


@app.post("/api/chat")
def chat(payload: dict):
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "empty message")
    conv = _conversation(payload.get("conversation"), payload.get("source") or "web")
    tier = payload.get("tier") or None
    if tier not in (None, "switch", *llm.TIERS):
        tier = None
    agent = Agent(conv, cwd=payload.get("cwd") or None, forced_tier=tier)
    if isinstance(payload.get("thinking"), bool):
        agent.thinking = payload["thinking"]
    if payload.get("small_talk") is False:
        agent.small_talk = False
    events = _events(agent, text)
    return StreamingResponse(_sse(agent, events), media_type="text/event-stream")


def _sse(agent: Agent, events: queue.Queue):
    """The run's events as server-sent events. When the client goes away
    mid-reply (a closed page, a quit terminal client), the run is stopped:
    left alone it kept Jan generating for nobody, and the next message waited
    behind it."""
    finished = False
    try:
        yield f"data: {json.dumps({'type': 'start', 'conversation': agent.conv.id})}\n\n"
        while True:
            try:
                event = events.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if event is None:
                finished = True
                break
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
    finally:
        if not finished:
            agent.stop()


@app.get("/api/settings")
def get_settings():
    return settings.load()


@app.post("/api/settings")
def set_settings(payload: dict):
    try:
        return settings.save(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/shells/{name}/input")
async def shell_input(name: str, request: Request):
    """A line typed in a shell's window (acchan/shell_window.py), or ctrl+c."""
    from acchan import shells

    shell = shells.SHELLS.get(name)
    if not shell or not shell.alive():
        raise HTTPException(404, f"No background shell named '{name}'")
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise HTTPException(400, 'send {"text": "..."}')
    text = str(body.get("text", ""))
    shell.send(text, wait=0.1)
    return {"ok": True}


@app.post("/api/stop")
def stop(payload: dict):
    agent = RUNNING.get(str(payload.get("conversation") or ""))
    if agent:
        agent.stop()
        return {"stopped": True}
    for running in list(RUNNING.values()):
        running.stop()
    return {"stopped": bool(RUNNING)}


# --- voice: replies read aloud and a microphone (acchan/voice.py) ----------------


@app.get("/api/voice/status")
def voice_status():
    return voice.status()


@app.post("/api/voice/speak")
def voice_speak(body: dict):
    text = str(body.get("text") or "")
    if not voice.speech_text(text):
        raise HTTPException(400, "Nothing to say.")
    try:
        wav = voice.speak(text, str(body.get("voice") or settings.load()["voice"]))
    except voice.VoiceError as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(wav, media_type="audio/wav")


@app.post("/api/voice/listen")
async def voice_listen(request: Request):
    kind = request.headers.get("content-type", "audio/webm").split(";")[0]
    suffix = {"audio/wav": ".wav", "audio/ogg": ".ogg", "audio/mp4": ".m4a"}.get(
        kind, ".webm"
    )
    try:
        return {"text": voice.transcribe(await request.body(), suffix)}
    except voice.VoiceError as exc:
        raise HTTPException(503, str(exc)) from exc


class _VoiceAgent(Agent):
    """The agent for a spoken command: tools the voice may not run are
    refused with a note to confirm them in Acchan, and so are arguments the
    voice may not use (a screenshot over an existing file)."""

    allow = staticmethod(lambda name: True)

    def _run_tool(self, name, args_raw, tier):
        real = registry.resolve_name(name) or name
        if not self.allow(real):
            return False, voice_command.CONFIRM
        try:
            args = registry.parse_arguments(args_raw)
        except registry.ToolError:
            args = {}  # the call itself reports the bad arguments
        refusal = voice_command.arg_refusal(real, args)
        if refusal:
            return False, refusal
        return super()._run_tool(name, args_raw, tier)


def _voice_agent(text: str, deadline: float, allow) -> tuple[str, list[dict]]:
    """Run the agent once, without streaming, until `deadline`."""
    agent = _VoiceAgent(_conversation("voice", "voice"))
    agent.allow = staticmethod(allow)
    events = _events(agent, text)
    reply, done, calls, pending = "", None, [], {}
    while True:
        left = deadline - time.monotonic()
        try:
            event = events.get(timeout=max(left, 0.05))
        except queue.Empty:
            agent.stop()
            return "Sorry, that took too long.", calls
        if event is None:
            break
        kind = event.get("type")
        if kind == "text":
            reply += event.get("delta") or ""
        elif kind == "done":
            done = event.get("text")
        elif kind == "tool":
            pending[event.get("id")] = event
        elif kind == "result":
            start = pending.pop(event.get("id"), {})
            calls.append(
                {
                    "tool": event.get("name"),
                    "args": start.get("args") or {},
                    "ok": bool(event.get("ok")),
                }
            )
        elif kind == "error":
            reply = f"Sorry, something went wrong: {event.get('message')}"
    return done or reply, calls


@app.post("/api/voice/command")
def voice_command_route(body: dict, request: Request):
    """A spoken command: fast path, then phrases, then (use_model) Jan.

    Only callers sending `X-Forge: 1` with a Host of 127.0.0.1 or localhost
    (the Voice app, Forge pages; no DNS-rebinding page) get in, and
    the voice guard always applies here whatever `source` says: nothing risky
    runs from this route.
    """
    host = (request.headers.get("host") or "").rsplit(":", 1)[0]
    if request.headers.get("x-forge") != "1" or host not in ("127.0.0.1", "localhost"):
        raise HTTPException(403, "voice commands need X-Forge: 1 and a local Host")
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "empty command")
    return voice_command.handle(
        text,
        use_model=body.get("use_model", True) is not False,
        source="voice",
        agent=_voice_agent,
    )


@app.get("/api/conversations")
def conversations():
    return {"conversations": Conversation.list_all()}


@app.get("/api/conversations/{cid}")
def conversation(cid: str):
    try:
        conv = Conversation.load(cid)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(404, "no such conversation")
    return {
        "id": conv.id,
        "title": conv.title,
        "messages": conv.messages,
        "toolsets": conv.toolsets,
    }


@app.delete("/api/conversations/{cid}")
def delete_conversation(cid: str):
    try:
        Conversation.load(cid).delete()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return {"deleted": cid}


@app.get("/api/status")
def status():
    try:
        models = forge_jan.models(refresh=True)
        jan = True
    except Exception:
        models, jan = [], False
    return {
        "jan": jan,
        "desktop": current().name,
        "tiers": {tier: llm.model_for(tier) for tier in llm.TIERS},
        "models": models,
        "loaded": forge_jan.loaded_models(),
        "tools": len(registry.TOOLS),
        "busy": bool(RUNNING),
    }


@app.get("/api/tools")
def tools():
    return {
        "toolsets": registry.TOOLSETS,
        "tools": [
            {
                "name": t.name,
                "toolset": t.toolset,
                "signature": t.signature(),
                "description": t.description,
                "risky": t.risky,
            }
            for t in registry.TOOLS.values()
        ],
    }


@app.get("/api/tabs")
def tabs():
    """Other Forge apps shown as tabs inside Acchan. Declared in this app's
    forge_app.json ("tabs": [app names]); each tab reads that app's own
    manifest for its label and port, so nothing about them is copied here."""
    manifest = json.loads((ROOT / "forge_app.json").read_text(encoding="utf-8"))
    found = []
    for name in manifest.get("tabs", []):
        path = APPS / name / "forge_app.json"
        try:
            other = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        found.append(
            {
                "name": name,
                "label": other.get("label", name),
                "icon": other.get("icon", ""),
                "port": other.get("port"),
            }
        )
    return {"tabs": found}


# --------------------------------------------------------------- OpenAI API

MODEL_ID = "acchan"


@app.get("/v1/models")
def openai_models():
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {"id": MODEL_ID, "object": "model", "created": now, "owned_by": "forge"}
        ],
    }


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return ""


@app.post("/v1/chat/completions")
def openai_chat(payload: dict):
    """The whole agent behind the OpenAI chat API. The caller's own system
    prompt is dropped (Acchan's prompts are tuned for these models); its
    user/assistant turns become the conversation. Callers that keep their own
    history (Nyarch does) are matched to one stored conversation per caller
    so tool results from earlier turns are not lost."""
    messages = payload.get("messages") or []
    if not isinstance(messages, list):
        raise HTTPException(400, "messages must be a list")
    turns = [
        m
        for m in messages
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    ]
    if not turns or turns[-1].get("role") != "user":
        raise HTTPException(400, "the last message must be from the user")
    text = _text_of(turns[-1].get("content")).strip()
    if not text:
        raise HTTPException(400, "the last message is empty")
    # the caller names its stored chat, so only a plain name will do
    caller = "".join(
        c for c in str(payload.get("user") or "") if c.isalnum() or c in "_-"
    )
    caller = caller[:40] or "nyarch"
    cid = f"api-{caller}"
    conv = _conversation(cid, source=caller)
    if len(turns) == 1:
        # The caller started a new chat: start ours fresh too.
        conv = Conversation(cid, source=caller)
    agent = Agent(conv)
    events = _events(agent, text)
    stream = bool(payload.get("stream"))
    created = int(time.time())
    rid = "chatcmpl-" + uuid.uuid4().hex[:12]

    def chunk(delta: dict, finish=None) -> str:
        body = {
            "id": rid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": MODEL_ID,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"

    if stream:

        def gen():
            yield chunk({"role": "assistant"})
            sent = finished = False
            try:
                while True:
                    try:
                        event = events.get(timeout=15)
                    except queue.Empty:
                        yield ": keep-alive\n\n"
                        continue
                    if event is None:
                        finished = True
                        break
                    if event["type"] == "text" and event["delta"]:
                        sent = True
                        yield chunk({"content": event["delta"]})
                    elif event["type"] == "error":
                        sent = True
                        yield chunk(
                            {
                                "content": f"Sorry, something went wrong: {event['message']}"
                            }
                        )
            finally:
                if not finished:
                    agent.stop()  # the caller went away (see _sse)
            if not sent:
                yield chunk({"content": "Done."})
            yield chunk({}, "stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    reply = ""
    while True:
        event = events.get()
        if event is None:
            break
        if event["type"] == "text":
            reply += event["delta"]
        elif event["type"] == "error":
            reply = f"Sorry, something went wrong: {event['message']}"
    return JSONResponse(
        {
            "id": rid,
            "object": "chat.completion",
            "created": created,
            "model": MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply or "Done."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
    )


# ------------------------------------------------------------------ static


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


if SHARED.is_dir():
    app.mount("/shared", StaticFiles(directory=str(SHARED)), name="shared")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
