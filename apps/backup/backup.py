#!/usr/bin/env python3
"""Forge backup: snapshots onto the external drive.

Two areas, both described in sets.json:
- rescue: the whole system, so a dead laptop can be rebuilt exactly.
- vault: Claude and Forge work with longer history, plus offline git mirrors.

Every snapshot is a dated folder. Files that did not change since the last
snapshot are hard links to it, so each extra snapshot only costs the changes.
A snapshot is written as <stamp>.partial and renamed when rsync finishes, so a
folder without .partial is always complete.

Run as root (the systemd unit does this) to read every file. As a normal user,
`now` asks systemd to start the root unit, and `status` only reads.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "sets.json"
STAMP = "%Y-%m-%d_%H%M%S"
STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")
# rsync exit 24 means some files vanished while copying (normal on a live system).
RSYNC_OK = {0, 24}


def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(path.read_text())


# ---------------------------------------------------------------- drive


def find_mount(label: str, mount_root: str, mount: bool = True) -> Path | None:
    """Where the partition with this label is mounted, mounting it if needed
    (unless mount is False)."""
    dev = Path("/dev/disk/by-label") / label
    if not dev.exists():
        return None
    real = str(dev.resolve())
    out = subprocess.run(
        ["findmnt", "-rno", "TARGET", real], capture_output=True, text=True
    ).stdout.splitlines()
    if out:
        return Path(out[0])
    if not mount:
        return None
    if os.geteuid() == 0:
        target = Path(mount_root) / label.lower()
        target.mkdir(parents=True, exist_ok=True)
        subprocess.run(["mount", real, str(target)], check=True)
        MOUNTED_HERE.append(target)
        return target
    subprocess.run(["udisksctl", "mount", "-b", real], capture_output=True)
    out = subprocess.run(
        ["findmnt", "-rno", "TARGET", real], capture_output=True, text=True
    ).stdout.splitlines()
    return Path(out[0]) if out else None


# Partitions this process mounted as root; run() unmounts them again at the end,
# so the drive is not left root-mounted where the user cannot eject it.
MOUNTED_HERE: list[Path] = []


def unmount_ours() -> None:
    subprocess.run(["sync"])
    while MOUNTED_HERE:
        target = MOUNTED_HERE.pop()
        if subprocess.run(["umount", str(target)], capture_output=True).returncode:
            log(f"left {target} mounted (in use)")


def still_mounted(cfg: dict) -> list[str]:
    """Where the drive's partitions are still mounted."""
    found = []
    for area in cfg["areas"].values():
        dev = Path("/dev/disk/by-label") / area["label"]
        if dev.exists():
            found += subprocess.run(
                ["findmnt", "-rno", "TARGET", str(dev.resolve())],
                capture_output=True,
                text=True,
            ).stdout.splitlines()
    return found


def eject(cfg: dict) -> int:
    """Unmount both partitions and power the drive off; say plainly if not."""
    subprocess.run(["sync"])
    devs = [Path("/dev/disk/by-label") / a["label"] for a in cfg["areas"].values()]
    for dev in devs:
        if dev.exists():
            subprocess.run(
                ["udisksctl", "unmount", "-b", str(dev.resolve())], capture_output=True
            )
            subprocess.run(["umount", str(dev.resolve())], capture_output=True)
    left = still_mounted(cfg)
    if left:
        steps = " && ".join(f"sudo umount {m}" for m in left)
        print(
            f"The drive is still mounted at {', '.join(left)}. The backup mounts it "
            f"as root, and a user cannot unmount that. Run this in a terminal: "
            f"{steps}, then press Eject again. If it says busy, close any "
            "window showing files on the drive first."
        )
        return 1
    present = [d for d in devs if d.exists()]
    if present:
        disk = "/dev/" + Path(present[0].resolve()).name.rstrip("0123456789")
        out = subprocess.run(
            ["udisksctl", "power-off", "-b", disk], capture_output=True, text=True
        )
        if out.returncode:
            print(
                "Both parts are unmounted, so it is safe to unplug, but the drive "
                f"did not power down: {out.stderr.strip()}"
            )
            return 0
    print("Ejected. The drive can be unplugged.")
    return 0


def free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1e9


# ---------------------------------------------------------------- snapshots


