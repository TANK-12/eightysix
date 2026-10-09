"""Read-only views of the backup drive for the Backup hub app.

Everything here looks at the drive; nothing deletes a snapshot or a mirror.
The only writes are restores, which always go to a new folder under
~/Restored/<snapshot>/ and never over an existing file.

- status: drive plugged in or not, free space, every set's snapshots, due or
  not, last-run.json, the systemd units and their journal.
- snapshots: list sets and dated snapshots, browse folders, read files,
  compare a file with the live copy on the laptop, copy back.
- git: the bare mirrors in Vault/git/, read with plumbing commands.

The drive logic (where it is mounted, what counts as a snapshot, when a set
is due) lives in backup.py and is imported, not copied.
"""

from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import backup

TEXT_LIMIT = 1_000_000
DIFF_LIMIT = 600_000
LIST_LIMIT = 2000
MIN_FREE = 5e9  # a restore stops before the laptop has less than this free
LOG_PAGE = 50
NO_DRIVE = (
    "The backup drive is not plugged in. Plug in the Toshiba drive and "
    "press Check again; everything here fills in by itself."
)
EJECTED_SAY = (
    "The drive is ejected and safe to unplug. Unplug it and plug it in again "
    "to use it here."
)
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}
GIT = ["git", "-c", "safe.directory=*", "-c", "core.quotepath=off"]
# Any branch, tag or commit name git allows, but never an option (-x) and no
# spaces or control characters.
REV_RE = re.compile(r"^[^-\s\x00-\x1f\x7f][^\s\x00-\x1f\x7f]*$")
README_RE = re.compile(r"^readme(\.(md|markdown|txt|rst))?$", re.I)


class NoDrive(Exception):
    """The partition this needs is not plugged in."""


class NeedsAdmin(Exception):
    """A root-owned file or folder the app cannot read."""


class BadInput(Exception):
    """A path or name the app refuses (outside the snapshot, a link...)."""


class NotFound(Exception):
    pass


class Busy(Exception):
    """A backup is running, so this action has to wait."""


def run_cmd(cmd: list[str], timeout: float = 30) -> subprocess.CompletedProcess:
    """One place every outside command goes through, so tests can swap it."""
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


# ---------------------------------------------------------------- drive


# Labels this app ejected. Reading a page must not mount them again while the
# drive stays plugged in; they are forgotten once the drive is unplugged.
EJECTED: set[str] = set()


def label_present(label: str) -> bool:
    return (Path("/dev/disk/by-label") / label).exists()


def ejected(cfg: dict) -> bool:
    """True when this app ejected the drive and it is still plugged in."""
    for area in cfg["areas"].values():
        if not label_present(area["label"]):
            EJECTED.discard(area["label"])
    return bool(EJECTED)


def area_mount(cfg: dict, area: str) -> Path | None:
    """Where an area's partition is mounted, or None when it is not plugged in.

    BACKUP_DRIVE_DIR=<dir> makes <dir>/<area> stand in for the drive (tests and
    screenshots without the real drive)."""
    if area not in cfg["areas"]:
        raise BadInput(f"no area called {area}")
    fake = os.environ.get("BACKUP_DRIVE_DIR")
    if fake:
        path = Path(fake) / area
        return path if path.is_dir() else None
    label = cfg["areas"][area]["label"]
    if not label_present(label):
        EJECTED.discard(label)
    try:
        return backup.find_mount(label, cfg["mount_root"], mount=label not in EJECTED)
    except (OSError, subprocess.SubprocessError):
        return None


def need_mount(cfg: dict, area: str) -> Path:
    mount = area_mount(cfg, area)
    if mount is None:
        raise NoDrive(EJECTED_SAY if ejected(cfg) else NO_DRIVE)
    return mount


def unit_names(cfg: dict) -> list[str]:
    names = ["all", *cfg["areas"]]
    return [
        f"forge-backup-{kind}@{n}.service" for kind in ("now", "auto") for n in names
    ]


