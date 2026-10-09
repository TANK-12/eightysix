"""Conversations: messages on disk, and a trimmed view that fits a small model.

Stored as one JSON file each in ~/.local/share/forge/acchan/conversations.
The trimmed view keeps the newest messages that fit a character budget,
shortens old tool results (the model already acted on them), and never
starts on a tool result whose call was cut off, which Qwen's template rejects.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

DATA = Path(os.environ.get("ACCHAN_DATA", Path.home() / ".local/share/forge/acchan"))
OLD_RESULT = 400  # characters kept of a tool result more than two turns back


ID_RE = re.compile(r"[\w-]{1,120}")


def valid_id(cid) -> bool:
    """A conversation id names one file in the folder: letters, digits, _
    and - only, so no id can reach settings.json or anything outside."""
    return isinstance(cid, str) and ID_RE.fullmatch(cid) is not None


def folder() -> Path:
    path = DATA / "conversations"
    path.mkdir(parents=True, exist_ok=True)
    return path


class Conversation:
    def __init__(
        self, cid: str | None = None, title: str = "", source: str = ""
    ) -> None:
        self.id = cid or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.title = title
        self.source = source  # "tui", "web", "nyarch" ...
        self.messages: list[dict] = []
        self.toolsets: list[str] = []
        # The model size this chat has settled on ("" until the first reply).
        self.tier = ""
        # Older messages folded into a short summary so the chat is not
        # forgotten when it outgrows the model's budget; messages before
        # summary_upto are covered by it and no longer sent.
        self.summary = ""
        self.summary_upto = 0
        self.created = time.time()
        self.updated = self.created

    # ------------------------------------------------------------ persistence
    @property
    def path(self) -> Path:
        return folder() / f"{self.id}.json"

    def save(self) -> None:
        self.updated = time.time()
        if not self.title:
            first = next(
                (m["content"] for m in self.messages if m["role"] == "user"), ""
            )
            first = re.sub(r"^\(Working folder: [^)]*\)\n", "", first)
            self.title = (
                (first[:60] + ("…" if len(first) > 60 else "")) if first else "New chat"
            )
        data = {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "created": self.created,
            "updated": self.updated,
            "toolsets": self.toolsets,
            "tier": self.tier,
            "summary": self.summary,
            "summary_upto": self.summary_upto,
            "messages": self.messages,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    @classmethod
    def load(cls, cid: str) -> "Conversation":
        if not valid_id(cid):
            raise ValueError(f"not a conversation id: {str(cid)[:40]!r}")
        data = json.loads((folder() / f"{cid}.json").read_text(encoding="utf-8"))
        # the id inside the file decides where it saves, so it must be a plain
        # name too (a hand-edited "../settings" would write outside the folder)
        if not isinstance(data, dict) or not valid_id(data.get("id")):
            raise ValueError(f"not a conversation file: {cid}")
        conv = cls(data["id"], data.get("title", ""), data.get("source", ""))
        conv.messages = data.get("messages", [])
        conv.toolsets = data.get("toolsets", [])
        conv.tier = data.get("tier", "")
        conv.summary = data.get("summary", "")
        conv.summary_upto = data.get("summary_upto", 0)
        conv.created = data.get("created", conv.created)
        conv.updated = data.get("updated", conv.updated)
        return conv

    @staticmethod
    def list_all() -> list[dict]:
        rows = []
        for file in folder().glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            # one odd file (hand-edited, half-written) must not break the list
            if not isinstance(data, dict) or not valid_id(data.get("id")):
                continue
            updated = data.get("updated", 0)
            messages = data.get("messages")
            rows.append(
                {
                    "id": data["id"],
                    "title": str(data.get("title") or "New chat"),
                    "source": str(data.get("source") or ""),
                    "updated": (
                        updated
                        if isinstance(updated, (int, float))
                        and not isinstance(updated, bool)
                        else 0
                    ),
                    "count": len(messages) if isinstance(messages, list) else 0,
                }
            )
        return sorted(rows, key=lambda r: -r["updated"])

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)

    # ------------------------------------------------------------- messages
    def add(self, message: dict) -> None:
        self.messages.append(message)

    @staticmethod
    def size(message: dict) -> int:
        return len(message.get("content") or "") + len(
            json.dumps(message.get("tool_calls", ""))
        )

    def unsummarised(self) -> int:
        """Characters of history not yet folded into the summary."""
        return sum(self.size(m) for m in self.messages[self.summary_upto :])

    def fold_point(self, keep: int) -> int:
        """Where to cut so that at most `keep` characters stay as full
        messages: always at the start of a user turn, never inside the
        newest turn."""
        user_turns = [
            i
            for i, m in enumerate(self.messages)
            if m["role"] == "user" and i > self.summary_upto
        ]
        cut = self.summary_upto
        for index in user_turns[:-1]:
            cut = index
            if sum(self.size(m) for m in self.messages[index:]) <= keep:
                break
        return cut

    def trimmed(self, budget: int) -> list[dict]:
        """Newest messages that fit `budget` characters, ready to send."""
        user_turns = [i for i, m in enumerate(self.messages) if m["role"] == "user"]
        recent_from = user_turns[-2] if len(user_turns) >= 2 else 0
        out: list[dict] = []
        used = 0
        for index in range(len(self.messages) - 1, self.summary_upto - 1, -1):
            message = dict(self.messages[index])
            content = message.get("content") or ""
            if (
                message["role"] == "tool"
                and index < recent_from
                and len(content) > OLD_RESULT
            ):
                message["content"] = content[:OLD_RESULT] + " …[older result shortened]"
            size = len(message.get("content") or "") + len(
                json.dumps(message.get("tool_calls", ""))
            )
            if out and used + size > budget:
                break
            used += size
            out.append(message)
        out.reverse()
        # Never begin with a tool result or an assistant tool call cut from
        # its user turn.
        while out and out[0]["role"] != "user":
            out.pop(0)
        return out
