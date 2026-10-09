"""WhatsApp chat mode: one standing conversation plus at most one work task.

Emerson's WhatsApp messages that are not commands all go to one chat task
(setting `whatsapp_chat_task`, made on first use). It is light on purpose
(Haiku 5.5 at low effort by default, `whatsapp_chat_model`): it
chats, answers questions about Relay, and turns plain requests into Relay
commands. Real work goes to one work task at a time (`whatsapp_work_task`,
opus): `new: <text>` from Emerson, or `relay 'new: ...'` from the chat
session. While that task is open, more work is told to it or added to its
request instead of making new tasks.

The chat task's file keeps the conversation under `## Messages`. A message
that has not been read yet starts with `[new]`; the boss puts new messages
into the session's prompt, and a running session takes later ones with
`relay inbox`. When its session ends the task goes `idle` (not done) and the
next message queues it again, resuming the same Claude session while its
context is small so it remembers the talk.

Sessions answer straight away with `relay reply <text>` (and `relay
send-file`, `relay unsend`): those write to an outbox folder and the boss,
the only thing that touches the Whatsie page, sends them on its fast poll.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHARED = Path(os.environ.get("FORGE_SHARED_DIR") or ROOT.parent.parent / "shared")
if SHARED.is_dir() and str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

import forge_attach  # noqa: E402  (shared: files sent with a message)

import items
import store

IDLE = "idle"
DESK = "desk"  # the Jan front desk has the new messages (frontdesk.py)
OPEN = ("queued", "running", "handing_over", "reviewing", "blocked")
KEEP_MESSAGES = 40
NEW = "[new] "
MESSAGES = "## Messages"

CHAT_REQUEST = """\
The standing WhatsApp chat with Emerson. Every message he sends to Relay on
WhatsApp that is not a command lands under Messages below. Answer each one
with `relay reply`, short and plain, and turn plain requests into Relay
actions. Real work goes to the work task (`relay 'new: ...'`).

