"""Keymap -- view and edit every Hyprland keybind across all three shells
(end4-pC, Brain Shell, Caelestia) plus the personal-overrides file, from one
page.

Reads are a fresh parse of the Lua source files on every request (see
parser.py) -- there is no cached/stale model to fall out of sync with what
Hyprland will actually load. Writes go through editor.py, which backs up the
target file, patches only the matched literal, and rejects the write outright
if the result doesn't pass `luac -p`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import editor
import sources
from parser import parse_binds_file, resolve_vars_target

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
SHARED_DIR = os.environ.get("FORGE_SHARED_DIR") or os.path.join(
    ROOT, "..", "..", "shared"
)
sys.path.insert(0, os.path.abspath(SHARED_DIR))

app = FastAPI(title="Keymap")


@app.exception_handler(RequestValidationError)
async def bad_body(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """A 422 that names the bad field without echoing its value: FastAPI's
    own answer repeats the input, and a body of 1e999 or NaN cannot be
    written back as JSON, so it turned into a 500."""
    detail = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type")}
        for e in exc.errors()
    ]
    return JSONResponse({"detail": detail}, status_code=422)


def _editable_files() -> set[Path]:
    """The only files an edit or undo may write: every keybind file the scope
    registry lists, plus Caelestia's variables.lua. Anything else (a path
    typed into the API by hand) is refused before it is read or backed up."""
    files = {f for s in sources.load_scopes() for f in s.files}
    files.add(sources.VARIABLES_LUA)
    return {f.resolve() for f in files}


def _refusal(file: str, new_text: str, old_text: str) -> str | None:
    if Path(file).resolve() not in _editable_files():
        return f"{file} is not one of the keybind files Keymap edits"
    if not old_text:
        return "nothing to replace: the old key combo is empty"
    if not new_text.strip():
        return "the new key combo is empty"
    if "\n" in new_text or "\r" in new_text:
        return "a key combo has to stay on one line"
    return None


def _collect_binds() -> list[dict]:
    scopes = sources.load_scopes()
    seen_files: dict[Path, list[str]] = {}
    for s in scopes:
        for f in s.files:
            seen_files.setdefault(f, []).append(s.label)

    rows: list[dict] = []
    for file, scope_labels in seen_files.items():
        if not file.exists():
            continue
        for b in parse_binds_file(file):
            row = {
                "file": str(b.file),
                "line": b.start_line,
                "end_line": b.end_line,
                "scopes": scope_labels,
                "kind": b.kind,
                "description": b.description,
                "key_display": b.key_display,
                "editable": b.editable,
                "edit_file": str(b.edit_file) if b.edit_file else None,
                "edit_line": b.edit_line,
                "edit_old_text": b.edit_old_text,
            }
            if b.kind == "vars":
                resolved = resolve_vars_target(b.key_display, sources.VARIABLES_LUA)
                if resolved is not None:
                    v_file, v_line, v_old, v_display = resolved
                    row["editable"] = True
                    row["edit_file"] = str(v_file)
                    row["edit_line"] = v_line
                    row["edit_old_text"] = v_old
                    row["key_display"] = v_display
            rows.append(row)

    rows.sort(
        key=lambda r: (r["scopes"][0] if r["scopes"] else "", r["file"], r["line"])
    )
    return rows


class EditTarget(BaseModel):
    file: str
    line: int
    old_text: str
    new_text: str
    description: str | None = None
    scopes: list[str] = []


class BulkEditBody(BaseModel):
    targets: list[EditTarget]


@app.get("/api/binds")
def list_binds():
    return {"binds": _collect_binds()}


@app.post("/api/binds/edit")
def bulk_edit(body: BulkEditBody):
    results = []
    for t in body.targets:
        refused = _refusal(t.file, t.new_text, t.old_text)
        if refused:
            results.append({"ok": False, "file": t.file, "error": refused})
            continue
        try:
            entry = editor.apply_edit(
                file=Path(t.file),
                line=t.line,
                old_text=t.old_text,
                new_text=t.new_text,
                description=t.description,
                scopes=t.scopes,
            )
            results.append({"ok": True, "file": t.file, "history_id": entry.id})
        except editor.EditConflict as e:
            results.append({"ok": False, "file": t.file, "error": str(e)})
        except editor.SyntaxCheckFailed as e:
            results.append(
                {
                    "ok": False,
                    "file": t.file,
                    "error": f"luac rejected the change: {e.luac_output}",
                }
            )
        except (OSError, UnicodeDecodeError) as e:
            results.append(
                {"ok": False, "file": t.file, "error": f"could not edit the file: {e}"}
            )
    return {"results": results}


@app.get("/api/history")
def history():
    return {"history": editor.read_history()}


@app.post("/api/undo/{history_id}")
def undo(history_id: str):
    target = next((e for e in editor.read_history() if e["id"] == history_id), None)
    if target is None:
        raise HTTPException(404, "no such history entry")
    refused = _refusal(target["file"], target["old_text"], target["new_text"])
    if refused:
        raise HTTPException(409, refused)
    try:
        entry = editor.undo(history_id)
    except KeyError:
        raise HTTPException(404, "no such history entry")
    except editor.EditConflict as e:
        raise HTTPException(409, str(e))
    except editor.SyntaxCheckFailed as e:
        raise HTTPException(422, f"luac rejected the revert: {e.luac_output}")
    except (OSError, UnicodeDecodeError) as e:
        raise HTTPException(409, f"could not edit the file: {e}")
    return {"ok": True, "history_id": entry.id}


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as handle:
        return handle.read()


if os.path.isdir(SHARED_DIR):
    app.mount("/shared", StaticFiles(directory=SHARED_DIR), name="shared")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
