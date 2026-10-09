"""One spoken command in, one short spoken answer out (POST /api/voice/command).

Order: the no-model fast path (router.fast_path), then natural phrasing
(acchan/phrases.py), then, when `use_model` is set, the agent once. The answer
is plain JSON: {handled_by: fast|phrase|jan|none, reply, calls, ms}.

From `source: "voice"` a tool runs only when its `@tool(voice=...)` field says
so (registry.Tool.voice): "ok" may run from any path, "fast" only from the fast
path or a phrase (the model never gets it for a spoken request), and "no", the
default, never; unknown tools are refused too. The reply says to confirm it in
Acchan instead. open_terminal / terminal_new_tab with a command and launch_app
outside the installed desktop apps are refused by their arguments, and so is
take_screenshot / blender_viewport_shot with a path to a file or folder that
already exists (other than the tool's own default file; for Blender the name
with ".png" counts too), from any path, the model's included
(web_app._VoiceAgent).
"""

from __future__ import annotations

import inspect
import re
import time
from typing import Callable

from . import phrases, registry, router, voice

CONFIRM = "That one needs a yes from you: confirm it in Acchan."
NO_LAUNCH = "There is no installed app called {name}."
# A desktop entry whose command switches the machine off or restarts it.
POWER_EXEC = re.compile(
    r"\b(poweroff|reboot|shutdown|halt|suspend|hibernate|systemctl|loginctl)\b"
)
# Tools that run whatever command they are handed: from voice only without one.
# Which tools may run from voice at all is each tool's own `voice` field.
COMMAND_TOOLS = {"open_terminal", "terminal_new_tab"}
# Tools that save a picture where they are told: from voice never over a file
# that is already there ("save it as my notes file"), except their own default.
# The value is the extension the tool may put on the name it is given
# (Blender's screenshot can save "notes" as notes.png); that file counts too.
WRITE_TOOLS = {"take_screenshot": "", "blender_viewport_shot": ".png"}
NO_OVERWRITE = (
    "There is already a {kind} called {name}; I will not replace it from voice."
)

AgentRunner = Callable[[str, float, Callable[[str], bool]], tuple[str, list[dict]]]


def voice_blocked(name: str) -> bool:
    """True when the tool may not run from voice at all (unknown or "no")."""
    entry = registry.TOOLS.get(name)
    return entry is None or entry.voice == "no"


def voice_agent_allowed(name: str) -> bool:
    """May the model pick this tool for a spoken request? Only voice="ok"."""
    entry = registry.TOOLS.get(name)
    return entry is not None and entry.voice == "ok"


def launch_refusal(args: dict) -> str | None:
    """From voice, launch_app starts only an installed desktop app, never any
    program on PATH ("start reboot" must do nothing), and never an entry whose
    command powers the machine off. Returns the spoken refusal, or None."""
    from .tools import apps

    name = str(args.get("name") or "").strip()
    app = apps.find_app(name) if name else None
    if app is None or POWER_EXEC.search(str(app.get("exec") or "")):
        return NO_LAUNCH.format(name=name or "that")
    return None


def overwrite_refusal(name: str, args: dict) -> str | None:
    """From voice, a tool that saves to a given path may not replace a file
    that exists, unless it is the tool's own default file ("take a
    screenshot" twice). Returns the spoken refusal, or None."""
    from .sysutil import path as to_path

    given = str(args.get("path") or "").strip()
    entry = registry.TOOLS.get(name)
    if not given or entry is None:
        return None
    target = to_path(given)
    param = inspect.signature(entry.func).parameters.get("path")
    if param is not None and isinstance(param.default, str):
        if target == to_path(param.default):
            return None
    saved = [target]
    ext = WRITE_TOOLS.get(name, "")
    if ext and target.name and target.suffix.lower() != ext:
        saved.append(target.with_suffix(ext))
    for found in saved:
        if found.exists():
            kind = "folder" if found.is_dir() else "file"
            return NO_OVERWRITE.format(kind=kind, name=found.name or found)
    return None


def arg_refusal(name: str, args: dict) -> str | None:
    """Why a tool the voice may use must not run with these arguments."""
    if name in COMMAND_TOOLS and str(args.get("command") or "").strip():
        return CONFIRM
    if name == "launch_app":
        return launch_refusal(args)
    if name in WRITE_TOOLS:
        return overwrite_refusal(name, args)
    return None


def voice_refusal(name: str, args: dict) -> str | None:
    """Why a spoken call must not run, or None when it may."""
    if voice_blocked(name):
        return CONFIRM
    return arg_refusal(name, args)


def spoken(text: str, sentences: int = 2, limit: int = 240) -> str:
    """At most two short plain sentences."""
    words = voice.speech_text(text or "")
    parts = re.split(r"(?<=[.!?])\s+", words)
    out = " ".join(p for p in parts[:sentences] if p)
    if len(out) > limit:
        cut = out[:limit]
        out = (cut[: cut.rfind(" ")] if " " in cut else cut).rstrip(",;:") + "."
    return out


def _run(name: str, args: dict) -> tuple[bool, str]:
    try:
        return True, registry.call(name, args)
    except registry.ToolError as exc:
        return False, str(exc)


def handle(
    text: str,
    use_model: bool = True,
    source: str = "voice",
    agent: AgentRunner | None = None,
    cap_s: float = 90.0,
) -> dict:
    started = time.monotonic()
    guarded = source == "voice"

    def answer(handled_by: str, reply: str, calls: list[dict]) -> dict:
        return {
            "handled_by": handled_by,
            "reply": reply,
            "calls": calls,
            "ms": int((time.monotonic() - started) * 1000),
        }

    text = str(text or "").strip()
    if not text:
        return answer("none", "", [])

    fast = router.fast_path(text)
    if fast:
        refusals = [voice_refusal(c.tool, c.args) for c in fast] if guarded else []
        refusal = next((r for r in refusals if r), None)
        if refusal:
            calls = [{"tool": c.tool, "args": c.args, "ok": False} for c in fast]
            return answer("fast", refusal, calls)
        calls, replies = [], []
        for call in fast:
            ok, result = _run(call.tool, call.args)
            calls.append({"tool": call.tool, "args": call.args, "ok": ok})
            if not ok:
                replies.append(result)
                break
            replies.append(call.reply.replace("{result}", result))
        return answer("fast", spoken(" ".join(replies)), calls)

    found = phrases.match(text)
    if found:
        name, args, _confidence = found
        refusal = voice_refusal(name, args) if guarded else None
        if refusal:
            return answer(
                "phrase", refusal, [{"tool": name, "args": args, "ok": False}]
            )
        ok, result = _run(name, args)
        return answer(
            "phrase", spoken(result), [{"tool": name, "args": args, "ok": ok}]
        )

    if not use_model or agent is None:
        return answer("none", "", [])
    deadline = started + cap_s
    allow = voice_agent_allowed if guarded else (lambda name: True)
    reply, calls = agent(text, deadline, allow)
    return answer("jan", spoken(reply) or "Done.", calls)
