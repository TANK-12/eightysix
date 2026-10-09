"""The Calendar's event log: one SQLite file that anyone can write to.

Emerson asked on 2026-09-24 for "a calendar app that is locally generated or
updated by you and me and jan and nyarch and python scripts, basically logs of
things that happen or said or app opened and times and stuff".

An event is a moment (``ts``, optional ``end_ts``, both Unix seconds) with a
``source`` (emerson, claude, jan, nyarch, apps, forge, hyprland,
script:<name>), a ``kind`` (said, app_open, app_close, session, task, note,
reminder, milestone), a title, a body and tags. ``key`` is an optional unique
id a feeder sets, so reading the same history twice never logs anything twice.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
from pathlib import Path

KINDS = (
    "said",
    "app_open",
    "app_close",
    "session",
    "task",
    "note",
    "reminder",
    "milestone",
)
MAX_TITLE = 200
MAX_BODY = 4000
# Times outside years 1..9999 (or inf / nan) are refused: Python's datetime
# and the page's Date cannot show them, and an inf once made every search
# that met it fail.
MIN_TS = -62135596800.0
MAX_TS = 253402300799.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    end_ts REAL,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    key TEXT UNIQUE,
    done INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS events_source ON events(source);
"""


# Numbers typed next to "sudo" or "password" are masked before storing, so a
# password Emerson typed into a chat never lands in a second place.
SECRET_NEAR = re.compile(
    r"(?i)((?:sudo|passw(?:or)?d|pass(?:code)?|pin)\W{0,3}(?:\w+\W{1,3}){0,3}?)(\d{3,})"
    r"|(\d{3,})(\W{0,3}(?:is\W+)?(?:my\W+)?(?:sudo|passw(?:or)?d)\b)"
)


def redact(text: str) -> str:
    def mask(m: re.Match) -> str:
        if m.group(2):
            return m.group(1) + "••••"
        return "••••" + m.group(4)

    return SECRET_NEAR.sub(mask, text)


class EventError(ValueError):
    """A bad event. The message is safe to show the user."""


def seconds(value, name: str) -> float:
    if isinstance(value, bool):
        raise EventError(f"{name} must be a time in seconds")
    try:
        t = float(value)
    except (TypeError, ValueError, OverflowError):
        raise EventError(f"{name} must be a time in seconds")
    if not (math.isfinite(t) and MIN_TS <= t <= MAX_TS):
        raise EventError(f"{name} must be a time in seconds")
    return t


def ends_before(ts: float | None, end: float | None) -> None:
    if ts is not None and end is not None and end < ts:
        raise EventError("the end must not be before the start")


def clean(event: dict, partial: bool = False) -> dict:
    """Validate an event (or, with partial, a set of changes to one)."""
    out: dict = {}
    if not partial or "ts" in event:
        ts = event.get("ts")
        if ts is None and partial:
            # a change to "no time" must not quietly move the event to now
            raise EventError("ts must be a time in seconds")
        out["ts"] = time.time() if ts is None else seconds(ts, "ts")
    if "end_ts" in event:
        end = event.get("end_ts")
        out["end_ts"] = None if end in (None, "") else seconds(end, "end_ts")
    ends_before(out.get("ts"), out.get("end_ts"))
    if not partial or "source" in event:
        source = str(event.get("source") or "emerson").strip().lower()[:40]
        if not source.replace(":", "").replace("_", "").replace("-", "").isalnum():
            raise EventError("source may use letters, digits, : _ -")
        out["source"] = source
    if not partial or "kind" in event:
        kind = str(event.get("kind") or "note")
        if kind not in KINDS:
            raise EventError(f"kind must be one of {', '.join(KINDS)}")
        out["kind"] = kind
    if not partial or "title" in event:
        title = redact(" ".join(str(event.get("title") or "").split()))[:MAX_TITLE]
        if not title:
            raise EventError("An event needs a title")
        out["title"] = title
    if not partial or "body" in event:
        out["body"] = redact(str(event.get("body") or ""))[:MAX_BODY]
    if not partial or "tags" in event:
        tags = event.get("tags") or []
        if isinstance(tags, str):
            tags = [t for t in tags.replace(",", " ").split() if t]
        elif not isinstance(tags, (list, tuple, dict)):
            raise EventError("tags must be a list or words split by commas")
        out["tags"] = json.dumps([str(t)[:30] for t in tags][:12])
    if "key" in event and event["key"] is not None:
        out["key"] = str(event["key"])[:200]
    if "done" in event:
        out["done"] = 1 if event["done"] else 0
    return out


