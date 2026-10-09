"""
A project as a single file.

Everything a project is currently lives in a folder under `~/PulseForgeData`,
which is fine until you want to back one up, move it to another machine, or send
someone the look you built. This packs it into one `.pfproj` (an ordinary zip,
so it is inspectable and repairable) and reads it back.

Media is **optional**. The JSON and the painted masks are a few kilobytes; the
songs and backgrounds are hundreds of megabytes. Most of the time what you want
to keep is the work, not another copy of the music, so that is the default.
"""

import json
import os
import shutil
import zipfile
from pathlib import Path

from . import strictjson

SUFFIX = ".pfproj"
MANIFEST = "pulseforge-project.json"
MEDIA_EXTS = (
    ".mp3",
    ".wav",
    ".flac",
    ".m4a",
    ".ogg",
    ".opus",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".gif",
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".m4v",
)


def export(project, out_path, include_media=False):
    """Write the project to `out_path`. Returns (path, bytes)."""
    root = Path(project.dir)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            MANIFEST,
            json.dumps(
                {
                    "format": 1,
                    "slug": project.slug,
                    "includes_media": bool(include_media),
                    "data": project.data,
                },
                indent=2,
                ensure_ascii=False,
            ),
        )
        for sub in ("masks", "assets"):
            folder = root / sub
            if not folder.is_dir():
                continue
            for f in sorted(folder.rglob("*")):
                if not f.is_file():
                    continue
                media = f.suffix.lower() in MEDIA_EXTS
                # masks are the work and always travel; assets are usually media
                if sub == "assets" and media and not include_media:
                    continue
                z.write(f, str(Path(sub) / f.relative_to(folder)))
        if include_media:
            for f in sorted(root.glob("*")):
                if f.is_file() and f.suffix.lower() in MEDIA_EXTS:
                    z.write(f, f.name)
    return str(out_path), os.path.getsize(out_path)


def _read_manifest(z):
    """The manifest, refused when it holds NaN or Infinity (a project made
    from it could not be opened) or is not a PulseForge manifest at all."""
    try:
        meta = strictjson.loads(z.read(MANIFEST).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise ValueError(f"that project file is damaged ({e})")
    if not isinstance(meta, dict) or not isinstance(meta.get("data") or {}, dict):
        raise ValueError("that is not a PulseForge project file")
    return meta


def inspect(path):
    """What is in a file, without unpacking it."""
    with zipfile.ZipFile(path) as z:
        if MANIFEST not in z.namelist():
            raise ValueError("that is not a PulseForge project file")
        meta = _read_manifest(z)
    data = meta.get("data") or {}
    return {
        "name": data.get("name", meta.get("slug", "")),
        "slug": meta.get("slug", ""),
        "songs": len(data.get("playlist") or []),
        "shots": len(data.get("shots") or []),
        "includes_media": bool(meta.get("includes_media")),
    }


def _safe_members(z):
    """Skip anything trying to escape the project folder."""
    for name in z.namelist():
        p = Path(name)
        if p.is_absolute() or ".." in p.parts:
            continue
        yield name


def restore(path, project):
    """Unpack into a project. Existing files with the same name are replaced."""
    root = Path(project.dir)
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as z:
        if MANIFEST not in z.namelist():
            raise ValueError("that is not a PulseForge project file")
        meta = _read_manifest(z)
        for name in _safe_members(z):
            if name == MANIFEST:
                continue
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(name) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)

    data = meta.get("data") or {}
    keep_name = project.data.get("name")
    project.data.update(data)
    if keep_name:
        project.data["name"] = keep_name
    # the playlist may point at songs that were not packed
    project.data["playlist"] = [
        n for n in (project.data.get("playlist") or []) if (root / n).exists()
    ]
    project.save()
    return project.data