def parse_stamp(name: str) -> dt.datetime | None:
    """The time in a snapshot name, or None when it is not one (2026-13-45...)."""
    if not STAMP_RE.match(name):
        return None
    try:
        return dt.datetime.strptime(name, STAMP)
    except ValueError:
        return None


def snapshots(set_dir: Path) -> list[Path]:
    """Complete snapshots of one set, oldest first."""
    if not set_dir.is_dir():
        return []
    return sorted(
        p for p in set_dir.iterdir() if p.is_dir() and parse_stamp(p.name) is not None
    )


def stamp_time(snap: Path) -> dt.datetime:
    return dt.datetime.strptime(snap.name, STAMP)


def rsync_item(item: dict, snap: Path, prev: Path | None, flags: list[str]) -> int:
    src = Path(item["from"])
    if not src.exists():
        log(f"skip {src}: not found")
        return 0
    cmd = ["rsync", *flags, "--delete", "--delete-excluded"]
    for pattern in item.get("exclude", []):
        cmd.append(f"--exclude={pattern}")
    if src.is_dir():
        dest = snap / item["to"]
        dest.mkdir(parents=True, exist_ok=True)
        if prev is not None and (prev / item["to"]).is_dir():
            cmd.append(f"--link-dest={prev / item['to']}")
        cmd += [f"{src}/", f"{dest}/"]
    else:
        if prev is not None and (prev / item["to"]).exists():
            cmd.append(f"--link-dest={prev}")
        cmd += [str(src), str(snap / item["to"])]
    return subprocess.run(cmd).returncode


def take_snapshot(
    set_dir: Path, items: list[dict], flags: list[str], now: dt.datetime
) -> tuple[Path | None, list[int]]:
    """One new snapshot of a set. Returns (snapshot or None on failure, rsync codes)."""
    set_dir.mkdir(parents=True, exist_ok=True)
    name = now.strftime(STAMP)
    partial = set_dir / f"{name}.partial"
    # A run that died earlier left a .partial: reuse it so rsync only fills the gaps.
    leftovers = sorted(set_dir.glob("*.partial"))
    if leftovers:
        leftovers[-1].rename(partial)
        for extra in leftovers[:-1]:
            remove_snapshot(set_dir, extra)
    partial.mkdir(exist_ok=True)
    done = snapshots(set_dir)
    prev = done[-1] if done else None
    codes = [rsync_item(item, partial, prev, flags) for item in items]
    if all(c in RSYNC_OK for c in codes):
        final = set_dir / name
        partial.rename(final)
        return final, codes
    return None, codes


def remove_snapshot(set_dir: Path, snap: Path) -> None:
    """Delete one of our own snapshot folders, refusing anything else."""
    name = snap.name.removesuffix(".partial")
    if snap.parent != set_dir or not STAMP_RE.match(name):
        raise ValueError(f"refusing to remove {snap}")
    shutil.rmtree(snap)


def prune(set_dir: Path, keep: int) -> list[Path]:
    """Drop the oldest snapshots past `keep`. The newest one is never dropped."""
    snaps = snapshots(set_dir)
    gone = snaps[: max(0, len(snaps) - max(keep, 1))]
    for snap in gone:
        remove_snapshot(set_dir, snap)
    return gone


def make_room(mount: Path, set_dirs: list[Path], min_free: float) -> list[Path]:
    """Drop oldest snapshots (from the set with the most) until min_free GB is free."""
    gone: list[Path] = []
    while free_gb(mount) < min_free:
        candidates = [d for d in set_dirs if len(snapshots(d)) > 1]
        if not candidates:
            break
        fullest = max(candidates, key=lambda d: len(snapshots(d)))
        oldest = snapshots(fullest)[0]
        remove_snapshot(fullest, oldest)
        gone.append(oldest)
    return gone


def is_due(set_dirs: list[Path], every_hours: float, now: dt.datetime) -> bool:
    newest = [snapshots(d)[-1] for d in set_dirs if snapshots(d)]
    if len(newest) < len(set_dirs):
        return True
    oldest_newest = min(stamp_time(s) for s in newest)
    return now - oldest_newest >= dt.timedelta(hours=every_hours)


# ---------------------------------------------------------------- git


def mirror_name(repo: Path) -> str:
    parts = repo.relative_to(repo.anchor).parts
    if len(parts) > 2 and parts[0] == "home":
        parts = parts[2:]
    return "__".join(parts) + ".git"


