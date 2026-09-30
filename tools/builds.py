"""Keeps the playable build of Eighty Six up to date, saves each changed build as a numbered version,
and packs share zips for friends on Windows, Linux and macOS.

    python3 tools/builds.py ensure [--notify]       rebuild the local build if the game changed, save it
                                                    as a new version if it differs, print its binary
    python3 tools/builds.py path <NNN|latest|previous>   print a saved version's binary
    python3 tools/builds.py list [--json]           the saved versions, newest first
    python3 tools/builds.py export <platform> [--debug]  one export into build/<platform>/
    python3 tools/builds.py share [--platforms windows,linux,macos]
                                                    export the current game for each platform and zip
                                                    it into the newest version's share/ folder

Platforms and what to watch come from tools/platforms.json. Versions live in
build/versions/NNN-YYYY-MM-DD_HHMM/ (git-ignored). Nothing here deletes a version.
"""

import argparse
import fcntl
import filecmp
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
GODOT = os.environ.get("GODOT", "godot")
VERSION_DIR = re.compile(r"^(\d{3})-")

Exporter = Callable[[str, bool], int]


def load_platforms(root: Path = ROOT) -> dict:
    return json.loads((root / "tools" / "platforms.json").read_text())


def game_version(root: Path = ROOT) -> str:
    match = re.search(
        r'^config/version="([^"]*)"', (root / "project.godot").read_text(), re.M
    )
    return match.group(1) if match else "0"


def godot_version() -> str:
    out = subprocess.run([GODOT, "--version"], capture_output=True, text=True).stdout
    match = re.match(r"(\d+\.\d+(?:\.\d+)?)\.([a-z]+)", out.strip())
    return f"{match.group(1)}.{match.group(2)}" if match else "unknown"


def templates_dir() -> Path:
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data / "godot" / "export_templates" / godot_version()


def fingerprint(root: Path, platforms: dict) -> str:
    """A hash of every exported file's path, size and change time, plus the Godot version."""
    skip_dirs = set(platforms.get("watch_ignore", []))
    skip_files = platforms.get("watch_ignore_files", [])
    digest = hashlib.sha256()
    for folder, dirs, files in os.walk(root):
        rel_dir = Path(folder).relative_to(root).as_posix()
        dirs[:] = sorted(
            d
            for d in dirs
            if (d if rel_dir == "." else f"{rel_dir}/{d}") not in skip_dirs
        )
        for name in sorted(files):
            if any(fnmatch.fnmatch(name, pat) for pat in skip_files):
                continue
            path = Path(folder, name)
            st = path.stat()
            rel = path.relative_to(root).as_posix()
            digest.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
    digest.update(godot_version().encode())
    return digest.hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_state(root: Path) -> tuple[str, bool]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True
        ).stdout.strip()

    return git("rev-parse", "--short", "HEAD") or "none", bool(
        git("status", "--porcelain")
    )


def versions(root: Path) -> list[dict]:
    """Saved versions, newest first, each its VERSION.json plus 'dir' and 'share' (zip names)."""
    base = root / "build" / "versions"
    found = []
    if base.is_dir():
        for d in base.iterdir():
            info_file = d / "VERSION.json"
            if d.is_dir() and VERSION_DIR.match(d.name) and info_file.is_file():
                info = json.loads(info_file.read_text())
                info["dir"] = str(d)
                share = d / "share"
                info["share"] = (
                    sorted(p.name for p in share.glob("*.zip"))
                    if share.is_dir()
                    else []
                )
                found.append(info)
    return sorted(found, key=lambda v: v["number"], reverse=True)


def version_binary(info: dict, platforms: dict) -> Path:
    local = platforms["local"]
    return Path(info["dir"]) / local / platforms["platforms"][local]["file"]


def pick(root: Path, platforms: dict, which: str) -> Optional[Path]:
    saved = versions(root)
    if which == "latest":
        chosen = saved[:1]
    elif which == "previous":
        chosen = saved[1:2]
    else:
        chosen = [v for v in saved if v["number"] == int(which)]
    return version_binary(chosen[0], platforms) if chosen else None


def save_version(
    root: Path, platforms: dict, made: datetime, extra: dict
) -> tuple[dict, bool]:
    """Saves build/<local>/ as the next version unless its pack matches the newest one.

    Returns (version info, created). The binary is the unchanged Godot template in most builds, so it
    is hard-linked to the previous version's copy when identical; each version then costs only its pack.
    """
    local = platforms["local"]
    src = root / "build" / local
    binary_name = platforms["platforms"][local]["file"]
    pck_name = Path(binary_name).stem + ".pck"
    pck_sha = sha256(src / pck_name)
    saved = versions(root)
    if saved and saved[0].get("pck_sha256") == pck_sha:
        return saved[0], False
    number = saved[0]["number"] + 1 if saved else 1
    name = f"{number:03d}-{made.strftime('%Y-%m-%d_%H%M')}"
    dest = root / "build" / "versions" / name / local
    dest.mkdir(parents=True)
    shutil.copy2(src / pck_name, dest / pck_name)
    previous_bin = version_binary(saved[0], platforms) if saved else None
    if (
        previous_bin
        and previous_bin.is_file()
        and filecmp.cmp(previous_bin, src / binary_name, shallow=False)
    ):
        os.link(previous_bin, dest / binary_name)
    else:
        shutil.copy2(src / binary_name, dest / binary_name)
    info = {
        "number": number,
        "name": name,
        "game_version": game_version(root),
        "made": made.isoformat(timespec="seconds"),
        "pck_sha256": pck_sha,
        **extra,
    }
    (dest.parent / "VERSION.json").write_text(json.dumps(info, indent=2) + "\n")
    info["dir"] = str(dest.parent)
    info["share"] = []
    return info, True