def units(cfg: dict) -> list[dict]:
    """State of every backup unit, from systemctl show."""
    props = (
        "Id,ActiveState,SubState,Result,ExecMainStartTimestamp,ExecMainExitTimestamp"
    )
    try:
        out = run_cmd(["systemctl", "show", f"--property={props}", *unit_names(cfg)])
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for block in out.stdout.decode(errors="replace").split("\n\n"):
        info = dict(
            line.split("=", 1) for line in block.strip().splitlines() if "=" in line
        )
        if info.get("Id"):
            info["running"] = info.get("ActiveState") in {"active", "activating"}
            found.append(info)
    return found


def journal(lines: int = 40) -> list[str]:
    try:
        out = run_cmd(
            [
                "journalctl",
                "-u",
                "forge-backup-*",
                "-n",
                str(lines),
                "-o",
                "short-iso",
                "--no-pager",
                "-q",
            ]
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return out.stdout.decode(errors="replace").splitlines()[-lines:]


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def all_snapshot_dirs(set_dir: Path) -> list[dict]:
    """Complete snapshots plus unfinished ones (.partial), newest first."""
    try:
        names = [p.name for p in set_dir.iterdir() if p.is_dir()]
    except PermissionError as e:
        raise NeedsAdmin(f"{set_dir} needs admin") from e
    except OSError:
        return []
    found = []
    for name in names:
        stamp = name.removesuffix(".partial")
        when = backup.parse_stamp(stamp)
        if when is not None:
            found.append(
                {
                    "name": name,
                    "when": when.isoformat(sep=" "),
                    "partial": name.endswith(".partial"),
                }
            )
    return sorted(found, key=lambda s: s["name"], reverse=True)


def status(cfg: dict, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now()
    areas = []
    for name, area in cfg["areas"].items():
        mount = area_mount(cfg, name)
        info: dict = {
            "name": name,
            "label": area["label"],
            "about": area["about"],
            "every_hours": area["every_hours"],
            "keep": area["keep"],
            "plugged": mount is not None,
        }
        if mount is not None:
            usage = shutil.disk_usage(mount)
            set_dirs = [mount / s["name"] for s in area["sets"]]
            try:
                due: bool | None = backup.is_due(set_dirs, area["every_hours"], now)
            except PermissionError:
                due = None
            info |= {
                "mount": str(mount),
                "free_gb": round(usage.free / 1e9, 1),
                "used_gb": round(usage.used / 1e9, 1),
                "total_gb": round(usage.total / 1e9, 1),
                "due": due,
                "last_run": read_json(mount / "last-run.json"),
                "sets": [set_status(d, now, area["every_hours"]) for d in set_dirs],
            }
            git_dir = mount / "git"
            if area.get("git"):
                info["mirrors"] = (
                    sorted(p.name for p in git_dir.glob("*.git"))
                    if git_dir.is_dir()
                    else []
                )
        areas.append(info)
    found_units = units(cfg)
    plugged = any(a["plugged"] for a in areas)
    return {
        "plugged": plugged,
        "message": (None if plugged else EJECTED_SAY if ejected(cfg) else NO_DRIVE),
        "areas": areas,
        "units": found_units,
        "running": any(u["running"] for u in found_units),
        "status_file": read_json(Path(cfg["status_file"])),
        "now": now.isoformat(sep=" ", timespec="seconds"),
    }


def set_status(set_dir: Path, now: dt.datetime, every_hours: float = 24) -> dict:
    try:
        snaps = backup.snapshots(set_dir)
        due = backup.is_due([set_dir], every_hours, now)
        partial = sorted(set_dir.glob("*.partial")) if set_dir.is_dir() else []
    except PermissionError:
        return {
            "name": set_dir.name,
            "count": None,
            "unfinished": [],
            "newest": None,
            "age_hours": None,
            "due": None,
            "needs_admin": True,
        }
    info: dict = {
        "name": set_dir.name,
        "count": len(snaps),
        "unfinished": [p.name for p in partial],
        "newest": None,
        "age_hours": None,
        "due": due,
    }
    if snaps:
        when = backup.stamp_time(snaps[-1])
        info["newest"] = snaps[-1].name
        info["age_hours"] = round((now - when).total_seconds() / 3600, 1)
    return info


def progress(cfg: dict) -> dict:
    """The cheap part of status, polled while a backup runs."""
    used = {}
    for name in cfg["areas"]:
        mount = area_mount(cfg, name)
        if mount is not None:
            used[name] = round(shutil.disk_usage(mount).used / 1e9, 1)
    found = units(cfg)
    return {
        "running": any(u["running"] for u in found),
        "units": found,
        "used_gb": used,
        "journal": journal(),
    }


def start_backup(cfg: dict, area: str) -> str:
    if area != "all" and area not in cfg["areas"]:
        raise BadInput(f"no area called {area}")
    if any(u["running"] for u in units(cfg)):
        raise Busy("A backup is already running; it carries on by itself.")
    unit = f"forge-backup-now@{area}.service"
    out = run_cmd(["systemctl", "start", "--no-block", unit])
    if out.returncode != 0:
        raise BadInput(
            out.stderr.decode(errors="replace").strip() or f"could not start {unit}"
        )
    return unit


def eject(cfg: dict) -> str:
    if any(u["running"] for u in units(cfg)):
        raise Busy("A backup is running. Eject when it has finished.")
    with JOBS_LOCK:
        copying = any(j["state"] == "copying" for j in JOBS.values())
    if copying:
        raise Busy(
            "A copy to ~/Restored is still reading the drive. Eject when it is done."
        )
    out = run_cmd([sys.executable, str(backup.HERE / "backup.py"), "eject"], 120)
    text = (out.stdout + out.stderr).decode(errors="replace").strip()
    if out.returncode != 0:
        raise BadInput(text or "The drive could not be ejected.")
    EJECTED.update(a["label"] for a in cfg["areas"].values())
    return text or "Ejected. The drive can be unplugged."


# ---------------------------------------------------------------- snapshots


def set_spec(cfg: dict, area: str, set_name: str) -> dict:
    for spec in cfg["areas"].get(area, {}).get("sets", []):
        if spec["name"] == set_name:
            return spec
    raise BadInput(f"no set called {set_name} in {area}")


def list_sets(cfg: dict, area: str) -> list[dict]:
    mount = need_mount(cfg, area)
    found = []
    for spec in cfg["areas"][area]["sets"]:
        info = {"name": spec["name"], "items": [i["to"] for i in spec["items"]]}
        try:
            info["snapshots"] = all_snapshot_dirs(mount / spec["name"])
        except NeedsAdmin:
            info |= {"snapshots": [], "needs_admin": True}
        found.append(info)
    return found


def snap_root(cfg: dict, area: str, set_name: str, snap: str) -> Path:
    set_spec(cfg, area, set_name)
    if not backup.STAMP_RE.match(snap.removesuffix(".partial")):
        raise BadInput(f"{snap} is not a snapshot name")
    if backup.parse_stamp(snap.removesuffix(".partial")) is None:
        raise BadInput(f"{snap} is not a snapshot name")
    root = need_mount(cfg, area) / set_name / snap
    if not root.is_dir():
        raise NotFound(f"snapshot {snap} is not on the drive")
    return root


def rel_parts(rel: str) -> list[str]:
    parts = [p for p in rel.strip("/").split("/") if p]
    for p in parts:
        if p in {".", ".."} or "\0" in p:
            raise BadInput("that path is not allowed")
    return parts


def safe_path(root: Path, rel: str) -> Path:
    """root/rel without following a link on the way: a link in a snapshot
    (an absolute one especially) would lead onto the laptop instead."""
    path = root
    parts = rel_parts(rel)
    for i, part in enumerate(parts):
        path = path / part
        try:
            st = path.lstat()
        except PermissionError as e:
            raise NeedsAdmin(f"{'/'.join(parts[:i])} needs admin") from e
        except FileNotFoundError as e:
            raise NotFound(f"{rel} is not in this snapshot") from e
        if stat.S_ISLNK(st.st_mode) and i < len(parts) - 1:
            raise BadInput(f"{'/'.join(parts[: i + 1])} is a link; open its target")
    return path


def shown_name(name: str) -> tuple[str, bool]:
    """A file name as text, and whether the page can open it by that name.

    A name that is not valid UTF-8 comes from os.scandir with its odd bytes as
    surrogates, which JSON cannot carry: show them as \ufffd and do not offer
    to open it (the name sent back would not match the file)."""
    try:
        name.encode("utf-8")
        return name, True
    except UnicodeEncodeError:
        raw = name.encode("utf-8", "surrogateescape")
        return raw.decode("utf-8", "replace"), False


def entry_info(path: Path, st: os.stat_result) -> dict:
    mode = st.st_mode
    kind = (
        "link"
        if stat.S_ISLNK(mode)
        else "dir" if stat.S_ISDIR(mode) else "file" if stat.S_ISREG(mode) else "other"
    )
    name, openable = shown_name(path.name)
    try:
        mtime = dt.datetime.fromtimestamp(st.st_mtime).isoformat(
            sep=" ", timespec="minutes"
        )
    except (OverflowError, OSError, ValueError):
        mtime = ""
    info = {
        "name": name,
        "openable": openable,
        "type": kind,
        "size": st.st_size if kind == "file" else None,
        "mtime": mtime,
        "readable": True,
    }
    if kind == "dir":
        info["readable"] = os.access(path, os.R_OK | os.X_OK)
    elif kind == "file":
        info["readable"] = os.access(path, os.R_OK)
    elif kind == "link":
        try:
            info["target"] = shown_name(os.readlink(path))[0]
        except OSError:
            info["target"] = "?"
    return info


def list_dir(
    cfg: dict, area: str, set_name: str, snap: str, rel: str, offset: int = 0
) -> dict:
    """One folder, folders first then by name, LIST_LIMIT entries from offset."""
    root = snap_root(cfg, area, set_name, snap)
    path = safe_path(root, rel)
    if not path.is_dir() or path.is_symlink():
        raise BadInput(f"{rel} is not a folder")
    entries = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    name, openable = shown_name(entry.name)
                    entries.append(
                        {
                            "name": name,
                            "openable": openable,
                            "type": "other",
                            "size": None,
                            "mtime": "",
                            "readable": False,
                        }
                    )
                    continue
                entries.append(entry_info(Path(entry.path), st))
    except PermissionError as e:
        raise NeedsAdmin(f"{rel or 'this folder'} needs admin") from e
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower(), e["name"]))
    offset = max(0, offset)
    page = entries[offset : offset + LIST_LIMIT]
    return {
        "path": "/".join(rel_parts(rel)),
        "entries": page,
        "offset": offset,
        "total": len(entries),
        "more": offset + len(page) < len(entries),
        "live": live_path(cfg, area, set_name, rel),
    }