def mirror_repo(repo: Path, git_dir: Path) -> bool:
    """Create or refresh a bare mirror (every branch and tag) of a local repo."""
    if not (repo / ".git").exists():
        log(f"skip git {repo}: not a repo")
        return False
    dest = git_dir / mirror_name(repo)
    base = ["git", "-c", "safe.directory=*"]
    if dest.exists():
        cmd = [*base, "--git-dir", str(dest), "remote", "update", "--prune"]
    else:
        git_dir.mkdir(parents=True, exist_ok=True)
        cmd = [*base, "clone", "--mirror", "--quiet", str(repo), str(dest)]
    ok = subprocess.run(cmd, capture_output=True).returncode == 0
    if ok and os.geteuid() == 0:
        st = repo.stat()
        subprocess.run(["chown", "-R", f"{st.st_uid}:{st.st_gid}", str(dest)])
    return ok


def build_clean(git_dir: Path) -> dict:
    """The clean copies of clean.json (no secrets, personal data or models),
    owned like the folder they copy so publish can run as that user."""
    import clean

    out = {}
    for copy in clean.load_rules()["copies"]:
        try:
            res = clean.build(copy, git_dir)
            out[copy["name"]] = {"ok": True, **res}
            log(f"clean {copy['name']}: {res['kept']} kept, {res['left_out']} left out")
        except (clean.Unsafe, RuntimeError, OSError) as e:
            out[copy["name"]] = {"ok": False, "error": str(e)[:500]}
            log(f"clean {copy['name']}: failed: {e}")
        repo = git_dir / copy["name"]
        if os.geteuid() == 0 and repo.exists():
            st = Path(copy["items"][0]["from"]).stat()
            subprocess.run(["chown", "-R", f"{st.st_uid}:{st.st_gid}", str(repo)])
    return out


def clean_command(cfg: dict, cmd: str) -> int:
    """publish: check the clean copy's whole history, then push it.
    scan: only the check, printing what was found (names, never values)."""
    import clean

    area = next((a for a in cfg["areas"].values() if a.get("clean")), None)
    mount = find_mount(area["label"], cfg["mount_root"]) if area else None
    if mount is None:
        print("The Vault drive is not plugged in.")
        return 1
    rules = clean.load_rules()
    code = 0
    for copy in rules["copies"]:
        repo = mount / "git" / copy["name"]
        try:
            if cmd == "publish":
                print(clean.publish(copy, mount / "git", rules))
                continue
            head = clean.rev(repo, f"refs/heads/{copy.get('branch', 'main')}")
            if not head:
                print(
                    f"{copy['name']}: no clean copy yet (run: forge-backup now vault)"
                )
                code = 1
                continue
            bad = clean.scan_repo(repo, [head], clean.Checker(rules))
            for path, why in sorted(bad.items()):
                print(f"  {path}: {why}")
            print(f"{copy['name']}: {'clean' if not bad else f'{len(bad)} problems'}")
            code = code or (1 if bad else 0)
        except (clean.Unsafe, RuntimeError) as e:
            print(f"{copy['name']}: {e}")
            code = 1
    return code


# ---------------------------------------------------------------- runs


def run_area(name: str, area: dict, mount: Path, force: bool, now: dt.datetime) -> dict:
    set_dirs = [mount / s["name"] for s in area["sets"]]
    result: dict = {"area": name, "started": now.isoformat(timespec="seconds")}
    if not force and not is_due(set_dirs, area["every_hours"], now):
        result["skipped"] = "not due"
        log(f"{name}: not due yet")
        return result
    t0 = time.monotonic()
    result["pruned"] = [
        str(p) for d in set_dirs for p in prune(d, area["keep"] - 1)
    ] + [str(p) for p in make_room(mount, set_dirs, area["min_free_gb"])]
    result["sets"] = {}
    for spec, set_dir in zip(area["sets"], set_dirs):
        log(f"{name}/{spec['name']}: copying")
        snap, codes = take_snapshot(set_dir, spec["items"], area["rsync"], now)
        result["sets"][spec["name"]] = {
            "ok": snap is not None,
            "snapshot": str(snap) if snap else None,
            "rsync_codes": codes,
        }
        log(f"{name}/{spec['name']}: {'done' if snap else 'failed'} {codes}")
    if area.get("git"):
        result["git"] = {
            repo: mirror_repo(Path(repo), mount / "git") for repo in area["git"]
        }
    if area.get("clean"):
        result["clean"] = build_clean(mount / "git")
    result["ok"] = (
        all(s["ok"] for s in result["sets"].values())
        and all(result.get("git", {}).values())
        and all(c["ok"] for c in result.get("clean", {}).values())
    )
    result["seconds"] = round(time.monotonic() - t0)
    result["free_gb"] = round(free_gb(mount), 1)
    (mount / "last-run.json").write_text(json.dumps(result, indent=2))
    copy_tool(mount)
    return result


