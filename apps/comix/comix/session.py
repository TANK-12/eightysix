"""Emerson's comix.to login, borrowed from the Forge Browser.

He logs in once in the Forge Browser (a real WebKit window, so captchas and
"sign in with Google" work). That browser keeps its cookies in a libsoup
``cookies.sqlite``. Comix reads the cookies for one site from a temporary copy
of that file (the live file is never opened for writing) and hands them to its
own headless Chrome as DevTools ``Network.setCookies`` parameters. No password
is ever stored here.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

COOKIE_DB = Path(
    os.environ.get(
        "COMIX_COOKIE_DB",
        Path.home() / ".local/share/forge/browser-profile/cookies.sqlite",
    )
)
# libsoup's SoupSameSitePolicy numbering
_SAME_SITE = {0: "None", 1: "Lax", 2: "Strict"}


def _host_matches(host: str, domain: str) -> bool:
    host = host.lstrip(".")
    return host == domain or host.endswith("." + domain)


def read_cookies(domain: str, db: Path | None = None) -> list[dict]:
    """Unexpired cookies for ``domain`` and its subdomains, as CDP cookie params."""
    db = db or COOKIE_DB
    if not db.exists():
        return []
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "cookies.sqlite"
        shutil.copy2(db, copy)
        con = sqlite3.connect(str(copy))
        try:
            rows = con.execute(
                "select name, value, host, path, expiry, isSecure, isHttpOnly, "
                "sameSite from moz_cookies"
            ).fetchall()
        finally:
            con.close()
    now = time.time()
    out = []
    for name, value, host, path, expiry, secure, http_only, same_site in rows:
        if not _host_matches(host or "", domain):
            continue
        if expiry and expiry < now:
            continue
        cookie = {
            "name": name,
            "value": value,
            "domain": host,
            "path": path or "/",
            "secure": bool(secure),
            "httpOnly": bool(http_only),
        }
        if expiry:
            cookie["expires"] = float(expiry)
        if same_site in _SAME_SITE:
            cookie["sameSite"] = _SAME_SITE[same_site]
        out.append(cookie)
    return out


def summary(domain: str, db: Path | None = None) -> dict:
    """What the page shows: whether any login cookies exist yet, never values."""
    cookies = read_cookies(domain, db)
    return {
        "cookies": len(cookies),
        "names": sorted({c["name"] for c in cookies}),
        "profile_found": (db or COOKIE_DB).exists(),
    }