def is_binary(data: bytes) -> bool:
    return b"\0" in data[:8192]


def read_bytes(path: Path, limit: int) -> tuple[bytes, int]:
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            return f.read(limit), size
    except PermissionError as e:
        raise NeedsAdmin(f"{path.name} needs admin") from e


def text_view(data: bytes, size: int, name: str) -> dict:
    suffix = Path(name).suffix.lower()
    view: dict = {"size": size, "truncated": size > len(data)}
    if suffix in IMAGE_TYPES:
        view["kind"] = "image"
    elif is_binary(data):
        view["kind"] = "binary"
    else:
        view["kind"] = "text"
        view["text"] = data.decode("utf-8", errors="replace")
    return view


def read_file(cfg: dict, area: str, set_name: str, snap: str, rel: str) -> dict:
    path = safe_path(snap_root(cfg, area, set_name, snap), rel)
    if path.is_symlink():
        return {"kind": "link", "target": shown_name(os.readlink(path))[0], "size": 0}
    if not path.is_file():
        raise BadInput(f"{rel} is not a file")
    data, size = read_bytes(path, TEXT_LIMIT)
    view = text_view(data, size, path.name)
    view["live"] = live_path(cfg, area, set_name, rel)
    return view


def raw_file(cfg: dict, area: str, set_name: str, snap: str, rel: str) -> Path:
    path = safe_path(snap_root(cfg, area, set_name, snap), rel)
    if path.is_symlink() or not path.is_file():
        raise BadInput(f"{rel} is not a file")
    if not os.access(path, os.R_OK):
        raise NeedsAdmin(f"{path.name} needs admin")
    return path