def godot_export(platform: str, debug: bool) -> int:
    platforms = load_platforms()
    entry = platforms["platforms"][platform]
    tdir = templates_dir()
    missing = [t for t in entry["templates"] if not (tdir / t).is_file()]
    if missing:
        print(
            f"export: no Godot export template {', '.join(missing)} in {tdir}; install the "
            f"official {godot_version()} templates first (see README)",
            file=sys.stderr,
        )
        return 3
    out = ROOT / "build" / platform / entry["file"]
    out.parent.mkdir(parents=True, exist_ok=True)
    mode = "--export-debug" if debug else "--export-release"
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT), mode, entry["preset"], str(out)],
        stdout=sys.stderr,
    )
    if result.returncode == 0 and not out.is_file():
        return 1
    return result.returncode


def notify(enabled: bool, text: str) -> None:
    if enabled and shutil.which("notify-send"):
        subprocess.run(
            ["notify-send", "--app-name=Eighty Six", "Eighty Six", text], check=False
        )


def ensure(
    root: Path, platforms: dict, exporter: Exporter, notify_user: bool = False
) -> Optional[Path]:
    """Makes the local build match the game source, saves a version if it changed, and returns the
    binary to run: the newest version, or the newest older one if the rebuild failed."""
    local = platforms["local"]
    build = root / "build" / local
    build.mkdir(parents=True, exist_ok=True)
    with open(root / "build" / ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        fp = fingerprint(root, platforms)
        state_file = build / "BUILD.json"
        state = json.loads(state_file.read_text()) if state_file.is_file() else {}
        binary = build / platforms["platforms"][local]["file"]
        if state.get("fingerprint") != fp or not binary.is_file():
            notify(notify_user, "Updating to the latest game...")
            if exporter(local, False) != 0:
                notify(notify_user, "The update failed; playing the last good version.")
                print(
                    "builds: export failed, using the newest saved version",
                    file=sys.stderr,
                )
                return pick(root, platforms, "latest")
            commit, dirty = git_state(root)
            state = {
                "fingerprint": fp,
                "made": datetime.now().isoformat(timespec="seconds"),
                "commit": commit,
                "dirty": dirty,
            }
            state_file.write_text(json.dumps(state, indent=2) + "\n")
        info, _ = save_version(
            root,
            platforms,
            (
                datetime.fromisoformat(state["made"])
                if "made" in state
                else datetime.now()
            ),
            {k: state[k] for k in ("commit", "dirty") if k in state},
        )
        return version_binary(info, platforms)


def zip_folder(folder: Path, zip_path: Path, readme: str) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.iterdir()):
            if path.is_file():
                z.write(path, f"{folder.name}/{path.name}")
        z.writestr(f"{folder.name}/HOW-TO-RUN.txt", readme + "\n")


def share(
    root: Path, platforms: dict, wanted: list[str], exporter: Exporter
) -> list[Path]:
    """Zips the current game for each wanted platform into the newest version's share/ folder."""
    if ensure(root, platforms, exporter) is None:
        raise SystemExit("share: no build to share")
    info = versions(root)[0]
    vdir = Path(info["dir"])
    (vdir / "share").mkdir(exist_ok=True)
    made = []
    for platform in wanted:
        entry = platforms["platforms"][platform]
        stem = f"eightysix-{info['game_version']}-v{info['number']:03d}-{platform}"
        zip_path = vdir / "share" / f"{stem}.zip"
        readme = f"Eighty Six {info['game_version']}, version {info['number']:03d} ({info['made']}), {entry['label']}.\n{entry['how_to_run']}"
        if platform != platforms["local"]:
            if exporter(platform, False) != 0:
                print(f"share: {platform} export failed", file=sys.stderr)
                continue
            src = root / "build" / platform
        else:
            src = vdir / platform
        if entry["file"].endswith(".zip"):
            shutil.copy2(src / entry["file"], zip_path)
            with zipfile.ZipFile(zip_path, "a") as z:
                z.writestr("HOW-TO-RUN.txt", readme + "\n")
        else:
            staged = vdir / "share" / stem
            staged.mkdir(exist_ok=True)
            for name in (entry["file"], Path(entry["file"]).stem + ".pck"):
                shutil.copy2(src / name, staged / name)
            zip_folder(staged, zip_path, readme)
            shutil.rmtree(staged)
        made.append(zip_path)
    return made


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ensure")
    p.add_argument("--notify", action="store_true")
    p = sub.add_parser("path")
    p.add_argument("which")
    p = sub.add_parser("list")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("export")
    p.add_argument("platform")
    p.add_argument("--debug", action="store_true")
    p = sub.add_parser("share")
    p.add_argument("--platforms", default="")
    args = parser.parse_args()
    platforms = load_platforms()

    if args.cmd == "export":
        return godot_export(args.platform, args.debug)
    if args.cmd == "list":
        saved = versions(ROOT)
        if args.json:
            print(json.dumps(saved, indent=2))
        for v in [] if args.json else saved:
            flag = " (uncommitted changes)" if v.get("dirty") else ""
            print(
                f"{v['number']:03d}  {v['made']}  {v.get('commit', '?')}{flag}  share: {len(v['share'])}"
            )
        return 0
    if args.cmd == "path":
        binary = pick(ROOT, platforms, args.which)
    elif args.cmd == "share":
        wanted = [p for p in args.platforms.split(",") if p] or list(
            platforms["platforms"]
        )
        made = share(ROOT, platforms, wanted, godot_export)
        for zip_path in made:
            print(zip_path)
        return 0 if len(made) == len(wanted) else 1
    else:
        binary = ensure(ROOT, platforms, godot_export, args.notify)
    if binary is None:
        print("builds: no saved version", file=sys.stderr)
        return 1
    print(binary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
