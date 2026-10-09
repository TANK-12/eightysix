"""The WhatsApp chat's running record, and its tidy-up (Emerson, 2026-10-07).

Nothing is lost: every message the boss sees in the chat goes into a plain
text file, one per chat and day, in Relay's data folder
(`chatlog/Indeed-2026-10-07.txt`, one `[2026-10-07 19:25] Relay: ...` line
each), before anything in the chat is deleted. The boss records the visible
chat every `whatsapp_log_minutes` (10). `chatlog/<chat>.ids.json` lists every
message id already written, so nothing is written twice.

The tidy-up: when more than `whatsapp_tidy_keep` (30) messages sit below an
older stretch of at least `whatsapp_tidy_least` (15), at most once every
`whatsapp_tidy_minutes` (60), or when Emerson writes "tidy chat", that
stretch becomes ONE new summary message and the summarised messages are
deleted from the chat ("delete for me"). WhatsApp only lets you edit your
own message for about 15 minutes, so the summary is a new message, not an
edited old one. Only messages already in the log are deleted, never the last
30, never an earlier summary. `whatsapp_tidy_delete` false keeps the summary
and the log and deletes nothing.

The summary is written by the local Jan model (localchat's role, no usage).
When Jan is down or its summary fails the checks (empty, too long, a task
number that is not in the stretch), one short Claude call (Sonnet, low
effort) writes it instead. Score it on a saved stretch of the real chat with
`.venv/bin/python chatlog.py --try <stretch.json>`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import store
from channels import whatsapp

SUMMARY_HEAD = "Summary of "
SUMMARY = re.compile(whatsapp.OWN_PATTERN + re.escape(SUMMARY_HEAD))
DELETED = re.compile(r"^(This message was deleted|You deleted this message)\.?$")

SYSTEM = """\
You summarise one stretch of a WhatsApp chat between Emerson and Relay, the
assistant that runs Claude sessions on his laptop. Relay's messages start
with a running number and a sign ("83 ◆ ..."); Jan is the small local model
that sometimes answers for Relay. The stretch is about to be removed from the
chat, so your summary is what Emerson keeps on his phone.