def live_path(cfg: dict, area: str, set_name: str, rel: str) -> str | None:
    """Where this snapshot path lives on the laptop, from the set's items."""
    parts = rel_parts(rel)
    if not parts:
        return None
    for item in set_spec(cfg, area, set_name)["items"]:
        to = rel_parts(item["to"])
        if parts[: len(to)] == to:
            rest = parts[len(to) :]
            return str(Path(item["from"]).joinpath(*rest))
    return None


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def compare(cfg: dict, area: str, set_name: str, snap: str, rel: str) -> dict:
    """The snapshot copy against the live one on the laptop."""
    snap_path = safe_path(snap_root(cfg, area, set_name, snap), rel)
    live = live_path(cfg, area, set_name, rel)
    if live is None:
        raise BadInput("this path has no live copy on the laptop")
    live_p = Path(live)
    out: dict = {"live": live}
    if snap_path.is_symlink() or not snap_path.is_file():
        if snap_path.is_dir() and not snap_path.is_symlink():
            return out | compare_dirs(snap_path, live_p)
        raise BadInput("only files and folders can be compared")
    try:
        live_p.stat()
    except PermissionError:
        return out | {"state": "needs_admin", "say": "The laptop copy needs admin."}
    except OSError:
        return out | {"state": "missing", "say": "Not on the laptop any more."}
    if not live_p.is_file():
        return out | {"state": "different", "say": "On the laptop it is not a file."}
    if not os.access(live_p, os.R_OK):
        return out | {"state": "needs_admin", "say": "The laptop copy needs admin."}
    if not os.access(snap_path, os.R_OK):
        raise NeedsAdmin(f"{snap_path.name} needs admin")
    a_size, b_size = snap_path.stat().st_size, live_p.stat().st_size
    out |= {"snap_size": a_size, "live_size": b_size}
    if a_size == b_size and file_digest(snap_path) == file_digest(live_p):
        return out | {"state": "same", "say": "The laptop copy is identical."}
    a, _ = read_bytes(snap_path, TEXT_LIMIT)
    b, _ = read_bytes(live_p, TEXT_LIMIT)
    out |= {"state": "different", "say": "The laptop copy has changed."}
    if is_binary(a) or is_binary(b) or max(a_size, b_size) > TEXT_LIMIT:
        return out | {"diff": None}
    diff = difflib.unified_diff(
        a.decode("utf-8", "replace").splitlines(),
        b.decode("utf-8", "replace").splitlines(),
        "snapshot",
        "laptop",
        lineterm="",
    )
    lines = list(diff)
    return out | {"diff": "\n".join(lines[:4000]), "truncated": len(lines) > 4000}


