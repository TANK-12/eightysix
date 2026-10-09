"""Web logins Forge can open side by side, from shared/accounts.json.

Every account has its own Firefox profile under
~/.local/share/forge/accounts/<id>/firefox: a separate Firefox with its own
logins and its own window (Wayland app id forge-<id>), so two claude.ai
logins, Gemini and two Gmail accounts can all be signed in at once.

Signing in happens with remote control OFF. Firefox under remote control
sets navigator.webdriver and paints the address bar in red stripes, and
Google (Gmail, Gemini, "Sign in with Google" on claude.ai) refuses to sign in
such a browser as "not secure". So open_account starts a plain Firefox by
default; only control=True (for Claude to read or click in the page, after
signing in) adds --remote-debugging-port. Bringing a login into Forge reads
the profile's cookie file and never needs the port.

Claude Code accounts are not here: the Claude app keeps those (apps/claude).

    python forge_accounts.py list | open <id> [--control]
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ACCOUNTS_FILE = Path(
    os.environ.get("FORGE_ACCOUNTS_FILE", Path(__file__).with_name("accounts.json"))
)
DATA_DIR = Path(
    os.environ.get("FORGE_ACCOUNTS_DATA", Path.home() / ".local/share/forge/accounts")
)
KINDS = ("web",)
ACCOUNT_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")


class AccountError(Exception):
    """A bad registry entry, or an account that cannot be opened right now."""


# --- the registry -------------------------------------------------------------


def load(file: Path | None = None) -> dict:
    """The registry, checked: unique ids, known kinds, a port per account."""
    data = json.loads((file or ACCOUNTS_FILE).read_text(encoding="utf-8"))
    seen_ids: set[str] = set()
    seen_ports = {int(data.get("main_firefox_port", 9222))}
    for acct in data.get("accounts", []):
        aid = str(acct.get("id", ""))
        if not ACCOUNT_ID.fullmatch(aid):
            raise AccountError(
                f"Account id '{aid}' must be lowercase letters, digits, - or _"
            )
        if aid in seen_ids:
            raise AccountError(f"Account id '{aid}' is used twice")
        seen_ids.add(aid)
        if acct.get("kind", "web") not in KINDS:
            raise AccountError(
                f"Account '{aid}' has kind '{acct.get('kind')}'; use web"
            )
        acct["kind"] = "web"
        if not str(acct.get("url", "")).startswith(("https://", "http://")):
            raise AccountError(f"Account '{aid}' needs an http(s) url")
        port = acct.get("port")
        if not isinstance(port, int) or port in seen_ports:
            raise AccountError(f"Account '{aid}' needs its own port number")
        seen_ports.add(port)
    data["main_firefox_port"] = int(data.get("main_firefox_port", 9222))
    return data


def get(account_id: str, data: dict | None = None) -> dict:
    for acct in (data or load())["accounts"]:
        if acct["id"] == account_id:
            return acct
    raise AccountError(f"No account called '{account_id}'")


def port_for(account_id: str, data: dict | None = None) -> int:
    """The remote-control port of an account's Firefox. '' = your main
    Firefox, which only has one if you start it with
    `firefox --remote-debugging-port <main_firefox_port>`."""
    data = data or load()
    if not account_id:
        return data["main_firefox_port"]
    return get(account_id, data)["port"]


def profile_dir(acct: dict) -> Path:
    return DATA_DIR / acct["id"] / "firefox"


def web_argv(acct: dict, control: bool = False, firefox: str = "firefox") -> list[str]:
    """No --no-remote: running the same line again while that profile is open
    reaches the open window (a new tab, raised) instead of failing."""
    argv = [
        firefox,
        "--profile",
        str(profile_dir(acct)),
        "--name",
        f"forge-{acct['id']}",
    ]
    if control:
        argv += ["--remote-debugging-port", str(acct["port"])]
    return argv + [acct["url"]]


def running(profile: Path) -> bool:
    """Firefox keeps a `lock` symlink ("<ip>:+<pid>") in a profile while it
    has it open. One left behind by a Firefox that crashed or was killed
    names a process that is gone, so the pid is checked too."""
    lock = profile / "lock"
    if not lock.is_symlink():
        return False
    pid = os.readlink(lock).rpartition("+")[2]
    return pid.isdigit() and Path(f"/proc/{pid}").exists()


# A 50 MB disk cache per account instead of Firefox's smart sizing (up to
# about 1 GB each), since the laptop is short on disk.
PROFILE_PREFS = (
    'user_pref("browser.cache.disk.smart_size.enabled", false);',
    'user_pref("browser.cache.disk.capacity", 51200);',
)


def _ensure_prefs(profile: Path) -> None:
    profile.mkdir(parents=True, exist_ok=True)
    file = profile / "user.js"
    text = file.read_text(encoding="utf-8") if file.exists() else ""
    add = [line for line in PROFILE_PREFS if line not in text]
    if add:
        head = "" if not text or text.endswith("\n") else "\n"
        file.write_text(
            text + head + "// Forge: forge_accounts.py\n" + "\n".join(add) + "\n",
            encoding="utf-8",
        )


# --- bringing a login into Forge -----------------------------------------------


def read_cookies(account_id: str, data: dict | None = None) -> list[dict]:
    """The account's unexpired Firefox cookies, in the shape
    forge_views.ViewHost.import_cookies takes. Read from a temporary copy,
    so a running Firefox is never touched."""
    profile = profile_dir(get(account_id, data or load()))
    folder = Path(tempfile.mkdtemp(prefix="forge-accounts-"))
    try:
        for suffix in ("", "-wal"):
            source = profile / f"cookies.sqlite{suffix}"
            if source.is_file():
                shutil.copy2(source, folder / source.name)
        if not (folder / "cookies.sqlite").is_file():
            return []
        conn = sqlite3.connect(folder / "cookies.sqlite")
        try:
            rows = conn.execute(
                "SELECT name, value, host, path, expiry, isSecure, isHttpOnly, sameSite"
                " FROM moz_cookies WHERE originAttributes = ''"
            ).fetchall()
        finally:
            conn.close()
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    now = int(time.time())
    out = []
    for name, value, host, path, expiry, secure, http_only, same_site in rows:
        expiry = int(expiry or 0)
        if expiry > 100_000_000_000:  # milliseconds in newer Firefox
            expiry //= 1000
        if expiry and expiry < now:
            continue
        out.append(
            {
                "name": name,
                "value": value,
                "host": host,
                "path": path or "/",
                "expiry": expiry,
                "secure": bool(secure),
                "http_only": bool(http_only),
                "same_site": int(same_site or 0),
            }
        )
    return out


# --- opening ------------------------------------------------------------------


def _spawn(argv: list[str]) -> None:
    subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def open_account(
    account_id: str, data: dict | None = None, control: bool = False, spawn=_spawn
) -> str:
    """Open an account's own Firefox window and say what happened.

    control=False (signing in, everyday use): a plain Firefox Google accepts.
    control=True: with remote control, for Claude to read or click in it."""
    import forge_bidi

    data = data or load()
    acct = get(account_id, data)
    profile = profile_dir(acct)
    if running(profile):
        if control and not forge_bidi.port_open(acct["port"]):
            raise AccountError(
                f"{acct['label']} is open without remote control (for signing in)."
                " Close its window, then ask again and it reopens with control on."
            )
        spawn(web_argv(acct))  # reaches the open window: a tab, raised
        return f"{acct['label']} is already open; brought it forward."
    _ensure_prefs(profile)
    spawn(web_argv(acct, control=control))
    if control:
        return f"Opened {acct['label']} with remote control on (not for signing in)."
    return f"Opened {acct['label']} in its own Firefox window. Sign in there as usual."


def describe(data: dict | None = None) -> list[dict]:
    """Every account with whether its window is open, for a UI list."""
    data = data or load()
    return [{**acct, "open": running(profile_dir(acct))} for acct in data["accounts"]]


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(Path(__file__).parent))
    if not argv or argv[0] == "list":
        for row in describe():
            print(f"{row['id']:10} {'open' if row['open'] else '-':5} {row['label']}")
    elif argv[0] == "open" and len(argv) in (2, 3):
        print(open_account(argv[1], control="--control" in argv[2:]))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except AccountError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