Write it for him in plain words, at most 8 short lines, each starting "- ",
under 700 characters in all:
what he asked for, what Relay did or found, what was decided, and what is
still open or waiting on him. Keep task numbers, names, numbers and times
exactly as written. Merge repeats and small talk into nothing. Never invent
anything that is not in the stretch. No headings, no code, no tables."""


# ---- the running log ----------------------------------------------------------------


def folder() -> Path:
    return store.path("chatlog")


def _safe(chat: str) -> str:
    return re.sub(r"[^\w.-]+", "_", chat).strip("_") or "chat"


def ids_file(chat: str) -> Path:
    return folder() / f"{_safe(chat)}.ids.json"


def log_file(chat: str, at: float) -> Path:
    return (
        folder() / f"{_safe(chat)}-{time.strftime('%Y-%m-%d', time.localtime(at))}.txt"
    )


def logged(chat: str) -> set[str]:
    return set(store.read_json(ids_file(chat), []) or [])


def who(msg: dict) -> str:
    text = msg.get("text") or ""
    if whatsapp.is_own(text):
        return "Relay"
    if msg.get("me"):
        return "Emerson"
    return whatsapp.stamp_of(msg.get("pre") or "")[1] or "Them"


def line(msg: dict, at: float) -> str:
    text = (msg.get("text") or "").replace("\n", "\n    ")
    return (
        f"[{time.strftime('%Y-%m-%d %H:%M', time.localtime(at))}] {who(msg)}: {text}\n"
    )


def record(chat: str, found: list[dict], now: float | None = None) -> int:
    """Append every message with text that is not in the log yet, in page
    order; how many were added. A row with no text (a picture, or one the
    page has not drawn) waits until it has text, and is never deleted."""
    now = now or time.time()
    done = logged(chat)
    added: list[str] = []
    for msg in found:
        mid, text = msg.get("id"), msg.get("text")
        if not mid or not text or mid in done or DELETED.match(text):
            continue
        at = whatsapp.stamp_of(msg.get("pre") or "")[0] or now
        file = log_file(chat, at)
        file.parent.mkdir(parents=True, exist_ok=True)
        if not file.exists():
            file.write_text(
                f"# WhatsApp chat {chat!r}, kept by Relay\n", encoding="utf-8"
            )
        with open(file, "a", encoding="utf-8") as fh:
            fh.write(line(msg, at))
        done.add(mid)
        added.append(mid)
    if added:
        old = store.read_json(ids_file(chat), []) or []
        store.write_json(ids_file(chat), old + added)
    return len(added)


# ---- picking the stretch ------------------------------------------------------------


def is_summary(text: str) -> bool:
    return bool(SUMMARY.match(text or ""))


def stretch(
    found: list[dict],
    done: set[str],
    keep: int = 30,
    least: int = 15,
    summarised: set[str] | None = None,
) -> list[dict]:
    """The old messages to fold into one summary: logged text rows above the
    last `keep` rows AND above Emerson's own last `keep` messages, earlier
    summaries, rows already summarised and rows with a picture, video, voice
    note or file left alone; [] when fewer than `least` (not worth a summary
    yet)."""
    rows = [m for m in found if m.get("id")]
    his = [i for i, m in enumerate(rows) if who(m) == "Emerson"]
    cut = len(rows) - keep
    if his:
        cut = min(cut, his[-keep] if len(his) >= keep else his[0])
    if cut <= 0:
        return []
    picked = [
        m
        for m in rows[:cut]
        if m["id"] in done
        and m["id"] not in (summarised or set())
        and m.get("text")
        and not m.get("media")
        and not is_summary(m["text"])
        and not DELETED.match(m["text"])
    ]
    return picked if len(picked) >= least else []


def summarised_file(chat: str) -> Path:
    return folder() / f"{_safe(chat)}.summarised.json"


def summarised(chat: str) -> set[str]:
    """Ids already folded into a posted summary (never summarised twice,
    even while their deletes are still going out)."""
    return set(store.read_json(summarised_file(chat), []) or [])


def mark_summarised(chat: str, ids: list[str]) -> None:
    known = list(store.read_json(summarised_file(chat), []) or [])
    seen = set(known)
    store.write_json(
        summarised_file(chat), (known + [i for i in ids if i not in seen])[-5000:]
    )


def transcript(msgs: list[dict], now: float | None = None) -> str:
    out = []
    for m in msgs:
        at = whatsapp.stamp_of(m.get("pre") or "")[0] or now or time.time()
        text = " ".join((m.get("text") or "").split())
        if len(text) > 700:
            text = text[:700] + " [cut]"
        out.append(f"[{time.strftime('%H:%M', time.localtime(at))}] {who(m)}: {text}")
    return "\n".join(out)


def heading(msgs: list[dict]) -> str:
    stamps = [whatsapp.stamp_of(m.get("pre") or "")[0] for m in msgs]
    known = [s for s in stamps if s]
    span = ""
    if known:
        first, last = time.localtime(min(known)), time.localtime(max(known))
        day = "%a %H:%M"
        end = "%H:%M" if first[:3] == last[:3] else day
        span = f"{time.strftime(day, first)}-{time.strftime(end, last)}, "
    return (
        f"{SUMMARY_HEAD}{span}{len(msgs)} messages "
        "(the full text is in Relay's chat log):"
    )


# ---- writing the summary -------------------------------------------------------------

# The summary and its heading must fit one WhatsApp part (whatsapp_part_chars,
# 900): a second part would not start with "Summary of" and be summarised again.
MOST_CHARS = 780
THINK = re.compile(r"<think>.*?(</think>|$)", re.S)
TASK_NUMBER = re.compile(r"(?:\btask\s*#?|#)(\d+)", re.I)


def clean(answer: str) -> str:
    text = THINK.sub("", answer or "").strip()
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def fit(summary: str) -> str:
    """A summary over MOST_CHARS keeps its first whole lines that fit: the
    2B often writes nine or ten good lines where eight were asked for (real
    chat, 2026-10-07), and a cut list beats a Claude call."""
    if len(summary) <= MOST_CHARS:
        return summary
    kept: list[str] = []
    for ln in summary.splitlines():
        if len("\n".join(kept + [ln])) > MOST_CHARS:
            break
        kept.append(ln)
    return "\n".join(kept) if len(kept) >= 3 else summary


def check(summary: str, msgs: list[dict]) -> str:
    """Why this summary is not good enough; "" when it is."""
    if len(summary) < 40:
        return "too short"
    if len(summary) > MOST_CHARS:
        return "too long"
    said = " ".join(m.get("text") or "" for m in msgs)
    known = set(re.findall(r"\d+", said))
    made_up = [n for n in TASK_NUMBER.findall(summary) if n not in known]
    if made_up:
        return f"names task {made_up[0]}, which is not in the stretch"
    return ""


def ask_jan(text: str) -> str:
    import localchat  # puts Forge's shared folder on the path

    import forge_jan

    forge_jan.ensure_router()
    name = localchat.model()
    with localchat.JAN.using(name):
        return forge_jan.chat(
            name,
            SYSTEM,
            f"The stretch:\n\n{text}\n\nThe summary:",
            temperature=0.2,
            max_tokens=450,
            timeout=400,
            extra={"top_p": 0.9, "top_k": 20},
        )


def ask_claude(text: str, settings: dict) -> str:
    import meters
    import picker

    account, why = picker.pick_account(meters.read(), {}, time.time(), settings)
    if not account:
        raise RuntimeError(f"no account for the Claude summary ({why})")
    from claude_launch import find_claude  # the boss's PATH has no ~/.local/bin

    claude = find_claude("RELAY_CLAUDE_BIN")
    if not claude:
        raise RuntimeError("claude not found")
    done = subprocess.run(
        [
            claude,
            "-p",
            f"{SYSTEM}\n\nThe stretch:\n\n{text}\n\nReply with the summary only.",
            "--model",
            "sonnet",
            "--effort",
            "low",
            "--max-turns",
            "1",
            "--no-session-persistence",
            "--tools",
            "",
        ],
        cwd="/tmp",
        env=meters.env_for(account),
        capture_output=True,
        text=True,
        timeout=240,
    )
    if done.returncode:
        raise RuntimeError(
            f"claude summary failed: {(done.stderr or done.stdout)[-200:]}"
        )
    return done.stdout


def summarise(
    msgs: list[dict], settings: dict, local=ask_jan, remote=ask_claude
) -> dict:
    """{"text", "by", "ids"} or {"error"}: Jan first, Claude when Jan's
    summary is missing or fails check()."""
    text = transcript(msgs)
    notes = []
    for by, ask in (
        ("jan", lambda: local(text)),
        ("claude", lambda: remote(text, settings)),
    ):
        try:
            summary = fit(clean(ask()))
        except Exception as e:  # Jan down, no account, timeout: try the next
            notes.append(f"{by}: {str(e)[:160]}")
            continue
        bad = check(summary, msgs)
        if bad:
            notes.append(f"{by}: {bad}")
            continue
        return {
            "text": f"{heading(msgs)}\n{summary}",
            "by": by,
            "ids": [m["id"] for m in msgs],
            "notes": notes,
        }
    return {"error": "; ".join(notes) or "no summary"}


# ---- asking for one, and the worker the boss runs ---------------------------------


def _request_file() -> Path:
    return folder() / "tidy-request"


def request() -> str:
    """Emerson's "tidy chat": the boss tidies at its next chat-log look."""
    _request_file().parent.mkdir(parents=True, exist_ok=True)
    _request_file().write_text(str(time.time()))
    return (
        "Tidying the chat within a minute: the older messages become one "
        "summary, the full text stays in Relay's chat log."
    )