Open from before: Emerson asked whether the boss uses usage or is a Python
thing. Answer it in your first reply: the boss is plain Python and spends no
usage while it watches; only Claude sessions (like this chat) use usage. He
also said the text was cut off with three dots; that is fixed (titles are no
longer cut, long messages are split).
"""


# ---- the chat task -------------------------------------------------------------


def chat_task(create: bool = True) -> dict | None:
    """The standing chat task, made on first use."""
    number = store.settings().get("whatsapp_chat_task") or 0
    task = items.find_task(number) if number else None
    if task or not create:
        return task
    task = items.new_task(
        "WhatsApp chat",
        CHAT_REQUEST,
        source="whatsapp",
        role="chat",
        done_when="Never done: it goes idle between messages.",
    )
    task["status"] = IDLE
    task["body"] = task["body"].replace("## State", f"{MESSAGES}\n\n## State")
    items.save(task)
    store.save_settings({"whatsapp_chat_task": task["id"]})
    store.event("chat", f"chat task {task['id']} made")
    return task


def is_chat(task: dict | None) -> bool:
    return bool(task) and (task or {}).get("role") == "chat"


def _split(body: str) -> tuple[str, list[str], str]:
    """(before Messages, message entries, from State on)."""
    head, sep, rest = body.partition(MESSAGES)
    if not sep:
        head, sep2, tail = body.partition("## State")
        return head, [], sep2 + tail
    text, sep2, tail = rest.partition("## State")
    entries: list[str] = []
    for line in text.strip("\n").splitlines():
        if line.startswith("- "):
            entries.append(line[2:])
        elif entries and line.strip():
            entries[-1] += "\n" + line.strip()
    return head, entries, sep2 + tail


def _join(head: str, entries: list[str], tail: str) -> str:
    lines = []
    for entry in entries[-KEEP_MESSAGES:]:
        first, *more = entry.split("\n")
        lines.append(f"- {first}")
        lines += [f"  {m}" for m in more]
    return (
        head.rstrip("\n")
        + f"\n\n{MESSAGES}\n\n"
        + "\n".join(lines)
        + ("\n\n" if lines else "")
        + tail.lstrip("\n")
    )


def _stamp() -> str:
    return time.strftime("%a %H:%M")


def _add_entry(task: dict, entry: str) -> None:
    head, entries, tail = _split(task.get("body", ""))
    task["body"] = _join(head, entries + [entry], tail)
    items.save(task)


def add_message(task: dict, text: str) -> None:
    _add_entry(task, f"{NEW}{_stamp()} Emerson: {text.strip()}")


def log_reply(text: str, who: str = "Relay") -> None:
    task = chat_task(create=False)
    if task:
        _add_entry(task, f"{_stamp()} {who}: {text.strip()}")


def message_text(entry: str) -> str:
    """A Messages entry without its stamp and name: "Thu 11:34 Emerson: hi"
    -> "hi"."""
    return re.sub(r"^\w{3} \d{1,2}:\d{2} [^:\n]{1,20}: ", "", entry, count=1)


def has_new(task: dict) -> bool:
    return any(e.startswith(NEW) for e in _split(task.get("body", ""))[1])


def new_messages(task: dict) -> list[str]:
    """The unread messages, without marking them read."""
    entries = _split(task.get("body", ""))[1]
    return [e[len(NEW) :] for e in entries if e.startswith(NEW)]


def mark_unread(task: dict, messages: list[str]) -> None:
    """A chat session that failed never answered these: back to new."""
    task = items.find_task(task["id"]) or task
    head, entries, tail = _split(task.get("body", ""))
    wanted = set(messages)
    entries = [NEW + e if e in wanted else e for e in entries]
    task["body"] = _join(head, entries, tail)
    items.save(task)


def mark_read(task: dict, messages: list[str]) -> None:
    """These messages are answered (by the front desk): drop their mark."""
    task = items.find_task(task["id"]) or task
    head, entries, tail = _split(task.get("body", ""))
    done = {NEW + m for m in messages}
    entries = [e[len(NEW) :] if e in done else e for e in entries]
    task["body"] = _join(head, entries, tail)
    items.save(task)


def take_new(task: dict) -> list[str]:
    """The unread messages (without the mark); marks them read."""
    task = items.find_task(task["id"]) or task
    head, entries, tail = _split(task.get("body", ""))
    new = [e[len(NEW) :] for e in entries if e.startswith(NEW)]
    if new:
        task["body"] = _join(
            head, [e[len(NEW) :] if e.startswith(NEW) else e for e in entries], tail
        )
        items.save(task)
    return new


def inbox() -> str:
    """`relay inbox`: messages that came in while the chat session worked."""
    task = chat_task(create=False)
    new = take_new(task) if task else []
    if not new:
        return "No new messages."
    return "New from Emerson:\n" + "\n".join(f"- {m}" for m in new)


def route(text: str) -> tuple[dict, bool]:
    """A plain WhatsApp message goes to the chat: (chat task, whether its
    session is running and only needs telling). Not running: to the Jan
    front desk (frontdesk.py) when it is on, to the local chat
    (localchat.py) when it is picked or Claude is out of usage, else queued
    for Claude. A Claude
    hand-off still waiting for usage goes back to the desk, so the chat never
    goes silent."""
    task = chat_task()
    assert task is not None
    add_message(task, text)
    task = items.find_task(task["id"]) or task
    status = task.get("status")
    if status in items.ACTIVE:
        return task, True
    settings = store.settings()
    desk = settings.get("whatsapp_frontdesk") == "jan"
    chat_wait = store.state().get("chat_wait")
    waiting = status == "queued" and chat_wait
    # The local chat (localchat.py): picked, or standing in while Claude
    # has no usage. It answers through the desk too.
    local = settings.get("whatsapp_frontdesk") == "local" or (
        chat_wait and settings.get("whatsapp_fallback", "auto") == "auto"
    )
    # A message with files goes to Claude: the local models read text only.
    # While Claude has no usage the local chat still answers, and the files
    # wait in the chat's Messages for Claude.
    if forge_attach.has_files(text) and not chat_wait:
        local = desk = False
    if local or (desk and (status != "queued" or waiting)):
        status = DESK
    elif status != DESK:
        status = "queued"
    task.update(status=status, note="")
    items.save(task)
    store.poke()
    return task, False


# The light chat model: the default and where every step down lands. Haiku
# 4.5 was never used for the chat (Emerson, 2026-10-07); Haiku 5.5 is, after a
# reply-quality probe on the real chat prompt (Relay task 99, 2026-10-08).
# "haiku" launches as store.MODEL_IDS["haiku"], never Claude Code's alias.
LIGHT = ("haiku", "low")
STEP_DOWN = ("light", "down", "default")
MODELS = ("haiku", "sonnet", "opus")


def chat_model(settings: dict) -> tuple[str, str]:
    """The (model, effort) the next chat session runs on. A step down, or
    no model saved, comes out as the light model; haiku with no effort at
    the light model's own."""
    model = str(settings.get("whatsapp_chat_model") or "").strip().lower()
    effort = str(settings.get("whatsapp_chat_effort") or "")
    if not model or model in STEP_DOWN:
        return LIGHT
    if model == LIGHT[0]:
        return model, effort or LIGHT[1]
    return model, effort


