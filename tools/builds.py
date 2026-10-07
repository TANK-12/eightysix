"""Keeps the playable build of Eighty Six up to date, saves finished work as numbered versions, and
packs share zips for friends on Windows, Linux and macOS.

    python3 tools/builds.py ensure [--notify]       rebuild the local build if the game changed and print
                                                    its binary (Play runs this; it never saves a version)
    python3 tools/builds.py save --note "what is in it"
                                                    save the current game as the next numbered version;
                                                    refused while the tree has uncommitted changes
    python3 tools/builds.py path <NNN|latest|previous>   print a saved version's binary
    python3 tools/builds.py list [--json]           the saved versions, newest first
    python3 tools/builds.py export <platform> [--debug]  one export into build/<platform>/
    python3 tools/builds.py share [--platforms windows,linux,macos]
                                                    zip the newest saved version for each platform (built
                                                    from that version's own commit) into build/share/,
                                                    each with an install script; older zips are deleted
    python3 tools/builds.py clear-shares            delete every share zip (they are remade on demand)

Emerson's rule (2026-10-01): one version per finished, committed part, from a clean tree, with a note
saying what is in it. Versions 007 and 008 were saved by Play from a folder holding another session's
uncommitted files, so no commit matched them; that is why only "save" numbers a version now.

Platforms and what to watch come from tools/platforms.json. Versions live in
build/versions/NNN-YYYY-MM-DD_HHMM/ (git-ignored). Nothing here deletes a version. Share zips are the
exception to keeping things: Emerson (2026-10-02) wants only the newest set on disk, so share deletes the old
ones once the new ones are made, and clear-shares deletes them all.
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

Exporter = Callable[..., int]  # (platform, debug, project root = ROOT) -> exit code
SHARE_DIR = (
    Path("build") / "share"
)  # the newest version's share zips, the only ones kept
SHARE_WORK = (
    Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "eightysix-share"
)


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


def godot_export(platform: str, debug: bool, root: Path = ROOT) -> int:
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
    out = root / "build" / platform / entry["file"]
    out.parent.mkdir(parents=True, exist_ok=True)
    mode = "--export-debug" if debug else "--export-release"
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(root), mode, entry["preset"], str(out)],
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
    """Makes the local build match the game source and returns the binary to run: the local build, or
    the newest saved version if the rebuild failed. Never saves a version (see save()).
    """
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
        return binary


class Refused(Exception):
    """A version that would not match the work it claims to be."""


def save(
    root: Path, platforms: dict, exporter: Exporter, note: str
) -> tuple[dict, bool]:
    """Saves the current game as the next numbered version, with a note saying what is in it.

    Refused (Refused) while the git tree has uncommitted changes, so a version is always exactly one
    commit. Returns (version info, created); created is False when the newest version already holds
    this same game."""
    if not note.strip():
        raise Refused("say what is in this version (--note)")
    commit, dirty = git_state(root)
    if dirty:
        raise Refused(
            "the tree has uncommitted changes (yours or another session's); commit first, "
            "so the version is exactly commit " + commit + " plus nothing"
        )
    if (
        ensure(root, platforms, exporter)
        != root
        / "build"
        / platforms["local"]
        / platforms["platforms"][platforms["local"]]["file"]
    ):
        raise Refused("the build failed; nothing saved")
    made = datetime.fromisoformat(
        json.loads((root / "build" / platforms["local"] / "BUILD.json").read_text())[
            "made"
        ]
    )
    return save_version(
        root, platforms, made, {"commit": commit, "dirty": False, "note": note.strip()}
    )


def _zip_add(z: zipfile.ZipFile, name: str, data: bytes, mode: int) -> None:
    info = zipfile.ZipInfo(name, date_time=datetime.now().timetuple()[:6])
    info.create_system = 3  # unix, so the mode below is honoured on Linux and macOS
    info.external_attr = (0o100000 | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(info, data)


def share_zips(root: Path) -> list[Path]:
    """Every share zip on disk: build/share/, the old per-version share/ folders, and the zip a macOS
    export leaves in build/macos/."""
    found = sorted((root / SHARE_DIR).glob("*.zip"))
    found += sorted((root / "build" / "versions").glob("*/share/*.zip"))
    found += sorted((root / "build" / "macos").glob("*.zip"))
    return found


def clear_shares(root: Path) -> tuple[int, int]:
    """Deletes every share zip (Emerson: they take space and are remade from a version on demand).
    Returns (files deleted, bytes freed)."""
    count = freed = 0
    for path in share_zips(root):
        freed += path.stat().st_size
        path.unlink()
        count += 1
    for folder in (root / "build" / "versions").glob("*/share"):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    return count, freed


def checkout_version(root: Path, commit: str, dest: Path) -> None:
    """The game exactly as it was at `commit`, in `dest` (a git worktree), with the files git does not
    keep copied in: synced model files and Godot's import cache (so the export does not re-import it all).
    """
    subprocess.run(
        ["git", "-C", str(root), "worktree", "add", "--detach", str(dest), commit],
        check=True,
        capture_output=True,
    )
    for path in (root / "assets" / "models").rglob("*"):
        if path.suffix in (".glb", ".png", ".jpg") and path.is_file():
            target = dest / path.relative_to(root)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    # Packaging settings are today's, not the version's (e.g. the Windows pack inside the exe)
    shutil.copy2(root / "export_presets.cfg", dest / "export_presets.cfg")
    if (root / ".godot").is_dir():
        shutil.copytree(
            root / ".godot",
            dest / ".godot",
            ignore=shutil.ignore_patterns("shader_cache", "editor"),
            dirs_exist_ok=True,
        )


def drop_checkout(root: Path, dest: Path) -> None:
    subprocess.run(
        ["git", "-C", str(root), "worktree", "remove", "--force", str(dest)],
        capture_output=True,
    )
    if dest.is_dir():
        shutil.rmtree(dest)
    subprocess.run(["git", "-C", str(root), "worktree", "prune"], capture_output=True)


def share(
    root: Path, platforms: dict, wanted: list[str], exporter: Exporter
) -> list[Path]:
    """Zips the newest saved version for each wanted platform into build/share/, then deletes every older
    share zip. Each platform is exported from that version's own commit (a scratch checkout), so the zips
    match the version even while sessions keep editing the game; the local platform reuses the version's
    saved build. Every zip holds one folder with the game, an install script and HOW-TO-RUN.txt.
    """
    saved = versions(root)
    if not saved:
        raise SystemExit('share: no saved version yet; run save --note "..." first')
    info = saved[0]
    commit = str(info.get("commit", ""))
    if info.get("dirty") or commit in ("", "none", "?"):
        raise SystemExit(
            f"share: version {info['number']:03d} was not saved from a commit; save a new version first"
        )
    vdir = Path(info["dir"])
    out_dir = root / SHARE_DIR
    new_dir = out_dir / ".new"
    if new_dir.is_dir():
        shutil.rmtree(new_dir)
    new_dir.mkdir(parents=True)
    work = SHARE_WORK / f"v{info['number']:03d}"
    remote = [p for p in wanted if p != platforms["local"]]
    made = []
    try:
        if remote:
            if work.exists():
                drop_checkout(root, work)
            work.parent.mkdir(parents=True, exist_ok=True)
            checkout_version(root, commit, work)
        for platform in wanted:
            entry = platforms["platforms"][platform]
            if platform == platforms["local"]:
                src = vdir / platform
            else:
                if exporter(platform, False, work) != 0:
                    print(f"share: {platform} export failed", file=sys.stderr)
                    continue
                src = work / "build" / platform
            made.append(_share_zip(root, info, platform, entry, src, new_dir))
    finally:
        if remote and work.exists():
            drop_checkout(root, work)
    if made:
        clear_shares(root)
        for path in made:
            path.rename(out_dir / path.name)
    shutil.rmtree(new_dir)
    return [out_dir / path.name for path in made]


MUSIC_NOTE = (
    "Music: the 86 soundtrack is not included (it is copyrighted). Out of the box the game plays a few"
    " free tracks instead. To hear your own music: open Settings (from the main menu), go to Audio >"
    " Music, press Your music folder and pick a folder of mp3, ogg or wav files you own. The game then"
    " shuffles that folder in place of the soundtrack. For each of Main menu, Exploring and In combat"
    " you can also pick Your music folder, one track, Shuffle or Off. Backspace on the folder row clears it."
)


def music_credits(root: Path) -> list[str]:
    """The credit line of every track that ships with the game (data/music.json entries with a "credit")."""
    path = root / "data" / "music.json"
    entries = json.loads(path.read_text())["entries"] if path.exists() else {}
    return [str(e["credit"]) for e in entries.values() if e.get("credit")]


def _share_zip(
    root: Path, info: dict, platform: str, entry: dict, src: Path, out_dir: Path
) -> Path:
    stem = f"eightysix-{info['game_version']}-v{info['number']:03d}-{platform}"
    zip_path = out_dir / f"{stem}.zip"
    readme = (
        f"Eighty Six {info['game_version']}, version {info['number']:03d} ({info['made']}), "
        f"{entry['label']}.\n{entry['how_to_run']}\n\n{MUSIC_NOTE}\n"
    )
    credits = music_credits(root)
    if credits:
        readme += "\nMusic credits:\n" + "".join(f"  {c}\n" for c in credits)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        if entry["file"].endswith(".zip"):
            # macOS: Godot's own zip holds the .app; its files go in our folder with their modes
            with zipfile.ZipFile(src / entry["file"]) as app:
                for item in app.infolist():
                    if item.is_dir():
                        continue
                    mode = (item.external_attr >> 16) & 0o777 or 0o644
                    _zip_add(z, f"{stem}/{item.filename}", app.read(item), mode)
        else:
            names = [entry["file"]]
            if not entry.get("pack_embedded"):
                names.append(Path(entry["file"]).stem + ".pck")
            for name in names:
                path = src / name
                z.write(path, f"{stem}/{name}")
        for extra in entry.get("extra", []):
            _zip_add(
                z, f"{stem}/{Path(extra).name}", (root / extra).read_bytes(), 0o644
            )
        if entry.get("installer"):
            script = root / entry["installer"]
            _zip_add(z, f"{stem}/{script.name}", script.read_bytes(), 0o755)
        _zip_add(z, f"{stem}/HOW-TO-RUN.txt", readme.encode(), 0o644)
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ensure")
    p.add_argument("--notify", action="store_true")
    p = sub.add_parser("save")
    p.add_argument("--note", required=True)
    p = sub.add_parser("path")
    p.add_argument("which")
    p = sub.add_parser("list")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("export")
    p.add_argument("platform")
    p.add_argument("--debug", action="store_true")
    p = sub.add_parser("share")
    p.add_argument("--platforms", default="")
    sub.add_parser("clear-shares")
    args = parser.parse_args()
    platforms = load_platforms()

    if args.cmd == "clear-shares":
        count, freed = clear_shares(ROOT)
        print(f"deleted {count} share zips, {freed / 1e6:.0f} MB freed")
        return 0
    if args.cmd == "export":
        return godot_export(args.platform, args.debug)
    if args.cmd == "list":
        saved = versions(ROOT)
        if args.json:
            print(json.dumps(saved, indent=2))
        for v in [] if args.json else saved:
            flag = " (uncommitted changes)" if v.get("dirty") else ""
            note = f"  {v['note']}" if v.get("note") else ""
            print(
                f"{v['number']:03d}  {v['made']}  {v.get('commit', '?')}{flag}  share: {len(v['share'])}{note}"
            )
        return 0
    if args.cmd == "save":
        try:
            info, created = save(ROOT, platforms, godot_export, args.note)
        except Refused as why:
            print(f"builds: not saved: {why}", file=sys.stderr)
            return 3
        print(
            f"saved version {info['number']:03d}: {info['note']}"
            if created
            else f"version {info['number']:03d} already holds this game; nothing saved"
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