def row(r: sqlite3.Row) -> dict:
    d = dict(r)
    end = d.get("end_ts")
    if end is not None and not (math.isfinite(end) and MIN_TS <= end <= MAX_TS):
        d["end_ts"] = None
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["done"] = bool(d.get("done"))
    return d


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        with self._lock:
            self.db.close()

    def add(self, event: dict) -> dict | None:
        """Store one event. None when its key was already logged."""
        e = clean(event)
        e["created"] = time.time()
        cols = ", ".join(e)
        marks = ", ".join("?" for _ in e)
        with self._lock:
            cur = self.db.execute(
                f"INSERT OR IGNORE INTO events ({cols}) VALUES ({marks})",
                list(e.values()),
            )
            self.db.commit()
            if cur.rowcount == 0:
                return None
            return self.get(cur.lastrowid or 0, locked=True)

    def add_many(self, events: list[dict]) -> int:
        added = 0
        for event in events:
            try:
                if self.add(event):
                    added += 1
            except EventError:
                continue
        return added

    def get(self, event_id: int, locked: bool = False) -> dict | None:
        def read():
            r = self.db.execute(
                "SELECT * FROM events WHERE id = ?", (event_id,)
            ).fetchone()
            return row(r) if r else None

        if locked:
            return read()
        with self._lock:
            return read()

    def update(self, event_id: int, changes: dict) -> dict | None:
        e = clean(changes, partial=True)
        e.pop("key", None)
        if not e:
            return self.get(event_id)
        if "ts" in e or "end_ts" in e:
            old = self.get(event_id)
            if old:
                ends_before(e.get("ts", old["ts"]), e.get("end_ts", old["end_ts"]))
        sets = ", ".join(f"{k} = ?" for k in e)
        with self._lock:
            self.db.execute(
                f"UPDATE events SET {sets} WHERE id = ?", [*e.values(), event_id]
            )
            self.db.commit()
            return self.get(event_id, locked=True)

    def delete(self, event_id: int) -> bool:
        with self._lock:
            cur = self.db.execute("DELETE FROM events WHERE id = ?", (event_id,))
            self.db.commit()
            return cur.rowcount > 0

    def query(
        self,
        start: float | None = None,
        end: float | None = None,
        sources: list[str] | None = None,
        kinds: list[str] | None = None,
        text: str = "",
        limit: int = 2000,
    ) -> list[dict]:
        # rows stored before times were checked may hold inf: never send them
        where, args = ["ts BETWEEN ? AND ?"], [MIN_TS, MAX_TS]
        if start is not None:
            where.append("COALESCE(end_ts, ts) >= ?")
            args.append(start)
        if end is not None:
            where.append("ts < ?")
            args.append(end)
        if sources:
            where.append(
                "(" + " OR ".join("source = ? OR source LIKE ?" for _ in sources) + ")"
            )
            for s in sources:
                args += [s, f"{s}:%"]
        if kinds:
            where.append(f"kind IN ({', '.join('?' for _ in kinds)})")
            args += kinds
        # SQLite refuses a LIKE pattern of about 50 000 characters (500)
        text = text[:200]
        if text:
            where.append("(title LIKE ? OR body LIKE ? OR tags LIKE ?)")
            args += [f"%{text}%"] * 3
        sql = "SELECT * FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts LIMIT ?"
        args.append(max(1, min(10000, limit)))
        with self._lock:
            return [row(r) for r in self.db.execute(sql, args)]

    def day_counts(self, start: float, end: float, utc_offset: float) -> dict:
        """{"YYYY-MM-DD": {source: count}} in the viewer's time zone."""
        with self._lock:
            rows = self.db.execute(
                "SELECT date(ts + ?, 'unixepoch') AS day, source, COUNT(*) AS n "
                "FROM events WHERE ts >= ? AND ts < ? AND ts BETWEEN ? AND ? "
                "GROUP BY day, source",
                (utc_offset, start, end, MIN_TS, MAX_TS),
            ).fetchall()
        out: dict[str, dict[str, int]] = {}
        for r in rows:
            base = r["source"].split(":")[0]
            out.setdefault(r["day"], {})
            out[r["day"]][base] = out[r["day"]].get(base, 0) + r["n"]
        return out

    def due_reminders(self, now: float) -> list[dict]:
        with self._lock:
            return [
                row(r)
                for r in self.db.execute(
                    "SELECT * FROM events WHERE kind = 'reminder' AND done = 0 AND ts <= ?",
                    (now,),
                )
            ]

    def prune(self, keep_days: int, now: float | None = None) -> int:
        """Drop logged activity older than keep_days. Emerson's own notes,
        reminders and milestones are never pruned."""
        if keep_days <= 0:
            return 0
        cutoff = (now or time.time()) - keep_days * 86400
        with self._lock:
            cur = self.db.execute(
                "DELETE FROM events WHERE ts < ? AND source != 'emerson' "
                "AND kind NOT IN ('reminder', 'milestone')",
                (cutoff,),
            )
            self.db.commit()
            return cur.rowcount
