"""Logins: every web login in shared/accounts.json as a tab inside Forge.

The page asks forge.py (through the hub) for one WebKit view per account,
each with session=<account id>, so each has its own cookie store. This
backend lists the accounts, opens an account's own plain Firefox window for
signing in, and hands the page that account's Firefox cookies to
import. Writes need the header `X-Forge: 1`.

    cd ~/Forge/apps/logins && \\
    FORGE_SHARED_DIR=/home/ejb/Forge/shared \\
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8454
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR", ROOT.parent.parent / "shared"))
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

import forge_accounts  # noqa: E402

app = FastAPI(title="Logins")


def forge_only(x_forge: str | None = Header(default=None)) -> None:
    if x_forge != "1":
        raise HTTPException(403, "Send X-Forge: 1")


guarded = [Depends(forge_only)]


def _checked(fn, *args):
    try:
        return fn(*args)
    except forge_accounts.AccountError as e:
        raise HTTPException(400, str(e))
    except (OSError, ValueError) as e:
        raise HTTPException(500, f"accounts.json: {e}")


@app.get("/api/accounts")
def accounts():
    rows = _checked(forge_accounts.describe)
    return {
        "accounts": [
            {k: r.get(k) for k in ("id", "label", "kind", "url", "open")} for r in rows
        ]
    }


@app.post("/api/accounts/{account_id}/signin", dependencies=guarded)
def signin(account_id: str):
    return {"message": _checked(forge_accounts.open_account, account_id)}


# Guarded as well as a read: the answer is live login cookies.
@app.get("/api/accounts/{account_id}/cookies", dependencies=guarded)
def cookies(account_id: str):
    return {"cookies": _checked(forge_accounts.read_cookies, account_id)}


# --- static -----------------------------------------------------------------------

if SHARED_DIR.is_dir():
    app.mount("/shared", StaticFiles(directory=str(SHARED_DIR)), name="shared")


@app.get("/")
def index():
    target = STATIC_DIR / "index.html"
    if not target.is_file():
        return JSONResponse({"error": "static/index.html is missing"}, status_code=500)
    return FileResponse(target)


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
