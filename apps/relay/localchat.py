"""The local chat: a small Jan model answers WhatsApp when Claude cannot.

Emerson (2026-10-07): a fallback chat on a small local model (under 4B),
switched on when he asks ("local") or by itself when Claude is out of usage,
and back to Claude when he says so ("claude") or when usage returns. It
answers in plain words about Relay, usage, Forge and the laptop, may look
things up, and is discouraged from changing anything because it is weak.

Who answers the chat is the setting `whatsapp_frontdesk`:

    off    Claude (the standing chat task); the default
    jan    the front desk (frontdesk.py): Jan first, hands off to Claude
    local  this: the local model answers everything, no usage

and `whatsapp_fallback` ("auto", the default, or "off"): with auto, while
the Claude chat has no usage to start (state `chat_wait`), this answers too.

The model gets a Facts block (time, why it is answering, Relay's tasks and
usage, the laptop) and the recent chat. It may ask for more with one line
`LOOKUP <name> [what]` (the LOOKUPS registry; read-only, two per message)
and may end with `ACTION <relay command>` lines, which Relay runs only for
the commands in ALLOWED_ACTIONS. Its instructions are localchat_prompt.md
(plain text, read on every message); its model is role `local` in
~/.config/forge/jan/relay.json (`local model 2b` from WhatsApp sets it).
Jan's model server is started if it is down (forge_jan.ensure_router), so
this works with Claude switched off and the Jan app closed.

    .venv/bin/python localchat.py --bench [model ...]   score models
"""

from __future__ import annotations

