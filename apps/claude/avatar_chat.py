"""Chat with the avatar directly: a short reply from the persona, made by this
app's own Jan model, with no Claude Code turn (which would cost tokens).

Emerson asked for the avatars to be "interactive and chattable" on
2026-09-24 (~/Forge/apps/claude/docs/PLAN-avatars-2.md). Each reply is 1 to 3 sentences in the
persona's voice and ends with one reaction tag; the stage plays the tag and
speaks the reply. The last 30 exchanges per persona are kept in
<data>/avatar_chat/<persona id>.json.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

TAGS = ("happy", "think", "shy", "sad", "surprised", "wink")
KEEP_EXCHANGES = 30
MAX_TEXT = 600

TAG_RE = re.compile(r"[\[(<*]*\s*(" + "|".join(TAGS) + r")\s*[\])>*]*[.!\s]*$", re.I)
ID_RE = re.compile(r"^[a-z0-9_\-]{1,48}$")


def system_prompt(persona: dict) -> str:
    return (
        f"You are {persona.get('name', 'the avatar')}, a character on Emerson's "
        f"desktop. {persona.get('prompt', '')}\n"
        "Chat casually with Emerson. Reply in 1 to 3 short sentences, in "
        "character, with no lists and no markdown. No explicit sexual content. "
        "End the reply with exactly one tag in square brackets from this list: "
        + ", ".join(f"[{t}]" for t in TAGS)
        + "."
    )


def parse_reply(text: str) -> tuple[str, str]:
    """(reply without its tag, tag). The tag defaults to "happy" when the
    model forgot it; a <think> block some models leak is dropped."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    tag = "happy"
    match = TAG_RE.search(text)
    if match:
        tag = match.group(1).lower()
        text = text[: match.start()].rstrip()
    # Any other bracketed tag left in the middle of the reply.
    text = re.sub(r"\s*\[(?:" + "|".join(TAGS) + r")\]", "", text, flags=re.I)
    return text.strip(), tag


def trim(history: list[dict], keep: int = KEEP_EXCHANGES) -> list[dict]:
    """The last `keep` exchanges (two messages each)."""
    return history[-2 * keep :] if keep > 0 else []


class History:
    """Per-persona chat history on disk."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def path(self, persona_id: str) -> Path:
        if not ID_RE.match(persona_id or ""):
            raise ValueError("No such persona")
        return self.folder / f"{persona_id}.json"

    def load(self, persona_id: str) -> list[dict]:
        path = self.path(persona_id)
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return []
        return [
            m
            for m in data
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        ]

    def add(self, persona_id: str, user: str, reply: str, tag: str) -> list[dict]:
        now = time.time()
        history = self.load(persona_id) + [
            {"role": "user", "content": user, "t": now},
            {"role": "assistant", "content": reply, "tag": tag, "t": now},
        ]
        history = trim(history)
        path = self.path(persona_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(history, indent=1, ensure_ascii=False))
        return history

    def clear(self, persona_id: str) -> None:
        self.path(persona_id).unlink(missing_ok=True)


def messages(persona: dict, history: list[dict], text: str) -> list[dict]:
    """The chat request: persona system prompt, recent history, the new line.
    Old assistant lines get their tag back so the model keeps the habit."""
    out = [{"role": "system", "content": system_prompt(persona)}]
    for m in history:
        content = m["content"]
        if m["role"] == "assistant" and m.get("tag"):
            content = f"{content} [{m['tag']}]"
        out.append({"role": m["role"], "content": content})
    out.append({"role": "user", "content": text[:MAX_TEXT]})
    return out
