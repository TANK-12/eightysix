"""The two attach routes a Forge chat box needs, for any app's FastAPI backend
(Relay task 118). The page (shared/forge_attach.js) uploads each file it is
given by paste, drop or the attach button, and sends the saved paths with the
message; the backend checks them with `paths()` and adds the note
(forge_attach.with_note) so the Claude session can open the files.

    ATTACH = forge_attach_api.Attachments(lambda: "<data dir>/attachments")
    app.include_router(ATTACH.router(dependencies=guarded))
    text = forge_attach.with_note(text, ATTACH.paths(body.files))

POST /api/attach              {name, data (base64)} -> {name, path, bytes}
POST /api/attach/paste-image  the desktop clipboard's image (WebKitGTK hands
                              a copied screenshot to the page only as a type)

Files land in <root>/YYYY-MM-DD/ and are never overwritten."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import forge_attach

# The Claude app's wl-paste reader, loaded by file: one copy for all of Forge.
CLIPBOARD = Path(__file__).resolve().parent.parent / "apps" / "claude" / "clipboard.py"


class Upload(BaseModel):
    name: str = "file"
    data: str = ""


def clipboard() -> ModuleType:
    spec = importlib.util.spec_from_file_location("forge_clipboard", CLIPBOARD)
    if spec is None or spec.loader is None:
        raise HTTPException(503, "The Claude app's clipboard reader is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _saved(path: Path) -> dict:
    return {"name": path.name, "path": str(path), "bytes": path.stat().st_size}


class Attachments:
    """One app's attachments folder, its size limits and its two routes."""

    def __init__(
        self,
        root: Callable[[], str | Path],
        max_bytes: int = 50 * 1024 * 1024,
        max_files: int = 20,
        what: str = "message",
    ) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self.max_files = max_files
        self.what = what

    def save(self, name: str, data: bytes) -> dict:
        try:
            path = forge_attach.save(
                forge_attach.day_folder(self.root()), name, data, self.max_bytes
            )
        except ValueError as e:
            raise HTTPException(413, str(e))
        except OSError as e:  # disk full, or the folder cannot be made
            raise HTTPException(507, f"Could not save the file: {e.strerror or e}")
        return _saved(path)

    def paths(self, files: Sequence[str]) -> list[str]:
        """The named files as full paths; each must be one this app saved, so
        a page cannot hand a session any path on the disk."""
        if len(files) > self.max_files:
            raise HTTPException(
                400, f"At most {self.max_files} files in one {self.what}"
            )
        out = []
        for name in files:
            found = forge_attach.inside(self.root(), name)
            if found is None:
                raise HTTPException(400, "An attached file is gone; attach it again")
            if str(found) not in out:  # the same file twice is named once
                out.append(str(found))
        return out

    def router(self, dependencies: Sequence = ()) -> APIRouter:
        r = APIRouter(dependencies=list(dependencies))

        @r.post("/api/attach")
        def attach(body: Upload):
            """A file as base64 JSON (no multipart dependency)."""
            try:
                data = forge_attach.decode_base64(body.data, self.max_bytes)
            except ValueError as e:
                raise HTTPException(413 if "larger" in str(e) else 400, str(e))
            return self.save(body.name, data)

        @r.post("/api/attach/paste-image")
        def attach_pasted_image(request: Request):
            """Only a JSON request: a form on another site cannot send one
            without asking first, so it cannot make the app save the
            clipboard."""
            kind = request.headers.get("content-type", "")
            if not kind.startswith("application/json"):
                raise HTTPException(415, "Send this as JSON")
            clip = clipboard()
            found = clip.read_image()
            if found is None:
                raise HTTPException(404, "There is no image on the clipboard")
            data, media = found
            return self.save("pasted" + clip.EXTENSIONS.get(media, ".png"), data)

        return r