def set_model(model: str, effort: str = "") -> str:
    """`relay chat-model opus high`: the chat steps up (or back down). The
    next chat session starts fresh on that model from State and Messages.
    `haiku` (or `light`, `down`, `default`) steps down to Haiku 5.5 low."""
    model = model.strip().lower()
    effort = effort.strip().lower()
    if model in STEP_DOWN or (model == LIGHT[0] and not effort):
        model, effort = LIGHT
    if model not in MODELS:
        return "Model must be haiku, sonnet or opus."
    if effort and effort not in ("low", "medium", "high", "xhigh", "max"):
        return "Effort must be low, medium, high, xhigh or max."
    store.save_settings({"whatsapp_chat_model": model, "whatsapp_chat_effort": effort})
    task = chat_task(create=False)
    if task:
        task["resume_ok"] = ""  # a new model starts a fresh session from State
        items.save(task)
    store.event("chat", f"chat model set to {model} {effort}".strip())
    return (
        f"The chat now runs on {model}" + (f" at {effort}" if effort else "") + ". "
        "Finish your reply and end; the next message goes to the new model."
    )


# ---- the work slot -----------------------------------------------------------------


def open_work() -> dict | None:
    number = store.settings().get("whatsapp_work_task") or 0
    task = items.find_task(number) if number else None
    return task if task and task.get("status") in OPEN else None


def add_to_task(task: dict, text: str, queue: bool = True) -> None:
    """More work for a task that is not running: into its request, queued.
    queue=False only writes it there (a task being reviewed). The file is
    read again first: the boss may have changed it since the caller read it.
    His answer to a blocked task counts as a review (review_due)."""
    task.update(items.find_task(task["id"]) or {})
    added = f"\n\nAdded later by Emerson ({_stamp()}): {text.strip()}\n"
    body = task.get("body", "")
    head, sep, tail = body.partition("## Done when")
    task["body"] = (
        (head.rstrip("\n") + added + "\n" + sep + tail) if sep else body + added
    )
    if queue:
        if task.get("status") == "blocked":
            task.update(fails=0, note="", reviewed_at=int(items.num(task, "attempts")))
        task["status"] = "queued"
    items.save(task)
    if queue:
        store.poke()


# ---- the outbox ------------------------------------------------------------------


def outbox_dir() -> Path:
    return store.path("outbox")


def files_dir() -> Path:
    """Where files to send are copied: a folder the Whatsie flatpak can read."""
    return Path(store.settings()["whatsapp_files_dir"]).expanduser()


def queue_out(kind: str, **fields) -> Path:
    folder = outbox_dir()
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{time.time():.6f}-{kind}.json"
    file = folder / name
    store.write_json(file, {"kind": kind, **fields})
    return file


def reply(text: str, who: str = "Relay") -> str:
    text = text.strip()
    if not text:
        return "Nothing to send."
    if not store.settings().get("whatsapp_enabled"):
        # still logged: Mission Control's WhatsApp view reads the log
        log_reply(text, who)
        return "WhatsApp is off in Relay's settings; logged in the chat, nothing sent."
    queue_out("text", text=text)
    store.write_text(outbox_dir() / "last_reply", str(time.time()))
    log_reply(text, who)
    return "Queued; it goes to WhatsApp within a few seconds."