def compare_dirs(snap_dir: Path, live_dir: Path) -> dict:
    """One level: names only in the snapshot, only on the laptop, or changed."""
    if not live_dir.is_dir():
        return {"state": "missing", "say": "This folder is not on the laptop any more."}
    try:
        snap = {shown_name(e.name)[0]: e for e in os.scandir(snap_dir)}
    except PermissionError as e:
        raise NeedsAdmin(f"{snap_dir.name} needs admin") from e
    try:
        live = {shown_name(e.name)[0]: e for e in os.scandir(live_dir)}
    except PermissionError:
        return {"state": "needs_admin", "say": "The laptop folder needs admin."}

    def size(e: os.DirEntry) -> int | None:
        try:
            return e.stat(follow_symlinks=False).st_size if e.is_file() else None
        except OSError:
            return None

    changed = [
        n for n in sorted(snap.keys() & live.keys()) if size(snap[n]) != size(live[n])
    ]
    only_snap = sorted(snap.keys() - live.keys())
    only_live = sorted(live.keys() - snap.keys())
    same = not (changed or only_snap or only_live)
    return {
        "state": "same" if same else "different",
        "say": (
            "Same names and sizes as on the laptop."
            if same
            else "The laptop folder differs from this snapshot."
        ),
        "only_snapshot": only_snap[:500],
        "only_laptop": only_live[:500],
        "changed": changed[:500],
    }


# ---------------------------------------------------------------- restore

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def restored_home() -> Path:
    return Path(os.environ.get("BACKUP_RESTORE_DIR") or Path.home() / "Restored")


def fresh_dest(dest: Path) -> Path:
    """dest, or dest-2, dest-3... whichever does not exist yet."""
    if not dest.exists() and not dest.is_symlink():
        return dest
    stem, suffix = dest.stem, dest.suffix
    n = 2
    while True:
        cand = dest.with_name(f"{stem}-{n}{suffix}")
        if not cand.exists() and not cand.is_symlink():
            return cand
        n += 1


