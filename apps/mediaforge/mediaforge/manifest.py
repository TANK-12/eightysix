"""
Move-manifest / undo system — the safety net for the Library Organiser.

Every organise run writes a JSON manifest to ~/MediaForgeData/manifests/ recording
every file operation ({op, src, dst, size, hash}). Manifests are NEVER deleted
automatically. "Revert" replays a manifest backwards: dst -> src, undoing moves,
copies (delete the copy) and hardlinks (delete the link). Reverting is itself
recorded as a manifest, so you can even undo an undo.

Nothing here ever deletes an original file: organise only moves/copies/links, and
revert only moves things back or removes copies/links it created.
"""

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

from .config import MANIFEST_DIR


def quick_hash(path, chunk=1 << 20):
    """Fast content signature: size + sha1 of head+tail (good enough to tell if a
    file is the same one after a move / rename)."""
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError:
        return None
    h = hashlib.sha1()
    h.update(str(size).encode())
    try:
        with open(p, "rb") as f:
            h.update(f.read(chunk))
            if size > chunk * 2:
                f.seek(-chunk, os.SEEK_END)
                h.update(f.read(chunk))
    except OSError:
        return None
    return h.hexdigest()


class Manifest:
    def __init__(self, label="organise"):
        self.id = time.strftime("%Y%m%d-%H%M%S")
        self.label = label
        self.path = MANIFEST_DIR / f"{self.id}_{label}.json"
        self.entries = []
        self.started = time.time()

    def record(self, op, src, dst, size=0, file_hash=None, note=""):
        self.entries.append({
            "op": op, "src": str(src), "dst": str(dst),
            "size": size, "hash": file_hash, "note": note,
            "t": time.time(),
        })

    def save(self):
        data = {
            "id": self.id, "label": self.label,
            "started": self.started, "finished": time.time(),
            "count": len(self.entries), "entries": self.entries,
        }
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        return self.path


# --------------------------------------------------------------------------
# file operations used by the organiser
# --------------------------------------------------------------------------
def _ensure_parent(dst):
    Path(dst).parent.mkdir(parents=True, exist_ok=True)


def apply_op(op, src, dst):
    """op in move|copy|hardlink. Returns the actual dst used (may differ if the
    caller pre-resolved conflicts). Raises on failure."""
    src, dst = Path(src), Path(dst)
    _ensure_parent(dst)
    if op == "move":
        shutil.move(str(src), str(dst))
    elif op == "copy":
        shutil.copy2(str(src), str(dst))
    elif op == "hardlink":
        try:
            os.link(str(src), str(dst))
        except OSError:
            shutil.copy2(str(src), str(dst))
    else:
        raise ValueError(op)
    return dst


def list_manifests():
    out = []
    for p in sorted(MANIFEST_DIR.glob("*.json"), reverse=True):
        try:
            d = json.loads(p.read_text("utf-8"))
            out.append({"id": d.get("id"), "label": d.get("label"),
                        "count": d.get("count", 0),
                        "finished": d.get("finished"), "path": str(p)})
        except Exception:
            continue
    return out


def load_manifest(path):
    return json.loads(Path(path).read_text("utf-8"))


def revert(manifest_path, log=lambda s: None):
    """Undo a manifest. Returns (undone, skipped, new_manifest_path)."""
    data = load_manifest(manifest_path)
    rev = Manifest(label=f"revert-{data.get('id', 'x')}")
    undone = skipped = 0
    for e in reversed(data.get("entries", [])):
        op, src, dst = e["op"], Path(e["src"]), Path(e["dst"])
        if op in ("copy", "hardlink"):
            # the organiser created dst as a duplicate; remove it, keep src
            if dst.exists():
                try:
                    dst.unlink()
                    rev.record("delete", dst, "", note="undo " + op)
                    undone += 1
                    log(f"removed copy: {dst}")
                except OSError as ex:
                    skipped += 1
                    log(f"skip (can't remove {dst}): {ex}")
            else:
                skipped += 1
        elif op == "move":
            if not dst.exists():
                skipped += 1
                log(f"skip (gone): {dst}")
                continue
            if src.exists():
                skipped += 1
                log(f"skip (original path occupied): {src}")
                continue
            try:
                apply_op("move", dst, src)
                rev.record("move", dst, src, note="undo move")
                undone += 1
                log(f"moved back: {dst.name} -> {src}")
            except Exception as ex:
                skipped += 1
                log(f"skip ({ex})")
    rp = rev.save()
    return undone, skipped, str(rp)