def send_files(paths: list[str], caption: str = "") -> str:
    """Queue files as one lot: WhatsApp groups them in one tray."""
    sources = [Path(p).expanduser() for p in paths]
    for source, given in zip(sources, paths):
        if not source.is_file():
            return f"No file at {given}."
    if not sources:
        return "No file given."
    if not store.settings().get("whatsapp_enabled"):
        return "WhatsApp is off in Relay's settings; nothing sent."
    folder = files_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    copies = []
    for n, source in enumerate(sources):
        tag = f"{stamp}-{n}-" if n else f"{stamp}-"
        copy = folder / f"{tag}{source.name}"
        shutil.copy2(source, copy)
        copies.append(str(copy))
    queue_out(
        "file",
        path=copies[0],
        paths=copies,
        names=[s.name for s in sources],
        caption=caption.strip(),
    )
    names = ", ".join(s.name for s in sources)
    log_reply(f"(sent {names}) {caption}".strip())
    return f"Queued {names}; it goes to WhatsApp within a few seconds."


def send_file(path: str, caption: str = "") -> str:
    return send_files([path], caption)


def unsend(count: int = 1) -> str:
    count = max(1, min(int(count), 10))
    queue_out("delete", count=count)
    return f"Queued: delete Relay's last {count} message(s) for everyone."


def remember_sent(message_id: str) -> None:
    """Note a file message Relay sent: files carry no 🔨 mark, and Emerson's
    own photos look the same, so unsend only deletes ids listed here."""
    if not message_id:
        return
    ids = [i for i in sent_files() if i != message_id]
    store.write_json(
        store.path("whatsapp_sent_files.json"), (ids + [message_id])[-200:]
    )


def sent_files() -> list[str]:
    # Not in outbox_dir(): every .json there is a message waiting to go.
    return list(store.read_json(store.path("whatsapp_sent_files.json")) or [])


def last_reply_at() -> float:
    try:
        return float((outbox_dir() / "last_reply").read_text())
    except (OSError, ValueError):
        return 0.0


def pending() -> list[Path]:
    folder = outbox_dir()
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.json"))


def flush(sender, limit_tries: int = 5) -> int:
    """Send what sessions queued, oldest first, through `sender(entry)`.
    A failed entry stays and is tried again after 20 s times its tries; after
    `limit_tries` it moves to outbox/failed so it cannot block the rest."""
    sent = 0
    for file in pending():
        entry = store.read_json(file)
        if not isinstance(entry, dict):
            file.rename(file.with_suffix(".bad"))
            continue
        if float(entry.get("next_at") or 0) > time.time():
            break  # the last try failed just now; wait before the next
        try:
            sender(entry)
        except Exception as e:
            entry["tries"] = int(entry.get("tries") or 0) + 1
            entry["error"] = str(e)[:300]
            entry["next_at"] = time.time() + 20 * entry["tries"]
            if entry["tries"] >= limit_tries:
                failed = outbox_dir() / "failed"
                failed.mkdir(exist_ok=True)
                store.write_json(failed / file.name, entry)
                file.unlink()
                store.event("mail-error", f"whatsapp outbox gave up: {e}")
            else:
                store.write_json(file, entry)
            break  # keep the order: try again on the next poll
        file.unlink()
        sent += 1
        if entry.get("kind") == "delete_ids":
            break  # one tidy-up chunk per flush: the boss reads the chat between
    return sent


# ---- phone-friendly text -------------------------------------------------------------

FENCE = re.compile(r"```.*?(```|$)", re.S)
SHELL_LINE = re.compile(
    r"^\s*(\$ |# |sudo |cd |systemctl |\.venv/|python3? |pip |git )"
)
INLINE = re.compile(r"`([^`\n]*)`")


def phone(text: str) -> str:
    """No shell commands or code on the phone: code blocks and command lines
    go, inline code keeps its words when short."""
    text = FENCE.sub("(code left out)", text or "")
    text = "\n".join(ln for ln in text.splitlines() if not SHELL_LINE.match(ln))

    def inline(m: re.Match) -> str:
        inner = m.group(1).strip()
        looks_like_command = len(inner) > 30 or re.search(r"\s-{1,2}\w|[|;&>]", inner)
        return "" if looks_like_command else inner

    text = INLINE.sub(inline, text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def chunks(text: str, size: int) -> list[str]:
    """Split at paragraph, then line, then word boundaries; never mid-word."""
    out: list[str] = []
    rest = text.strip()
    while len(rest) > size:
        cut = -1
        for mark in ("\n\n", "\n", ". ", " "):
            cut = rest.rfind(mark, size // 3, size)
            if cut > 0:
                cut += len(mark.rstrip(" ")) if mark == ". " else 0
                break
        if cut <= 0:
            cut = size
        out.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        out.append(rest)
    return out
