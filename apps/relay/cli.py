"""Relay from the terminal: the same commands as mail.

    relay status
    relay pause | resume | digest | help
    relay --help                  this text
    relay stop 12 | retry 12
    relay "fix the cosmos orbit bug, tests must pass"
    relay 'goal: Emberfield boots to the title screen
    check: cd ~/Forge/apps/emberfield && .venv/bin/python -m pytest -q'
    relay < long-request.txt       (a long request from a file or a heredoc)

Unlike mail, the terminal may set a goal's `check:` command.

Session-only commands (never read from mail or WhatsApp), for talking to
Emerson on WhatsApp through the boss's outbox:

    relay reply <text>            a message to Emerson, sent within seconds
    relay send-file <path>... [caption]   files or pictures, sent as one lot
                                  (leading words that are files; the rest is the caption)
    relay unsend [n]              delete Relay's last n messages for everyone
    relay inbox                   chat messages that came in while you worked
    relay chat-model <haiku|sonnet|opus> [effort]   step the chat up or down
    relay chat-mode [claude|desk|local|boss]   who answers the chat (local: the
                                     small Jan model, no usage; boss: the boss line)
    relay as-whatsapp <text>      a line typed in Mission Control's WhatsApp mirror,
                                  handled as if sent on WhatsApp (text or stdin)

    relay boss <question>         ask Relay's boss here (one lean Claude turn;
                                  the answer prints here, not on WhatsApp)
    relay finishing               a work session close to done: Relay does not
                                  hand it over for its context size for a while
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHARED = Path(os.environ.get("FORGE_SHARED_DIR") or ROOT.parent.parent / "shared")
for extra in (str(ROOT), str(SHARED)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

import actions  # noqa: E402
import chat  # noqa: E402
import commands  # noqa: E402
import localchat  # noqa: E402
import items  # noqa: E402
import store  # noqa: E402


def _file(rest: list[str]) -> str:
    if not rest:
        return "Which file? relay send-file <path>... [caption]"
    # The first word is always a path; so is every following word that names
    # a file. The words after the last file are the caption.
    paths = [rest[0]]
    for word in rest[1:]:
        if not Path(word).expanduser().is_file():
            break
        paths.append(word)
    return chat.send_files(paths, " ".join(rest[len(paths) :]))


def _unsend(rest: list[str]) -> str:
    return chat.unsend(int(rest[0]) if rest and rest[0].isdigit() else 1)


def _model(rest: list[str]) -> str:
    if not rest:
        return "Which model? relay chat-model haiku|sonnet|opus [effort]"
    return chat.set_model(rest[0], rest[1] if len(rest) > 1 else "")


def _boss(rest: list[str]) -> str:
    import bossline

    text = " ".join(rest).strip()
    return (
        bossline.ask_now(text)
        if text
        else "Ask the boss something: relay boss <question>"
    )


def _entries(task: dict | None) -> list[str]:
    """The chat's Messages entries, without the unread mark."""
    entries = chat._split((task or {}).get("body", ""))[1]
    return [e.removeprefix(chat.NEW) for e in entries]


def _added(before: list[str], after: list[str]) -> list[str]:
    """The entries `after` has that `before` did not. The log only grows at
    its end and drops its oldest lines (it keeps the last KEEP_MESSAGES), so
    `after` starts with a tail of `before`; a line with the same words as one
    that dropped out still counts as new."""
    for drop in range(len(before)):
        kept = before[drop:]
        if after[: len(kept)] == kept:
            return after[len(kept) :]
    left = Counter(before)  # an empty or rewritten log: count instead
    added = []
    for entry in after:
        if left[entry]:
            left[entry] -= 1
        else:
            added.append(entry)
    return added


def _as_whatsapp(rest: list[str]) -> str:
    """Mission Control's WhatsApp mirror (task 109): a line Emerson typed
    there, handled as the boss handles one from WhatsApp. It lands in the
    chat's Messages (the mirror reads them) and, marked, on WhatsApp, so the
    phone thread stays whole; a command's answer goes to both."""
    text = " ".join(rest).strip()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    if not text:
        return "Nothing to send."
    on = bool(store.settings().get("whatsapp_enabled"))
    before = _entries(chat.chat_task())
    if on:
        chat.queue_out("text", text=f"From Mission Control: {text}")
    slugs = tuple(g["slug"] for g in items.all_goals())
    cmd = commands.parse("", text, slugs, source="whatsapp")
    reply, _ = actions.apply(cmd, "whatsapp")
    added = _added(before, _entries(chat.chat_task()))
    if not any(" Emerson: " in e.split("\n")[0] for e in added):
        chat.log_reply(text, "Emerson")  # a command: the chat did not log it
    if not reply:
        return "Sent: the answer comes in the chat."
    chat.reply(reply)  # logged in the chat too, WhatsApp on or off
    return reply


SESSION = {
    "reply": lambda rest: chat.reply(
        " ".join(rest) or ("" if sys.stdin.isatty() else sys.stdin.read())
    ),
    "send-file": _file,
    "unsend": _unsend,
    "inbox": lambda rest: chat.inbox(),
    "chat-model": _model,
    "boss": lambda rest: _boss(rest),
    "finishing": lambda rest: actions.finishing(os.environ.get("RELAY_RUN_ID", "")),
    "chat-mode": lambda rest: (
        localchat.set_mode(rest[0] if rest else "") if rest else localchat.describe()
    ),
    "as-whatsapp": _as_whatsapp,
}


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    store.ensure()
    if argv and argv[0] in SESSION:
        print(SESSION[argv[0]](argv[1:]))
        return 0
    text = " ".join(argv).strip()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    if not text:
        text = "status"
    slugs = tuple(g["slug"] for g in items.all_goals())
    cmd = commands.parse("", text, slugs, source="cli")
    if cmd.kind == "task" and os.environ.get("RELAY_RUN_KIND") == "chat":
        # a side-by-side job from the WhatsApp chat: its own task, not the
        # work task, and its result goes back to WhatsApp (task 105)
        task = actions.add_task(cmd, "whatsapp")
        print(f"Task {task['id']} queued beside the work task: {task['title']}.")
        return 0
    reply, _ = actions.apply(cmd, "the terminal")
    print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