def requested() -> bool:
    return _request_file().exists()


def clear_request() -> None:
    _request_file().unlink(missing_ok=True)


class Tidy:
    """One summary at a time, in a thread (Jan can take minutes); the boss
    picks up the result with step()."""

    def __init__(self, summariser=summarise) -> None:
        self.summariser = summariser
        self.thread: threading.Thread | None = None
        self.result: dict | None = None

    def busy(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def start(self, msgs: list[dict], settings: dict) -> None:
        def work():
            try:
                self.result = self.summariser(msgs, settings)
            except Exception as e:  # never let the thread die silently
                self.result = {"error": str(e)[:300]}

        self.result = None
        self.thread = threading.Thread(target=work, daemon=True, name="relay-tidy")
        self.thread.start()

    def step(self) -> dict | None:
        if self.busy() or self.result is None:
            return None
        done, self.result = self.result, None
        return done


def main(argv: list[str]) -> int:
    """`chatlog.py --try stretch.json`: summarise a saved stretch (a list of
    the page's message dicts) with Jan and print it with the checks."""
    if len(argv) != 2 or argv[0] != "--try":
        print(__doc__)
        return 2
    msgs = json.loads(Path(argv[1]).read_text())
    started = time.time()
    out = summarise(msgs, store.settings(), remote=lambda *_: "")
    print(f"{time.time() - started:.0f} s, {len(msgs)} messages")
    print(out.get("text") or out.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
