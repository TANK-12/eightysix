"""Questions spoken to Claude from anywhere (the Forge voice service).

POST /api/voice/ask hands the text to one visible conversation titled
"Voice" (made on first use, then reused; the default account, the read and
browse permission level, normal mode), so Emerson sees every spoken turn in
the list like any other. GET /api/voice/reply long-polls for the final
assistant text of that turn.

One voice turn runs at a time: each ask waits on its own thread until the
turn before it has ended, then sends, then watches the conversation's events
for the turn's `result`. The id of the Voice conversation is kept in
`voice_conversation.json` in the data folder; when that conversation has
been deleted a new one is made.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import runner

TITLE = "Voice"
MAX_CHARS = 4000
TURN_SECONDS = 600.0  # a voice turn that runs longer is given up on
KEEP_JOBS = 50


def reply_text(events: list[dict]) -> tuple[bool, str, str]:
    """(done, text, error) from a turn's events, oldest first. The final text
    is the result's own `result` when Claude Code gives one, else the text of
    the last assistant message."""
    last = ""
    for event in events:
        kind = event.get("type")
        if kind == "assistant":
            blocks = (event.get("message") or {}).get("content") or []
            text = "\n".join(
                b.get("text", "")
                for b in blocks
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
            if text:
                last = text
        elif kind == "result":
            bad = event.get("is_error") or event.get("subtype", "success") != "success"
            final = event.get("result")
            text = final.strip() if isinstance(final, str) and final.strip() else last
            if bad:
                return True, text, text or "Claude Code ended the turn with an error"
            return True, text, ""
        elif kind == "forge_exit":
            return True, last, "Claude Code stopped before it answered"
    return False, last, ""


class VoiceDesk:
    def __init__(self, registry: Callable[[], Any]):
        self._registry = registry  # a callable, so tests can swap the registry
        self._jobs: dict[str, dict] = {}
        self._cond = threading.Condition()
        self._turn = threading.Lock()

    def _store(self) -> Path:
        return Path(self._registry().data_dir) / "voice_conversation.json"

    def conversation(self) -> Any:
        """The Voice conversation, made when there is none."""
        registry = self._registry()
        store = self._store()
        try:
            conv_id = json.loads(store.read_text()).get("id", "")
        except (OSError, ValueError, AttributeError):
            conv_id = ""
        conv = registry.get(conv_id) if conv_id else None
        if conv is not None:
            return conv
        conv = registry.create("", "", runner.DEFAULT_MODE, "", "")
        conv.meta["title"] = TITLE
        conv.save_meta()
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(json.dumps({"id": conv.meta["id"]}))
        return conv

    def ask(self, text: str, source: str = "") -> str:
        """Start a voice turn; returns its id at once. ValueError when there
        is nothing to ask."""
        text = runner.clean_text(str(text or "")).strip()[:MAX_CHARS]
        if not text:
            raise ValueError("Nothing to ask")
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "source": str(source or "")[:40],
            "done": False,
            "text": "",
            "error": "",
            "conversation": "",
            "at": time.time(),
        }
        with self._cond:
            self._jobs[job_id] = job
            for old in list(self._jobs)[:-KEEP_JOBS]:
                if self._jobs[old]["done"]:
                    del self._jobs[old]
        threading.Thread(target=self._run, args=(job, text), daemon=True).start()
        return job_id

    def _finish(self, job: dict, text: str, error: str) -> None:
        with self._cond:
            job.update(done=True, text=text, error=error)
            self._cond.notify_all()

    def _run(self, job: dict, text: str) -> None:
        with self._turn:
            try:
                conv = self.conversation()
                job["conversation"] = conv.meta["id"]
                deadline = time.time() + TURN_SECONDS
                while conv.busy and time.time() < deadline:
                    time.sleep(0.2)  # a turn typed in the panel ends first
                seq = len(conv.events) - 1
                conv.send(text, [])
            except Exception as e:  # reported in the reply, never raised
                self._finish(job, "", f"Could not start the turn: {e}")
                return
            seen: list[dict] = []
            while time.time() < deadline:
                fresh = conv.events_after(seq, 5.0)
                if fresh:
                    seq = fresh[-1]["seq"]
                    seen.extend(fresh)
                    done, said, error = reply_text(seen)
                    if done:
                        self._finish(job, said, error)
                        return
            self._finish(job, reply_text(seen)[1], "Claude took too long")

    def reply(self, job_id: str, wait: float = 0.0) -> dict | None:
        """{done, text, error} for a voice turn, waiting up to `wait` seconds
        (at most 30) for it to end. None for an unknown id."""
        deadline = time.time() + max(0.0, min(30.0, float(wait)))
        with self._cond:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            while not job["done"] and time.time() < deadline:
                self._cond.wait(deadline - time.time())
            return {
                "done": job["done"],
                "text": job["text"],
                "error": job["error"],
                "conversation": job["conversation"],
            }
