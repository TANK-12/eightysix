"""Reading the user's Firefox profile: bookmarks, history and cookies.

Firefox keeps its databases locked and in WAL mode while it runs, so every
read works on a private copy (the .sqlite plus its -wal file) in a temporary
folder that is deleted straight after. Nothing in the Firefox profile is ever
written.

What cannot come across: Firefox's page cache and site storage use formats
only Firefox reads, and saved passwords are encrypted with Firefox's own key.
Cookies do come across, which is what keeps sites logged in.
"""

from __future__ import annotations

import configparser
import os
import shutil
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

ROOTS = [
    Path(os.environ.get("FORGE_FIREFOX_ROOT", Path.home() / ".config/mozilla/firefox")),
    Path.home() / ".mozilla/firefox",
]


def find_profile(roots: list[Path] | None = None) -> Path | None:
    """The profile Firefox itself would open: the install default, else the
    profile marked Default=1, else the one with the newest history."""
    for root in roots or ROOTS:
        ini = root / "profiles.ini"
        if not ini.is_file():
            continue
        parser = configparser.ConfigParser()
        try:
            parser.read(ini)
        except configparser.Error:
            continue

        def resolve(section: str) -> Path | None:
            path = parser.get(section, "Path", fallback="")
            if not path:
                return None
            relative = parser.get(section, "IsRelative", fallback="1") == "1"
            full = root / path if relative else Path(path)
            return full if (full / "places.sqlite").is_file() else None

        for section in parser.sections():
            if section.startswith("Install"):
                default = parser.get(section, "Default", fallback="")
                full = root / default
                if default and (full / "places.sqlite").is_file():
                    return full
        for section in parser.sections():
            if (
                section.startswith("Profile")
                and parser.get(section, "Default", fallback="") == "1"
            ):
                found = resolve(section)
                if found:
                    return found
        candidates = [
            p
            for s in parser.sections()
            if s.startswith("Profile")
            for p in [resolve(s)]
            if p
        ]
        if candidates:
            return max(candidates, key=lambda p: (p / "places.sqlite").stat().st_mtime)
    return None


@contextmanager
def _copy(profile: Path, name: str):
    folder = tempfile.mkdtemp(prefix="forge-firefox-")
    try:
        for suffix in ("", "-wal"):
            source = profile / f"{name}{suffix}"
            if source.is_file():
                shutil.copy2(source, Path(folder) / source.name)
        target = Path(folder) / name
        if not target.is_file():
            yield None
            return
        conn = sqlite3.connect(target)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def read_bookmarks(profile: Path) -> list[dict]:
    with _copy(profile, "places.sqlite") as conn:
        if conn is None:
            return []
        rows = conn.execute(
            "SELECT p.url, COALESCE(b.title, p.title, '') AS title,"
            " COALESCE(f.title, '') AS folder, b.dateAdded AS added"
            " FROM moz_bookmarks b JOIN moz_places p ON p.id = b.fk"
            " LEFT JOIN moz_bookmarks f ON f.id = b.parent"
            " WHERE b.type = 1 AND (p.url LIKE 'http://%' OR p.url LIKE 'https://%')"
            " ORDER BY b.dateAdded"
        ).fetchall()
    return [dict(r) for r in rows]


def read_history(profile: Path, limit: int = 20000) -> list[dict]:
    with _copy(profile, "places.sqlite") as conn:
        if conn is None:
            return []
        rows = conn.execute(
            "SELECT url, COALESCE(title, '') AS title, visit_count AS visits,"
            " COALESCE(last_visit_date, 0) AS last_us"
            " FROM moz_places WHERE visit_count > 0"
            " AND (url LIKE 'http://%' OR url LIKE 'https://%')"
            " ORDER BY last_visit_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "url": r["url"],
            "title": r["title"],
            "visits": r["visits"],
            "last": r["last_us"] / 1e6,
        }
        for r in rows
    ]


def expiry_seconds(value) -> int:
    """moz_cookies.expiry is seconds in older profiles and milliseconds in
    newer ones. A value past the year 5000 in seconds is milliseconds."""
    number = int(value or 0)
    return number // 1000 if number > 100_000_000_000 else number


def read_cookies(profile: Path) -> list[dict]:
    """Unexpired cookies, in the shape forge_views.ViewHost.import_cookies
    takes. Container and partitioned cookies (a non-empty originAttributes)
    are left out: WebKit has no place to put them."""
    now = int(time.time())
    with _copy(profile, "cookies.sqlite") as conn:
        if conn is None:
            return []
        rows = conn.execute(
            "SELECT name, value, host, path, expiry, isSecure, isHttpOnly, sameSite"
            " FROM moz_cookies WHERE originAttributes = ''"
        ).fetchall()
    out = []
    for r in rows:
        expiry = expiry_seconds(r["expiry"])
        if expiry and expiry < now:
            continue
        out.append(
            {
                "name": r["name"],
                "value": r["value"],
                "host": r["host"],
                "path": r["path"] or "/",
                "expiry": expiry,
                "secure": bool(r["isSecure"]),
                "http_only": bool(r["isHttpOnly"]),
                "same_site": int(r["sameSite"] or 0),
            }
        )
    return out