class NoSpace(Exception):
    """The laptop would drop below MIN_FREE; not an OSError, so copytree stops."""


RESTORE_LOCK = threading.Lock()


def no_links_between(top: Path, dest: Path) -> None:
    """Refuse when a folder on the way from top to dest is a link: writing
    through it could land outside ~/Restored."""
    here = top
    for part in dest.relative_to(top).parts[:-1]:
        here = here / part
        if here.is_symlink():
            raise BadInput(f"{here} is a link, so nothing is copied through it")


def check_space(dest_dir: Path, size: int) -> None:
    free = shutil.disk_usage(dest_dir).free
    if free - size < MIN_FREE:
        raise NoSpace(
            f"Not enough free space on the laptop: {free / 1e9:.1f} GB free, and "
            f"a restore always leaves {MIN_FREE / 1e9:.0f} GB. Free some space "
            "or copy a smaller folder."
        )


def restore(cfg: dict, area: str, set_name: str, snap: str, rel: str) -> dict:
    """Copy one file or folder out of a snapshot into ~/Restored/<snap>/<set>/<rel>.

    Never writes over anything: an existing target gets a -2, -3... name.
    Folders copy in a background thread; poll job(id)."""
    parts = rel_parts(rel)
    if not parts:
        raise BadInput("pick a file or folder inside the snapshot")
    src = safe_path(snap_root(cfg, area, set_name, snap), rel)
    top = restored_home()
    want = top.joinpath(snap.removesuffix(".partial"), set_name, *parts)
    no_links_between(top, want)
    is_dir = src.is_dir() and not src.is_symlink()
    readable = src.is_symlink() or os.access(
        src, os.R_OK | os.X_OK if is_dir else os.R_OK
    )
    if not readable:
        raise NeedsAdmin(f"{src.name} needs admin")
    job = {
        "id": uuid.uuid4().hex[:12],
        "src": str(src),
        "dest": "",
        "state": "copying",
        "files": 0,
        "bytes": 0,
        "skipped": [],
    }
    try:
        want.parent.mkdir(parents=True, exist_ok=True)
        with RESTORE_LOCK:
            dest = fresh_dest(want)
            job["dest"] = str(dest)
            if is_dir:
                dest.mkdir()
            else:
                if not src.is_symlink():
                    check_space(dest.parent, src.stat().st_size)
                shutil.copy2(src, dest, follow_symlinks=False)
                job |= {"state": "done", "files": 1, "bytes": dest.lstat().st_size}
    except NoSpace as e:
        raise BadInput(str(e)) from e
    except OSError as e:
        raise BadInput(f"could not copy: {e}") from e
    with JOBS_LOCK:
        JOBS[job["id"]] = job
    if is_dir:
        threading.Thread(target=copy_tree, args=(job, src, dest), daemon=True).start()
    return dict(job)


def copy_tree(job: dict, src: Path, dest: Path) -> None:
    def copy_one(a: str, b: str) -> str:
        if os.path.lexists(b):
            raise FileExistsError(b)
        if not os.path.islink(a):
            check_space(Path(b).parent, os.lstat(a).st_size)
        shutil.copy2(a, b, follow_symlinks=False)
        job["files"] += 1
        job["bytes"] += os.lstat(b).st_size
        return b

    try:
        shutil.copytree(
            src, dest, symlinks=True, copy_function=copy_one, dirs_exist_ok=True
        )
    except shutil.Error as e:
        job["skipped"] = [
            {"path": shown_name(str(err[0]))[0], "why": shown_name(str(err[2]))[0]}
            for err in e.args[0]
        ][:200]
    except NoSpace as e:
        job["state"] = "failed"
        job["error"] = str(e)
        return
    except OSError as e:
        job["state"] = "failed"
        job["error"] = str(e)
        return
    job["state"] = "done"


def get_job(job_id: str) -> dict:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        raise NotFound("no such copy job")
    return dict(job)


# ---------------------------------------------------------------- git


