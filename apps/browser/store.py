"""The Browser app's own records: bookmarks, history, open tabs, preferences.

One SQLite file at ~/.local/share/forge/browser/browser.db (FORGE_BROWSER_DATA
moves it). Cookies and site storage are not here: they live in the WebKit
profile forge.py owns (see forge_views.py).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import urllib.parse
from pathlib import Path

DATA_DIR = Path(
    os.environ.get("FORGE_BROWSER_DATA", Path.home() / ".local/share/forge/browser")
)

# Search engines, by name. Adding one is one row.
ENGINES = {
    "duckduckgo": "https://duckduckgo.com/?q={q}",
    "google": "https://www.google.com/search?q={q}",
    "brave": "https://search.brave.com/search?q={q}",
    "startpage": "https://www.startpage.com/do/search?q={q}",
}
DEFAULT_PREFS = {"engine": "duckduckgo", "home": "about:blank", "restore_tabs": True}

_lock = threading.Lock()
_HOSTLIKE = re.compile(
    r"^(localhost|[\w-]+(\.[\w-]+)+|\d{1,3}(\.\d{1,3}){3})(:\d+)?(/.*)?$"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookmarks (
  url TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', folder TEXT NOT NULL DEFAULT '',
  added REAL NOT NULL);
CREATE TABLE IF NOT EXISTS history (
  url TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', visits INTEGER NOT NULL DEFAULT 0,
  last REAL NOT NULL);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def db_path() -> Path:
    return DATA_DIR / "browser.db"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def resolve(text: str, engine: str = "duckduckgo") -> str:
    """What the address bar means: a web or file:/// address as typed, a path
    on this computer (/x, ~/x) as a file:/// address, a host with the scheme
    added, or a search."""
    text = (text or "").strip()
    if not text:
        return "about:blank"
    if text.startswith(("http://", "https://", "file:///")) or text == "about:blank":
        return text
    if text == "~" or text.startswith(("/", "~/")):
        return Path(os.path.expanduser(text)).as_uri()
    if " " not in text and _HOSTLIKE.match(text):
        scheme = "http" if text.startswith(("localhost", "127.")) else "https"
        return f"{scheme}://{text}"
    template = ENGINES.get(engine, ENGINES["duckduckgo"])
    return template.replace("{q}", urllib.parse.quote_plus(text))


# Longer addresses are not kept: a record that size is junk, not a page.
MAX_URL = 8192


# Spaces, control characters and the bidi overrides that make an address read
# as something else never belong in a real one (a browser sends them escaped).
_NOT_IN_URL = re.compile(r"[\x00-\x20\x7f\u202a-\u202e\u2066-\u2069]")


def web(url) -> bool:
    return (
        isinstance(url, str)
        and url.startswith(("http://", "https://"))
        and not _NOT_IN_URL.search(url)
    )


def keepable(url) -> bool:
    """A web address short enough to keep in the records."""
    return web(url) and len(url) <= MAX_URL


def local(url) -> bool:
    """A file on this computer: a tab may show one, but it is never a
    bookmark or a history row."""
    return (
        isinstance(url, str)
        and url.startswith("file:///")
        and not _NOT_IN_URL.search(url)
        and len(url) <= MAX_URL
    )


def tab_url(url) -> bool:
    """An address a saved tab may hold."""
    return keepable(url) or local(url) or url == "about:blank"


# --- bookmarks -----------------------------------------------------------------


def add_bookmark(url: str, title: str = "", folder: str = "") -> None:
    with _lock, connect() as conn:
        conn.execute(
            "INSERT INTO bookmarks (url, title, folder, added) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(url) DO UPDATE SET title = excluded.title,"
            " folder = CASE WHEN excluded.folder != '' THEN excluded.folder ELSE folder END",
            (url, title, folder, time.time()),
        )


def remove_bookmark(url: str) -> None:
    with _lock, connect() as conn:
        conn.execute("DELETE FROM bookmarks WHERE url = ?", (url,))


def bookmarks() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM bookmarks ORDER BY folder, added").fetchall()
    return [dict(r) for r in rows]


# --- history ------------------------------------------------------------------------


def record_visit(
    url: str, title: str = "", visits: int = 1, when: float | None = None
) -> None:
    with _lock, connect() as conn:
        conn.execute(
            "INSERT INTO history (url, title, visits, last) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(url) DO UPDATE SET visits = visits + excluded.visits,"
            " title = CASE WHEN excluded.title != '' THEN excluded.title ELSE title END,"
            " last = MAX(last, excluded.last)",
            (url, title, visits, when or time.time()),
        )


def search_history(query: str = "", limit: int = 50) -> list[dict]:
    """Matches in the address or title, most visited and most recent first."""
    like = f"%{query.strip()}%"
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM history WHERE url LIKE ? OR title LIKE ?"
            " ORDER BY visits DESC, last DESC LIMIT ?",
            (like, like, max(1, min(500, limit))),
        ).fetchall()
    return [dict(r) for r in rows]


def recent(limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM history ORDER BY last DESC LIMIT ?",
            (max(1, min(500, limit)),),
        ).fetchall()
    return [dict(r) for r in rows]


def clear_history() -> None:
    with _lock, connect() as conn:
        conn.execute("DELETE FROM history")


# --- tabs and preferences -----------------------------------------------------------


def _get(key: str, default):
    with connect() as conn:
        row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    try:
        return json.loads(row["value"]) if row else default
    except ValueError:
        return default


def _put(key: str, value) -> None:
    with _lock, connect() as conn:
        conn.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


def session() -> dict:
    data = _get("session", {"tabs": [], "active": 0})
    tabs = [
        {"url": t["url"], "title": str(t.get("title", ""))}
        for t in data.get("tabs", [])
        if isinstance(t, dict) and tab_url(t.get("url"))
    ]
    return {"tabs": tabs, "active": int(data.get("active", 0) or 0)}


def save_session(tabs: list, active: int) -> dict:
    _put("session", {"tabs": tabs, "active": active})
    return session()


def prefs() -> dict:
    stored = _get("prefs", {})
    out = dict(DEFAULT_PREFS)
    if stored.get("engine") in ENGINES:
        out["engine"] = stored["engine"]
    if web(stored.get("home")) or stored.get("home") == "about:blank":
        out["home"] = stored["home"]
    if isinstance(stored.get("restore_tabs"), bool):
        out["restore_tabs"] = stored["restore_tabs"]
    return out


def save_prefs(changes: dict) -> dict:
    # A yes/no that is not a real bool is dropped, so "no" never reads as yes.
    merged = dict(
        prefs(),
        **{
            k: v
            for k, v in (changes or {}).items()
            if k in DEFAULT_PREFS and (k != "restore_tabs" or isinstance(v, bool))
        },
    )
    _put("prefs", merged)
    return prefs()