import json
import os
import re
import shlex
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
SHARED = Path(os.environ.get("FORGE_SHARED_DIR") or ROOT.parent.parent / "shared")
for extra in (str(ROOT), str(SHARED)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

import actions  # noqa: E402
import chat  # noqa: E402
import commands  # noqa: E402
import forge_jan  # noqa: E402
import forge_sysinfo  # noqa: E402
import forge_websearch  # noqa: E402
import items  # noqa: E402
import meters  # noqa: E402
import quick  # noqa: E402
import store  # noqa: E402

PROMPT_FILE = ROOT / "localchat_prompt.md"
SAMPLES = ROOT / "tests" / "localchat_samples.json"
ROLE = "local"
# Picked by the 2026-10-07 benchmark (docs/library/models/
# 2026-10-07-relay-local-chat-bench.md): the best middle of smart and fast.
# Emerson (15:40): "I have the RAM, I want lots of context, about 30k at
# least", so the 2B and 4B run as their -long copies (forge_jan.long_entries,
# 131072 tokens); the plain names are the fallback when Jan lacks a copy.
BASE_2B = "Qwen3_5-2B-Uncensored-HauhauCS-Aggressive-Q4_K_M"
DEFAULT_MODEL = BASE_2B + forge_jan.LONG_SUFFIX
# Short names Emerson can type after "local model".
CANDIDATES = {
    "0.8b": "qwen35-0_8b-spectralquant-calib360-q4_k_m",
    "2b": DEFAULT_MODEL,
    "4b": "Qwen3_5-4B-IQ4_XS" + forge_jan.LONG_SUFFIX,
}
JAN = forge_jan.AppJan("relay", roles=("frontdesk", ROLE))
# boss: every plain message goes to the boss line (bossline.py).
MODES = {"claude": "off", "desk": "jan", "local": "local", "boss": "boss"}
RECENT = 40  # chat entries the model sees; each is cut at ENTRY_CHARS
ENTRY_CHARS = 1500
# ...and all of them together at HISTORY_CHARS, newest kept: the 2B reads
# about 170 tokens/s here, so 12000 characters (~3000 tokens) is ~18 s a turn.
HISTORY_CHARS = 12000
LOOKUP_CHARS = 6000
MAX_LOOKUPS = 2
LOOKUP = re.compile(r"^\s*\**LOOKUP\**\s*:?\s*([a-z]+)\s*(.*)$", re.I)
ACTION = re.compile(r"^\s*\**ACTION\**\s*:?\s*(.+)$", re.I)
ALLOWED_ACTIONS = ("stop", "retry", "pause", "resume", "tell", "work", "progress")
ALLOWED_QUICK = (
    "kill",
    "kill-task",
    "kill-all",
    "top-cpu",
    "top-gpu",
    "stats",
    "send-found",
)


# ---- who answers --------------------------------------------------------------------


def mode(settings: dict | None = None) -> str:
    """claude, desk, local or boss: the mode Emerson picked."""
    value = (settings or store.settings()).get("whatsapp_frontdesk") or "off"
    return {v: k for k, v in MODES.items()}.get(value, "claude")


def fallback_on(settings: dict | None = None) -> bool:
    return (settings or store.settings()).get("whatsapp_fallback", "auto") == "auto"


def active(settings: dict | None = None, state: dict | None = None) -> bool:
    """True when the local model answers new chat messages: picked, or
    standing in while the Claude chat has no usage."""
    settings = settings or store.settings()
    if mode(settings) == "local":
        return True
    state = state if state is not None else store.state()
    return fallback_on(settings) and bool(state.get("chat_wait"))


def model() -> str:
    name = JAN.model_for(ROLE, DEFAULT_MODEL)
    if name.endswith(forge_jan.LONG_SUFFIX):
        try:
            listed = forge_jan.models()
        except forge_jan.JanError:
            listed = []
        if listed and name not in listed:
            return name[: -len(forge_jan.LONG_SUFFIX)]
    return name


def short_name(name: str) -> str:
    plain = name.removesuffix(forge_jan.LONG_SUFFIX)
    return next(
        (
            k
            for k, v in CANDIDATES.items()
            if v.removesuffix(forge_jan.LONG_SUFFIX) == plain
        ),
        name,
    )


# ---- thinking -----------------------------------------------------------------------

# Qwen3.5 can reason before it answers. That costs time on this laptop's CPU,
# so "auto" thinks only when a message looks like it needs it (HARD), "on"
# always, "off" never. Setting local_thinking; quick command think on/off/auto.
# Off by default (Emerson, 2026-10-07, "maybe we don't need thinking"): on the
# 2B a thinking answer took 176 s against about 10 s without (bench doc).
THINK_MODES = ("auto", "on", "off")
HARD = re.compile(
    r"\bwhy\b|\bexplain|\bcompare|\bversus\b|pros and cons|\bplan\b|"
    r"should i|which (is|one|would)|work out|calculate|how (would|should|do i|come)|"
    r"\bthink\b|reason|figure out|what if|difference between|\bdebug|\bwhy's",
    re.I,
)
THINK_TOKENS = 1500


# ---- what it knows about itself ------------------------------------------------------

# Emerson asked "what model are you" and got "4B", "Qwen3.5 256K" and "Jan
# 128 KB", all wrong. So the facts carry its real name, size, context window
# and measured speed (speed_file, written after every answer).


def speed_file() -> Path:
    return store.path("local_speed.json")


def record_speed(name: str, stats: dict) -> None:
    if not stats.get("gen_tps"):
        return
    speeds = store.read_json(speed_file()) or {}
    speeds[name] = {**stats, "at": time.time()}
    store.write_json(speed_file(), speeds)


def size_of(name: str) -> str:
    """ "Qwen3_5-2B-..." -> "2B", "qwen35-0_8b-..." -> "0.8B"."""
    m = re.search(r"(?<![\d.])(\d+(?:[._]\d+)?)b(?![a-z])", name.lower())
    return m.group(1).replace("_", ".") + "B" if m else "unknown size"


def self_facts(name: str) -> str:
    family = "Qwen3.5" if re.search(r"qwen3[._]?5", name, re.I) else name.split("-")[0]
    ctx = forge_jan.context_size(name)
    line = (
        f"{family} {size_of(name)} ({size_of(name).rstrip('B')} billion parameters), "
        f"Jan model {name}, on this laptop through Jan's llama.cpp server. "
        + (f"Context window {ctx} tokens. " if ctx else "")
    )
    speed = (store.read_json(speed_file()) or {}).get(name) or {}
    if speed.get("gen_tps"):
        line += (
            f"Last measured: {speed['gen_tps']:.0f} tokens/s writing, "
            f"{speed.get('prompt_tps') or 0:.0f} tokens/s reading. "
        )
    return line + f"Thinking before answering: {thinking_mode()}."


def thinking_mode(settings: dict | None = None) -> str:
    value = (settings or store.settings()).get("local_thinking", "off")
    return value if value in THINK_MODES else "off"


def should_think(text: str, settings: dict | None = None) -> bool:
    picked = thinking_mode(settings)
    if picked != "auto":
        return picked == "on"
    return bool(HARD.search(text)) or len(text.split()) > 60


def set_thinking(value: str) -> str:
    value = value.strip().lower()
    if value not in THINK_MODES:
        return "Write think on, think off or think auto."
    store.save_settings({"local_thinking": value})
    store.event("chat", f"local thinking set to {value}")
    return {
        "auto": "The local model now thinks first only on harder questions (why, how, compare, plans).",
        "on": "The local model now thinks before every answer: smarter, but slower.",
        "off": "The local model now answers straight away, no thinking.",
    }[value]


def describe() -> str:
    settings, state = store.settings(), store.state()
    picked = mode(settings)
    if picked == "local":
        who = f"The local model ({short_name(model())}) answers, no usage. Write claude to go back."
    elif active(settings, state):
        who = (
            f"Claude is out of usage, so the local model ({short_name(model())}) "
            "stands in until it is back."
        )
    elif picked == "boss":
        who = "The boss line: every message goes straight to Relay's boss. Write claude to go back."
    elif picked == "desk":
        who = "The front desk: the local model answers first and passes bigger things to Claude."
    else:
        claude, effort = chat.chat_model(settings)
        who = f"Claude answers ({claude} {effort}). Write local for the local model."
    auto = "on" if fallback_on(settings) else "off"
    return (
        f"{who}\nStand-in when Claude is out of usage: {auto}."
        f"\nLocal thinking: {thinking_mode(settings)}."
    )


def set_mode(name: str) -> str:
    name = name.strip().lower()
    if name not in MODES:
        return "Mode must be claude, desk, local or boss."
    store.save_settings({"whatsapp_frontdesk": MODES[name]})
    store.event("chat", f"chat mode set to {name}")
    task = chat.chat_task(create=False)
    if name == "local":
        forge_jan.ensure_router(
            wait=0.0
        )  # starts Jan now, so the first answer is quicker
        return (
            f"Local chat on: {short_name(model())} on the laptop answers from now on, "
            "no usage. Write claude to switch back."
        )
    if task and task.get("status") == chat.DESK and not store.state().get("chat_wait"):
        task.update(status=chat.IDLE)
        items.save(task)
    if name == "boss":
        return (
            "Boss line on: every message now goes straight to Relay's boss "
            "(what runs, ETAs, usage, stop, queue or tell a task). Write claude, "
            "desk or local to go back."
        )
    if name == "desk":
        return "Front desk on: the local model answers first and passes bigger things to Claude."
    if store.state().get("chat_wait"):
        return (
            "Back to Claude, but Claude is out of usage right now, so the local "
            "model keeps answering until it is back."
        )
    return "Back to the Claude chat."


def pick_model(choice: str = "") -> str:
    choice = choice.strip().lower().replace(" ", "")
    available = forge_jan.models()
    if not choice:
        lines = [
            f"The local model is {short_name(model())}. Pick one with local model 2b:"
        ]
        for short, name in CANDIDATES.items():
            mark = " (now)" if name == model() else ""
            missing = "" if not available or name in available else " (not in Jan)"
            lines.append(f"- {short}{mark}{missing}")
        lines.append("Smaller answers faster, bigger answers better.")
        return "\n".join(lines)
    name = CANDIDATES.get(choice) or next(
        (m for m in available if choice in m.lower().replace("_", "").replace("-", "")),
        "",
    )
    if not name:
        return f"No local model called {choice}. Try 0.8b, 2b or 4b."
    JAN.update({"models": {ROLE: name}})
    store.event("chat", f"local model set to {name}")
    return f"The local chat now runs on {short_name(name)}."


# ---- what it knows ------------------------------------------------------------------


def _top(kind: str) -> str:
    if kind == "gpu":
        import forge_gpuload

        rows = forge_gpuload.top_gpu(8, 1.0)
        return (
            "\n".join(f"{r['name']} {r['share'] * 100:.0f}% GPU" for r in rows)
            or "nothing on the GPU"
        )
    rows = forge_sysinfo.top_cpu(8, 1.0)
    return "\n".join(f"{r['comm']} {r['cpu']}% CPU, {r['mem_mb']} MB" for r in rows)


def _disks(_arg: str = "") -> str:
    return "\n".join(
        f"{d['name']} ({d['mount']}): {d['used']}% used, {d['free_gb']} GB free"
        for d in forge_sysinfo.disks()
    )


def _forge(_arg: str = "") -> str:
    """Which Forge apps answer on their port right now."""
    up, down = [], []
    for manifest in sorted((ROOT.parent).glob("*/forge_app.json")):
        data = store.read_json(manifest) or {}
        port = data.get("port")
        if not port:
            continue
        with socket.socket() as s:
            s.settimeout(0.2)
            (up if s.connect_ex(("127.0.0.1", int(port))) == 0 else down).append(
                data.get("label") or manifest.parent.name
            )
    forge = subprocess.run(
        ["pgrep", "-f", "[F]orge/forge.py"], capture_output=True, text=True
    ).stdout.strip()
    return (
        f"Forge window {'open' if forge else 'closed'}. Apps up: "
        + (", ".join(up) or "none")
        + f". Not running: {len(down)}."
    )


def _events(_arg: str = "") -> str:
    rows = store.events(12)
    return "\n".join(
        f"{time.strftime('%H:%M', time.localtime(e.get('at', 0)))} {e.get('kind')}: "
        f"{str(e.get('text', ''))[:120]}"
        for e in rows
    )


def _board(_arg: str = "") -> str:
    out = subprocess.run(
        [
            sys.executable,
            str(Path.home() / ".claude/skills/crew/crew.py"),
            "dump",
            "forge",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout
    return "\n".join(out.strip().splitlines()[-8:])[-1500:] or "board empty"


def _file(arg: str) -> str:
    path = Path(os.path.expanduser(arg.strip() or "~")).resolve()
    if not str(path).startswith(str(Path.home())) or "/secrets" in str(path):
        return "Only files in his home folder, and never Relay's secrets."
    if path.is_dir():
        names = sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())
        return f"{path}: " + ", ".join(names[:60])
    try:
        text = path.read_text(errors="replace")
    except OSError as e:
        return f"Cannot read it: {e.strerror}"
    return text[:1500]


SHELL_OK = (  # read-only programs the model may run, with any arguments
    "uptime",
    "df",
    "free",
    "sensors",
    "ps",
    "date",
    "who",
    "lsblk",
    "nmcli",
    "ip",
    "uname",
    "journalctl",
    "systemctl",
    "pgrep",
    "ls",
    "du",
    "wc",
    "git",
)
SHELL_ARGS_OK = {"systemctl": ("status", "--user", "is-active", "list-units")}
SHELL_GIT_OK = ("status", "log", "diff", "show")


def _shell(arg: str) -> str:
    try:
        argv = shlex.split(arg)
    except ValueError:
        return "Could not read that command."
    if not argv or argv[0] not in SHELL_OK:
        return "Only these read-only programs: " + ", ".join(SHELL_OK)
    if argv[0] == "systemctl" and not set(argv[1:]) & set(SHELL_ARGS_OK["systemctl"]):
        return "systemctl only for status."
    if argv[0] == "systemctl" and any(
        a in ("start", "stop", "restart", "enable", "disable", "kill") for a in argv
    ):
        return "systemctl only for status."
    if argv[0] == "git" and (len(argv) < 2 or argv[1] not in SHELL_GIT_OK):
        return "git only for status, log, diff and show."
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"It failed: {e}"
    return (done.stdout + done.stderr).strip()[:1500] or "(no output)"


WEB_FILLER = re.compile(
    r"^(please |can you |could you |pls )*(search|google|look up|look it up|find|check)"
    r"( the| on the)?( web| internet| online)?( for| about)?\s+",
    re.I,
)


def _web(arg: str) -> str:
    query = WEB_FILLER.sub("", arg.strip()).strip(" ?.!") or arg
    return forge_websearch.text(query[:200], 6)


PRIVATE_HOST = re.compile(
    r"^(localhost|127\.|0\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|\[?::1|.*\.local$)",
    re.I,
)


def _page(arg: str) -> str:
    found = re.findall(r"https?://\S+|\b[\w.-]+\.[a-z]{2,}/\S*", arg)
    url = found[0] if found else arg.strip()
    host = re.sub(r"^https?://", "", url).split("/")[0].split(":")[0]
    if not re.match(r"^(https?://)?[\w.-]+\.[a-z]{2,}", url) or PRIVATE_HOST.match(
        host
    ):
        return "Only public web pages can be read."  # never this laptop's own apps
    return forge_websearch.page_text(url, LOOKUP_CHARS)


def _progress(arg: str) -> str:
    number = re.search(r"\d+", arg)
    return actions.progress_text(int(number.group()) if number else None)


@dataclass
class Lookup:
    gives: str  # what the prompt says it gives
    run: Callable[[str], str]  # its argument is what follows the name
    words: str = ""  # a regex: a message matching it gets this looked up first


# Small models rarely ask for a lookup themselves (2026-10-07 bench), so
# Relay looks up what a message's words point at before asking (`words`),
# and the model may still ask with a LOOKUP line. A new lookup is one entry.
LOOKUPS: dict[str, Lookup] = {
    "progress": Lookup(
        "where running tasks are, or one task (progress 12)",
        _progress,
        r"progress|how far|how.s .*(job|task|going)|status of|\btask \d+|\bjob\b",
    ),
    "usage": Lookup("Claude usage meters and resets", lambda a: _usage_lines()),
    "cpu": Lookup(
        "top CPU programs",
        lambda a: _top("cpu"),
        r"\bcpu\b|hog|slow|laggy|lag\b|using (all|so much)|eating|process",
    ),
    "gpu": Lookup("top GPU programs", lambda a: _top("gpu"), r"\bgpu\b|graphics"),
    "disks": Lookup(
        "drives and free space", _disks, r"disk|space|storage|drive|\bssd\b"
    ),
    "forge": Lookup(
        "which Forge apps run", _forge, r"forge|apps? (are )?(open|running|up)"
    ),
    "events": Lookup(
        "Relay's recent event log", _events, r"\blog\b|events|what happened"
    ),
    "board": Lookup(
        "the crew board (what Claude sessions say)",
        _board,
        r"board|sessions? (say|doing)|crew",
    ),
    "tasks": Lookup("Relay's tasks in full", lambda a: actions.status_text()),
    "file": Lookup("a file or folder in his home (file ~/Forge/README.md)", _file),
    "find": Lookup(
        "search his files by name (find report); numbered, send 2 sends one",
        lambda a: quick.find_text(a),
    ),
    "shell": Lookup("a read-only command (shell df -h)", _shell),
    "web": Lookup(
        "search the web (web <search words>); titles, links, snippets",
        _web,
        r"^(?!.*\b(files?|folders?|pdf|docs?|tasks?|jobs?|relay|forge|usage|laptop|cpu|gpu)\b)"
        r".*(\bweb\b|google|online|internet|"
        r"\bnews\b|weather|search (for|up)|look (it |that )?up|latest|price of|who won)",
    ),
    "page": Lookup("read one web page (page <address>)", _page),
}


def lookup(name: str, arg: str = "") -> str:
    entry = LOOKUPS.get(name.lower())
    if not entry:
        return f"No lookup called {name}. Names: {', '.join(LOOKUPS)}."
    try:
        return entry.run(arg)[:LOOKUP_CHARS]
    except Exception as e:  # a lookup never breaks the chat
        return f"That lookup failed: {type(e).__name__}: {e}"


def auto_lookups(messages: list[str]) -> list[str]:
    """The lookups a message's words point at (LOOKUPS[...].words)."""
    said = " ".join(_said(m)[1] for m in messages).lower()
    return [
        name
        for name, entry in LOOKUPS.items()
        if entry.words and re.search(entry.words, said)
    ][:3]


def _usage_lines() -> str:
    """One plain line per account and which can take work (meters.describe)."""
    readings = store.state().get("meters") or {}
    return "\n".join(meters.describe(readings, store.settings())) or "no usage readings"


def _compact_status() -> str:
    text = actions.status_text().split("\nUsage:")[0]
    keep = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(keep)[:1200]


def facts(settings: dict | None = None, state: dict | None = None) -> str:
    settings = settings or store.settings()
    state = state if state is not None else store.state()
    if mode(settings) == "local":
        why = "Emerson switched the chat to you (local)."
    else:
        why = (
            "Claude is out of usage"
            + (f" ({state.get('chat_wait')})" if state.get("chat_wait") else "")
            + ", so you stand in."
        )
    return "\n".join(
        [
            f"Now: {time.strftime('%A %d %B %Y, %H:%M')}",
            f"Why you are answering: {why}",
            f"You are: {self_facts(model())}",
            "Relay:\n" + _compact_status(),
            "Claude usage:\n" + _usage_lines(),
            "Laptop:\n" + quick.stats_text(0.3),
        ]
    )


def system_prompt() -> str:
    try:
        text = PROMPT_FILE.read_text(encoding="utf-8")
    except OSError:
        text = "You are Relay's local chat. Answer Emerson briefly. {lookups}"
    names = "; ".join(f"{k} ({v.gives})" for k, v in LOOKUPS.items())
    return text.replace("{lookups}", names)


# "Wed 15:48 Emerson: hi" (chat.py's stamp); older entries had no weekday.
# Missing the weekday once made every line Emerson's, timestamps included.
ENTRY = re.compile(r"^(?:[A-Z][a-z]{2} )?(?:\d\d:\d\d )?(\w+): (.*)$", re.S)


def _said(entry: str) -> tuple[str, str]:
    """A Messages entry ("10:31 Emerson: hi") -> (who, text)."""
    entry = entry[len(chat.NEW) :] if entry.startswith(chat.NEW) else entry
    m = ENTRY.match(entry.strip())
    return (m.group(1), m.group(2).strip()) if m else ("Emerson", entry.strip())


def conversation(
    task: dict, messages: list[str], known: str, looked: str = ""
) -> list[dict]:
    """The request as real chat turns: the instructions and facts, the last
    RECENT messages as user/assistant turns, then his new message(s). Facts
    sent with his message instead (so the history could be cached) made the
    2B loop and mistake them for orders (2026-10-07 bench), so they stay in
    the system turn."""
    system = system_prompt() + "\n\nFacts (live, trust these):\n" + known
    if looked:
        system += "\n\nLooked up for this message:\n" + looked
    turns: list[dict] = []
    entries = chat._split(task.get("body", ""))[1]
    recent: list[tuple[str, str]] = []
    budget = HISTORY_CHARS
    for entry in reversed([e for e in entries if not e.startswith(chat.NEW)][-RECENT:]):
        who, text = _said(entry)
        budget -= min(len(text), ENTRY_CHARS)
        if budget < 0:
            break
        recent.insert(0, (who, text))
    for who, text in recent:
        role = "user" if who == "Emerson" else "assistant"
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n" + text[:ENTRY_CHARS]
        else:
            turns.append({"role": role, "content": text[:ENTRY_CHARS]})
    while turns and turns[0]["role"] == "assistant":
        turns.pop(0)
    new = "\n".join(_said(m)[1] for m in messages)
    if turns and turns[-1]["role"] == "user":
        turns.pop()  # an unanswered earlier message: the new one says it again
    return [
        {"role": "system", "content": system},
        *turns,
        {"role": "user", "content": new},
    ]


# A bare command line in the reply ("tell 15:06 ok", "stop 12") is the model
# half-writing an ACTION: never run, and not sent to him either.
BARE_COMMAND = re.compile(
    r"^\s*\**(tell|stop|retry|kill|send|progress|new:|work:)\b.*\d"
    r"|^\s*\**(pause|resume|kill all|new:.*)\**\s*$",
    re.I,
)


def parse(answer: str) -> tuple[str, list[str]]:
    """The model's answer -> (text for Emerson, ACTION commands)."""
    text, acts = [], []
    for line in answer.strip().splitlines():
        m = ACTION.match(line)
        if m:
            act = m.group(1).strip().strip("`*").strip()
            if act:
                acts.append(act)
        elif not LOOKUP.match(line) and not BARE_COMMAND.match(line):
            text.append(line)
    return "\n".join(text).strip(), acts


def wanted_lookups(answer: str) -> list[tuple[str, str]]:
    found = []
    for line in answer.strip().splitlines():
        m = LOOKUP.match(line)
        if m:
            found.append((m.group(1).lower(), m.group(2).strip()))
    return found


def ask(
    task: dict,
    messages: list[str],
    known: str | None = None,
    name: str = "",
    asker: Callable[[list[dict]], str] | None = None,
    look: Callable[[str, str], str] | None = None,
    think: bool | None = None,
) -> str:
    """The model's final answer. Relay looks up what the message points at
    first; the model may ask for up to MAX_LOOKUPS more. Starts Jan's model
    server if it is down; raises forge_jan.JanError when it cannot."""
    name = name or model()
    said = " ".join(_said(m)[1] for m in messages)
    if think is None:
        think = should_think(said)
    if asker is None:
        if not forge_jan.ensure_router(wait=60.0):
            raise forge_jan.JanError("Jan's model server would not start")

        def jan_asker(turns: list[dict]) -> str:
            stats: dict = {}
            try:
                return _jan_answer(turns, stats)
            finally:
                record_speed(name, stats)

        def _jan_answer(turns: list[dict], stats: dict) -> str:
            with JAN.using(name):
                if think:
                    try:
                        return forge_jan.chat_messages(
                            name,
                            turns,
                            temperature=0.6,
                            max_tokens=THINK_TOKENS,
                            timeout=180,
                            thinking=True,
                            extra={"top_p": 0.95, "top_k": 20},
                            stats=stats,
                        )
                    except forge_jan.JanError as e:
                        if "busy" in str(e):
                            raise  # thought too long or timed out: answer without it
                return forge_jan.chat_messages(
                    name,
                    turns,
                    temperature=0.4,
                    max_tokens=300,
                    timeout=240,
                    extra={"top_p": 0.9, "top_k": 20},
                    stats=stats,
                )

        asker = jan_asker
    look = look or lookup
    known = known if known is not None else facts()
    done: list[str] = []
    looked = ""
    for lname in auto_lookups(messages):
        done.append(lname)
        looked += f"{lname}:\n{look(lname, said)}\n"
    answer = ""
    for round_ in range(MAX_LOOKUPS + 1):
        answer = asker(conversation(task, messages, known, looked))
        wanted = [w for w in wanted_lookups(answer) if w[0] not in done]
        if not wanted or round_ == MAX_LOOKUPS:
            break
        for lname, arg in wanted[:2]:
            done.append(lname)
            looked += f"{lname} {arg}".rstrip() + f":\n{look(lname, arg)}\n"
    if wanted_lookups(answer) and not parse(answer)[0]:
        answer = "Sorry, I could not find that out. Write claude to ask Claude."
    return answer


# An ACTION runs only when his own message asked for that kind of thing and
# names every number the action names: a small model guessing is harmless.
ACTION_WORDS = {  # whole words only: "end" in "weekend" once allowed kill all
    "stop": r"\b(stop|kill|cancel|end|halt)\b",
    "retry": r"\b(retry|rerun|re-run|restart|try (it |that )?again)\b",
    "pause": r"\b(pause|hold off)\b",
    "resume": r"\b(resume|unpause|carry on|continue|start again)\b",
    "tell": r"\b(tell|pass (it |that )?on|let (it|them|the task|task \d+) know)\b",
    "work": "",  # wants_task(), below
    "progress": r".",
    "kill": r"\b(kill|end|close|quit)\b",
    "kill-task": r"\b(kill|stop|end|cancel)\b",
    "kill-all": r"\b(kill|stop|end) (it )?(all|everything)\b|\bkill switch\b",
    "top-cpu": r".",
    "top-gpu": r".",
    "stats": r".",
    "send-found": r"\b(send|share|give|forward)\b",
}


def action_allowed(kind: str, action: str, messages: list[str]) -> bool:
    said = " ".join(_said(m)[1] for m in messages).lower()
    if kind == "work":  # queues his own words (work_action): numbers may be older
        return wants_task(said)
    words = ACTION_WORDS.get(kind)
    if not words or not re.search(words, said):
        return False
    return all(n in re.findall(r"\d+", said) for n in re.findall(r"\d+", action))


def run_action(text: str, messages: list[str]) -> str:
    """One ACTION line from the model, if it is an allowed command that his
    message asked for (action_allowed)."""
    found = quick.match(text)
    if found:
        if found[0] not in ALLOWED_QUICK or not action_allowed(
            found[0], text, messages
        ):
            store.event("chat", f"local model action refused: {text[:80]}")
            return ""
        return quick.run(*found)
    cmd = commands.parse("", text, source="whatsapp")
    if cmd.kind not in ALLOWED_ACTIONS or not action_allowed(cmd.kind, text, messages):
        store.event("chat", f"local model action refused: {text[:80]}")
        return ""
    said, _made = actions.apply(cmd, "whatsapp")
    store.event("chat", f"local model ran: {text[:80]}")
    return said


# Emerson, 15:43-15:51: asked four times for a task; the model said "queued"
# each time and nothing was, once with the prompt's own placeholder as the
# job. So a message asking for a task queues one in his words whatever the
# model writes, and a reply claiming a deed nothing did gets corrected.
TASK_ASK = re.compile(
    r"\b(make|add|queue|que|create|put|write|start|open)\b.{0,40}\b(tasks?|taks|jobs?)\b"
    r"|\b(relay|new) (tasks?|taks)\b|\bqueue (it|that|this)\b"
    r"|\b(get|ask|have|tell) claude to\b",
    re.I,
)
# ...but not a question about tasks or a "don't": those queued tasks in the
# critic's run ("how do I add a task", "dont make a task for that").
NOT_ASK = re.compile(
    r"\b(don'?t|do not|never|no need|did you|have you|is the|are the|was the|were the"
    r"|how do i|how to|how can i|which|what tasks|make sure|write down|any tasks?)\b",
    re.I,
)
PLACEHOLDER = re.compile(r"[\[\]<>]|full work request|\bjob\b$", re.I)
# A reply claims a deed: first person ("I've queued it", "I'll shut it
# down", "on it") or a bare report ("Stopped task 61.", "Task 61 is
# stopped"). Checked per sentence and only when his message asked for a
# deed, so status answers ("No tasks are queued") are left alone.
DOING = re.compile(
    r"\b(i'?ll|i will|i'?m going to|let me|i can do that|will do|on it|queuing it)\b"
    r"|\bi(?:'?ve| have)?\s+(?:just\s+)?(queued|added|stopped|killed|paused|made|created"
    r"|started|sent|changed|done|shut|restarted|set)\b"
    r"|^\W*(sure,?\s+)?(done|stopped|paused|killed|queued|added|sent)\b"
    r"|\b(is|are|has been|have been|got) (now )?(stopped|paused|killed|queued|added|sent"
    r"|shut down|restarted)\b",
    re.I,
)
NEGATED = re.compile(r"\b(no|not|nothing|none|never|can'?t|cannot)\b|n't\b", re.I)
DEED_ASK = re.compile(
    r"\b(stop|kill|pause|resume|queue|que|add|make|create|start|restart|shut|turn|"
    r"send|change|set|edit|delete|fix|run|retry|cancel|reorder|switch)\b",
    re.I,
)


def wants_task(said: str) -> bool:
    return bool(TASK_ASK.search(said)) and not NOT_ASK.search(said)


def claims_a_deed(reply: str, asked: str) -> bool:
    if not DEED_ASK.search(asked):
        return False
    sentences = re.split(r"(?<=[.!?\n])\s*", reply)
    return any(DOING.search(s) and not NEGATED.search(s) for s in sentences)


TALK_ONLY = (
    "(That was talk only: I'm the small local model and nothing was done. "
    "new: <job> queues it for Claude, or write claude to switch back.)"
)


def his_words(task: dict, messages: list[str]) -> str:
    """His new message(s), with his message before them when they are short
    and point back at it (a bare "make a relay task for it" needs the message
    "it" was). Quick commands and Relay commands are never pulled in."""
    new = [_said(m)[1] for m in messages]
    said = " ".join(new)
    if len(said.split()) < 15 and re.search(
        r"\b(it|that|this|those|these|them)\b", said, re.I
    ):
        entries = chat._split(task.get("body", ""))[1]
        older = [
            _said(e)[1]
            for e in entries
            if not e.startswith(chat.NEW) and _said(e)[0] == "Emerson"
        ]
        older = [
            o
            for o in older
            if o not in new
            and not quick.match(o)
            and commands.parse("", o, source="whatsapp").kind
            in ("task", "work", "chat")
        ][-1:]
        new = older + new
    return " / ".join(n.strip() for n in new if n.strip())


def work_action(model_text: str, task: dict, messages: list[str]) -> str:
    """A new: command carrying his own words; the model's summary leads only
    when it is real text, not a placeholder."""
    summary = re.sub(r"^\s*(new|work)\s*:\s*", "", model_text, flags=re.I).strip()
    if PLACEHOLDER.search(summary) or len(summary.split()) < 4:
        summary = ""
    words = his_words(task, messages)
    body = summary or words
    if summary:
        body += f"\n\nEmerson's own words on WhatsApp: {words}"
    return f"new: {body}"


def apply(task: dict, result: dict) -> str:
    """Send the local model's answer (or say it failed) and run its actions."""
    messages = result["messages"]
    if "error" in result:
        chat.reply(
            "The local model is not answering right now ("
            + result["error"][:120]
            + "). Quick commands still work: command list."
        )
        outcome = f"local model failed ({result['error'][:200]})"
    else:
        reply, acts = parse(result["answer"])
        acts = [
            (
                work_action(a, task, messages)
                if re.match(r"(new|work)\s*:", a, re.I)
                else a
            )
            for a in acts[:2]
        ]
        asked = " ".join(_said(m)[1] for m in messages)
        if wants_task(asked) and not any(a.startswith("new:") for a in acts):
            acts.append(work_action("", task, messages))
        done = [s for s in (run_action(a, messages) for a in acts) if s]
        if reply and not done and claims_a_deed(reply, asked):
            reply += "\n" + TALK_ONLY
        if reply:
            chat.reply(reply, who="Local")
        for said in done:
            chat.reply(said)
        outcome = "local model answered" + (f", ran {len(done)}" if done else "")
    chat.mark_read(task, messages)
    task = items.find_task(task["id"]) or task
    if task.get("status") == chat.DESK and not chat.has_new(task):
        task["status"] = chat.IDLE
        items.save(task)
    return outcome


def fallback_text(readings_reset: str) -> str:
    """Said once when Claude runs out of usage and the local model takes over."""
    return (
        f"Claude is out of usage{readings_reset}, so the local model "
        f"({short_name(model())}) answers meanwhile, no usage. It is small: "
        "fine for status and quick questions. Work you send with new: waits for "
        "Claude. Write command list for the instant commands."
    )


BACK_TEXT = (
    "Claude has usage again, so the chat is back on Claude. Write local to "
    "keep the local model."
)


# ---- benchmark ------------------------------------------------------------------------


def bench(names: list[str], think: bool | None = False) -> int:
    """Score models on tests/localchat_samples.json: each sample is a message
    with fixed facts; a reply passes when it has one of `any`, none of
    `not`, and the lookup or action the sample wants (if any)."""
    data = store.read_json(SAMPLES) or {}
    samples = data.get("samples", [])
    known = data.get("facts", "")
    results = []
    for name in names or list(CANDIDATES.values()):
        right, took = 0, []
        for sample in samples:
            seen: list[str] = []

            def fake_lookup(lname, arg, _seen=seen):
                _seen.append(lname)
                return data.get("lookups", {}).get(lname, "(nothing)")

            started = time.time()
            try:
                answer = ask(
                    {"body": ""},
                    [f"Emerson: {sample['text']}"],
                    known,
                    name,
                    look=fake_lookup,
                    think=think,
                )
            except forge_jan.JanError as e:
                answer = f"(failed: {e})"
            took.append(time.time() - started)
            reply, acts = parse(answer)
            low = reply.lower()
            ok = not sample.get("any") or any(w.lower() in low for w in sample["any"])
            ok = ok and not any(w.lower() in low for w in sample.get("not", []))
            if sample.get("lookup"):
                ok = ok and sample["lookup"] in seen
            if "action" in sample:
                want = sample["action"]
                ok = ok and (
                    any(a.lower().startswith(want) for a in acts) if want else not acts
                )
            right += ok
            print(
                f"{'ok  ' if ok else 'MISS'} {took[-1]:5.1f}s {sample['text'][:50]!r}"
                f" -> {reply[:150]!r} lookups={seen} actions={acts}",
                flush=True,
            )
        avg = sum(took) / max(1, len(took))
        print(
            f"== {name}: {right}/{len(samples)} right, {avg:.1f}s average", flush=True
        )
        results.append(
            {"model": name, "right": right, "of": len(samples), "avg_s": round(avg, 1)}
        )
        forge_jan.release(name)
    print(json.dumps(results))
    return 0


if __name__ == "__main__":
    if "--bench" in sys.argv:
        picked = {"--think": True, "--auto": None}
        think = next((v for k, v in picked.items() if k in sys.argv), False)
        sys.exit(bench([a for a in sys.argv[1:] if not a.startswith("--")], think))