def git_dir(cfg: dict) -> Path:
    for name, area in cfg["areas"].items():
        if area.get("git"):
            return need_mount(cfg, name) / "git"
    raise NotFound("no area keeps git mirrors")


def repo_label(name: str) -> str:
    return name.removesuffix(".git").replace("__", "/")


def git(repo: Path, *args: str, limit: int | None = None) -> bytes:
    try:
        out = run_cmd([*GIT, "--git-dir", str(repo), *args], 60)
    except subprocess.TimeoutExpired as e:
        raise BadInput("git took too long") from e
    if out.returncode != 0:
        msg = out.stderr.decode(errors="replace").strip().splitlines()
        raise NotFound(msg[-1] if msg else "git could not find that")
    return out.stdout if limit is None else out.stdout[:limit]


def repos(cfg: dict) -> list[dict]:
    base = git_dir(cfg)
    if not base.is_dir():
        return []
    if not os.access(base, os.R_OK | os.X_OK):
        raise NeedsAdmin(f"{base} needs admin")
    found = []
    for path in sorted(base.glob("*.git"), key=lambda p: p.name.lower()):
        info: dict = {"name": path.name, "label": repo_label(path.name)}
        try:
            out = git(
                path,
                "for-each-ref",
                "--sort=-committerdate",
                "--format=%(committerdate:iso-strict)%1f%(refname:short)%1f%(subject)",
                "refs/heads",
            ).decode(errors="replace")
            heads = [line.split("\x1f") for line in out.splitlines() if line]
            info["branches"] = len(heads)
            if heads:
                info["last_date"], info["last_branch"], info["last_subject"] = heads[0]
            info["head"] = head_branch(path)
        except (NotFound, BadInput) as e:
            info["error"] = str(e)
        found.append(info)
    return found


def repo_path(cfg: dict, name: str) -> Path:
    if "/" in name or not name.endswith(".git") or name.startswith("."):
        raise BadInput("not a mirror name")
    path = git_dir(cfg) / name
    if not path.is_dir():
        raise NotFound(f"no mirror called {name}")
    return path


def head_branch(repo: Path) -> str | None:
    try:
        return (
            git(repo, "symbolic-ref", "--short", "-q", "HEAD")
            .decode(errors="replace")
            .strip()
            or None
        )
    except NotFound:
        return None


def resolve(repo: Path, rev: str | None) -> str:
    rev = rev or head_branch(repo) or "HEAD"
    if not REV_RE.match(rev) or ".." in rev:
        raise BadInput(f"{rev} is not a branch, tag or commit")
    return (
        git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
        .decode()
        .strip()
    )


def refs(repo: Path) -> dict:
    out = git(
        repo,
        "for-each-ref",
        "--sort=-committerdate",
        "--format=%(refname)%1f%(objectname:short)%1f%(committerdate:iso-strict)"
        "%1f%(subject)%1f%(objecttype)%1f%(*objecttype)",
        "refs/heads",
        "refs/tags",
    ).decode(errors="replace")
    branches, tags = [], []
    for line in out.splitlines():
        ref, sha, date, subject, typ, peeled = (line.split("\x1f") + [""] * 5)[:6]
        if "commit" not in (typ, peeled):
            continue  # a tag on a tree or a blob: nothing to browse
        row = {"sha": sha, "date": date, "subject": subject}
        if ref.startswith("refs/heads/"):
            branches.append(row | {"name": ref.removeprefix("refs/heads/")})
        elif ref.startswith("refs/tags/"):
            tags.append(row | {"name": ref.removeprefix("refs/tags/")})
    return {"head": head_branch(repo), "branches": branches, "tags": tags}


def log(repo: Path, rev: str | None, skip: int = 0, path: str = "") -> dict:
    sha = resolve(repo, rev)
    args = [
        "log",
        f"--skip={max(0, skip)}",
        f"-n{LOG_PAGE}",
        "--format=%H%x1f%h%x1f%an%x1f%aI%x1f%s%x1e",
        sha,
    ]
    count_args = ["rev-list", "--count", sha]
    if path:
        clean = "/".join(rel_parts(path))
        args += ["--", clean]
        count_args += ["--", clean]
    commits = []
    for rec in git(repo, *args).decode(errors="replace").split("\x1e"):
        fields = rec.strip("\n").split("\x1f")
        if len(fields) == 5:
            full, short, author, date, subject = fields
            commits.append(
                {
                    "sha": full,
                    "short": short,
                    "author": author,
                    "date": date,
                    "subject": subject,
                }
            )
    total = int(git(repo, *count_args).decode().strip() or 0)
    return {"rev": sha, "commits": commits, "skip": skip, "total": total}