def copy_tool(mount: Path) -> None:
    """Keep this program and its guides on the drive, so a dead laptop is no obstacle."""
    shutil.copytree(
        HERE,
        mount / "forge-backup-tool",
        ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache"),
        dirs_exist_ok=True,
    )


def run(cfg: dict, which: list[str], force: bool) -> int:
    lock = open(cfg["lock"], "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("another backup is already running")
        return 0
    now = dt.datetime.now().replace(microsecond=0)
    results = {}
    for name in which:
        area = cfg["areas"][name]
        mount = find_mount(area["label"], cfg["mount_root"])
        if mount is None:
            log(f"{name}: drive '{area['label']}' not plugged in")
            results[name] = {"area": name, "skipped": "drive missing"}
            continue
        results[name] = run_area(name, area, mount, force, now)
    status = Path(cfg["status_file"])
    try:
        status.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(status.read_text()) if status.exists() else {}
        old.update(results)
        status.write_text(json.dumps(old, indent=2))
    except OSError:
        pass
    unmount_ours()
    failed = [n for n, r in results.items() if r.get("ok") is False]
    return 1 if failed else 0


def status(cfg: dict) -> None:
    now = dt.datetime.now()
    for name, area in cfg["areas"].items():
        mount = find_mount(area["label"], cfg["mount_root"])
        if mount is None:
            print(f"{name}: drive '{area['label']}' not plugged in")
            continue
        due = is_due(
            [mount / s["name"] for s in area["sets"]], area["every_hours"], now
        )
        print(
            f"{name} ({mount}): {free_gb(mount):.0f} GB free, due: {'yes' if due else 'no'}"
        )
        for spec in area["sets"]:
            snaps = snapshots(mount / spec["name"])
            if snaps:
                age = now - stamp_time(snaps[-1])
                hours = age.total_seconds() / 3600
                print(
                    f"  {spec['name']}: {len(snaps)} snapshots, newest {snaps[-1].name} ({hours:.0f} h ago)"
                )
            else:
                print(f"  {spec['name']}: no snapshots yet")
        git_dir = mount / "git"
        if git_dir.is_dir():
            print(
                f"  git mirrors: {', '.join(sorted(p.name for p in git_dir.iterdir()))}"
            )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="forge-backup",
        description="Forge backup: snapshots onto the external drive.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="show snapshots and free space")
    auto = sub.add_parser("auto", help="back up whatever is due (timer and plug-in)")
    now = sub.add_parser("now", help="back up now, due or not")
    for p in (auto, now):
        p.add_argument(
            "area", nargs="?", default="all", choices=["all", "rescue", "vault"]
        )
    sub.add_parser("eject", help="unmount both parts and power the drive off")
    sub.add_parser("scan", help="check the clean copy's whole history for secrets")
    sub.add_parser(
        "publish", help="check the clean copy, then push it to its GitHub branch"
    )
    args = ap.parse_args(argv)
    cfg = load_config()

    if args.cmd == "status":
        status(cfg)
        return 0
    if args.cmd == "eject":
        return eject(cfg)
    if args.cmd in ("scan", "publish"):
        return clean_command(cfg, args.cmd)
    if os.geteuid() != 0:
        # Hand the job to the root unit; the polkit rule lets this user start it.
        unit = f"forge-backup-{args.cmd}@{args.area}.service"
        code = subprocess.run(["systemctl", "start", "--no-block", unit]).returncode
        if code == 0:
            print(f"started {unit}; follow it with: journalctl -fu {unit}")
        return code
    which = list(cfg["areas"]) if args.area == "all" else [args.area]
    return run(cfg, which, force=args.cmd == "now")


if __name__ == "__main__":
    sys.exit(main())
