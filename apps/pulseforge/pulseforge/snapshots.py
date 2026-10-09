"""
Named points you can come back to.

Undo covers the last few moves in one editing session. This is the other thing
you want when you have built a shot you like and are about to try something
that might be worse: a named copy on disk that survives a reload, a crash, or
changing your mind a week later.

A snapshot stores the shot list *and copies of its painted regions*, because a
snapshot that referenced live mask files would silently change every time you
picked up a brush -- which is the exact opposite of the point.
"""

import json
import shutil
import time
from pathlib import Path


def _dir(project):
    d = Path(project.dir) / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(label):
    keep = "".join(c if c.isalnum() or c in " -_" else "" for c in str(label))
    return (keep.strip().replace(" ", "-").lower() or "snapshot")[:48]


def take(project, label=""):
    """Save the current shots under a name."""
    label = str(label or time.strftime("%H:%M:%S"))
    folder = _dir(project) / f"{int(time.time())}-{_slug(label)}"
    (folder / "masks").mkdir(parents=True, exist_ok=True)

    shots = json.loads(json.dumps(project.data.get("shots") or []))
    for shot in shots:
        for layer in shot.get("layers") or []:
            brush = (layer.get("region") or {}).get("brush")
            if not brush:
                continue
            src = project.masks_dir() / brush
            if src.exists():
                shutil.copyfile(src, folder / "masks" / brush)

    (folder / "snapshot.json").write_text(
        json.dumps(
            {
                "label": label,
                "taken": time.time(),
                "shots": shots,
                "target_seconds": project.data.get("target_seconds", 0.0),
                "ambience": project.data.get("ambience"),
                "overlay": project.data.get("overlay"),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return folder.name


def listing(project):
    """Every snapshot, newest first."""
    out = []
    root = _dir(project)
    for folder in sorted(root.iterdir(), reverse=True):
        meta = folder / "snapshot.json"
        if not folder.is_dir() or not meta.exists():
            continue
        try:
            data = json.loads(meta.read_text("utf-8"))
        except Exception:
            continue
        out.append(
            {
                "id": folder.name,
                "label": data.get("label", folder.name),
                "taken": data.get("taken", 0),
                "shots": len(data.get("shots") or []),
            }
        )
    return out


def restore(project, snapshot_id):
    """Put a snapshot back, restoring its masks over the live ones."""
    folder = _dir(project) / str(snapshot_id)
    meta = folder / "snapshot.json"
    if folder.parent != _dir(project) or not meta.exists():
        raise KeyError("no such snapshot")
    data = json.loads(meta.read_text("utf-8"))

    saved_masks = folder / "masks"
    if saved_masks.exists():
        for png in saved_masks.glob("*.png"):
            shutil.copyfile(png, project.masks_dir() / png.name)

    project.data["shots"] = data.get("shots") or []
    for key in ("target_seconds", "ambience", "overlay"):
        if data.get(key) is not None:
            project.data[key] = data[key]
    project.save()
    return project.data["shots"]


def delete(project, snapshot_id):
    folder = _dir(project) / str(snapshot_id)
    if folder.parent == _dir(project) and folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
        return True
    return False