def commit(repo: Path, rev: str) -> dict:
    sha = resolve(repo, rev)
    head = git(
        repo, "show", "-s", "--format=%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%B", sha
    ).decode(errors="replace")
    full, parents, author, email, date, message = (head.split("\x1f") + [""] * 6)[:6]
    raw = git(
        repo,
        "show",
        "--format=",
        "--patch",
        "--diff-merges=first-parent",
        "-M",
        "--no-color",
        "--no-ext-diff",
        sha,
        limit=DIFF_LIMIT + 1,
    )
    stats = git(
        repo,
        "show",
        "--format=",
        "--numstat",
        "--diff-merges=first-parent",
        "-M",
        "--no-color",
        sha,
    ).decode(errors="replace")
    files = []
    for line in stats.splitlines():
        bits = line.split("\t", 2)
        if len(bits) == 3:
            added, removed, name = bits
            files.append({"name": name, "added": added, "removed": removed})
    return {
        "sha": full.strip(),
        "parents": parents.split(),
        "author": author,
        "email": email,
        "date": date,
        "message": message.strip(),
        "files": files,
        "diff": raw[:DIFF_LIMIT].decode("utf-8", errors="replace"),
        "truncated": len(raw) > DIFF_LIMIT,
    }


def tree(repo: Path, rev: str | None, path: str = "") -> dict:
    sha = resolve(repo, rev)
    clean = "/".join(rel_parts(path))
    spec = f"{sha}:{clean}"
    kind = git(repo, "cat-file", "-t", spec).decode().strip()
    if kind != "tree":
        raise BadInput(f"{clean} is not a folder")
    out = git(repo, "ls-tree", "-z", "-l", spec)
    entries = []
    for raw in out.split(b"\0"):
        if b"\t" not in raw:
            continue
        meta_b, name_b = raw.split(b"\t", 1)
        mode, typ, _obj, size = meta_b.decode().split()
        try:
            name, openable = name_b.decode("utf-8"), True
        except UnicodeDecodeError:
            name, openable = name_b.decode("utf-8", "replace"), False
        entries.append(
            {
                "name": name,
                "openable": openable,
                "type": {"tree": "dir", "blob": "file", "commit": "submodule"}.get(
                    typ, typ
                ),
                "link": mode == "120000",
                "size": int(size) if size.isdigit() else None,
            }
        )
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
    readme = next(
        (
            e["name"]
            for e in entries
            if e["type"] == "file" and README_RE.match(e["name"])
        ),
        None,
    )
    return {"rev": sha, "path": clean, "entries": entries, "readme": readme}


def blob(repo: Path, rev: str | None, path: str) -> dict:
    sha = resolve(repo, rev)
    clean = "/".join(rel_parts(path))
    if not clean:
        raise BadInput("pick a file")
    spec = f"{sha}:{clean}"
    if git(repo, "cat-file", "-t", spec).decode().strip() != "blob":
        raise BadInput(f"{clean} is not a file")
    size = int(git(repo, "cat-file", "-s", spec).decode().strip())
    data = git(repo, "cat-file", "blob", spec, limit=TEXT_LIMIT)
    return {"rev": sha, "path": clean} | text_view(data, size, clean)


def blob_raw(repo: Path, rev: str | None, path: str) -> tuple[bytes, str]:
    sha = resolve(repo, rev)
    clean = "/".join(rel_parts(path))
    media = IMAGE_TYPES.get(Path(clean).suffix.lower())
    if media is None:
        raise BadInput("only pictures are served raw")
    return git(repo, "cat-file", "blob", f"{sha}:{clean}"), media


def help_docs() -> dict:
    here = backup.HERE
    return {
        name: (here / f"{name}.md").read_text()
        for name in ("README", "RESTORE")
        if (here / f"{name}.md").exists()
    }
