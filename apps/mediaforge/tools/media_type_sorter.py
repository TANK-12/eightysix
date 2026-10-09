#!/usr/bin/env python3
"""
media_type_sorter.py -- fold a folder of generically-named downloads (the "4K
Video Downloader" style dump: YouTube rips, music mixes, misc video/audio with
no episode structure anitopy/AniList can key off) into <library>/<label>/<ext>/.

Built for the case anime_sorter.py deliberately doesn't handle: files that
aren't episodes at all, where two files can share (or nearly share) a filename
while being completely different recordings, or have totally different names
while being the exact same recording re-encoded/re-downloaded.

  * Identity is decided by the ACTUAL AUDIO CONTENT, not the filename and not
    a head/tail byte hash: the first few minutes are decoded to raw PCM and
    hashed (mediaforge.audiohash). Two files that decode to the same audio are
    the same recording no matter what they're called or how they're encoded;
    two files with the same-looking name but different audio are kept as
    separate, distinctly-named files -- never silently merged or overwritten.
  * NEVER deletes, NEVER overwrites. Moves only (revertible manifest, the same
    format the Library Organiser / anime_sorter use).
  * True duplicates (identical audio) -> the smaller/later copy is MOVED to
    <library>/_DUPLICATES/<original path>, same as every other MediaForge
    tool -- never left scattered, never deleted.
  * Sorted into <library>/<label>/<ext>/<name>, one subfolder per file type
    (mp4, mp3, m4a, ...). A name clash between two DIFFERENT recordings gets a
    new, meaningful name: the audio duration appended ("Title [12m34s].mp4"),
    falling back to a short content-hash suffix if durations also collide.

Usage:
    media_type_sorter.py --scan DIR [DIR ...] --library DIR                 # dry run
    media_type_sorter.py --scan DIR [DIR ...] --library DIR --apply         # execute
    media_type_sorter.py --revert ~/MediaForgeData/manifests/XXXX.json      # undo
"""

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mediaforge.config import MANIFEST_DIR                     # noqa: E402
from mediaforge.manifest import Manifest, apply_op, quick_hash  # noqa: E402
from mediaforge.audiohash import (                              # noqa: E402
    audio_content_hash, probe_duration, format_duration, FFMPEG,
)

DEFAULT_EXTS = {
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v",                # video
    ".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg", ".opus",       # audio
}
SKIP_DIR_NAMES = {"_duplicates", "_conflicts", "system volume information",
                  ".trash-1000", "$recycle.bin"}


def clean_component(s):
    return "".join(c for c in s if c not in '<>:"/\\|?*').strip()


def scan_files(roots, exts):
    out = []
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in exts:
                continue
            if any(part.lower() in SKIP_DIR_NAMES for part in p.parts):
                continue
            out.append(p)
    return out


def content_key(path, audio_minutes, log):
    """(kind, hash). kind='audio' when we got a real audio-content hash,
    'bytes' when we fell back to the byte head/tail hash (no audio track, or
    ffmpeg unavailable/failed)."""
    h = audio_content_hash(path, minutes=audio_minutes)
    if h:
        return "audio", h
    log(f"  (no usable audio track in {path.name} -- falling back to byte hash)")
    return "bytes", quick_hash(path)


def unique_dest(base_dir, stem, suffix, dur_tag, content_hash):
    """base_dir/stem+suffix, or base_dir/'stem [dur_tag]'+suffix if that's
    taken by something else, or base_dir/'stem [hash6]'+suffix as a last
    resort, then a numeric tiebreak."""
    cand = base_dir / f"{stem}{suffix}"
    if not cand.exists():
        return cand
    if dur_tag:
        cand = base_dir / f"{stem} [{dur_tag}]{suffix}"
        if not cand.exists():
            return cand
    cand = base_dir / f"{stem} [{content_hash[:8]}]{suffix}"
    if not cand.exists():
        return cand
    k = 2
    while True:
        cand = base_dir / f"{stem} [{content_hash[:8]}] ({k}){suffix}"
        if not cand.exists():
            return cand
        k += 1


def build_plan(scan_roots, library, label, exts, audio_minutes, log=print):
    library = Path(library)
    dest_root = library / label
    files = scan_files(scan_roots, exts)
    log(f"{len(files)} file(s) found under {', '.join(str(r) for r in scan_roots)}")
    if not FFMPEG:
        log("  WARNING: ffmpeg not found -- every file will fall back to a byte "
            "hash instead of true audio-content identity.")

    groups = defaultdict(list)   # (kind, hash) -> [Path, ...]
    for i, p in enumerate(files, 1):
        kind, h = content_key(p, audio_minutes, log)
        if h:
            groups[(kind, h)].append(p)
        else:
            log(f"  couldn't hash (unreadable?): {p}")
        if i % 10 == 0:
            log(f"  hashed {i}/{len(files)}")

    plan = []   # dicts: op(move), src, dst, note
    # per-destination-folder claimed basenames, so two groups in the same run
    # don't collide with each other (not just with what's already on disk)
    claimed = defaultdict(set)

    for (kind, h), members in groups.items():
        # keeper = largest file (most likely the fullest/best-quality copy);
        # ties broken by shortest name (usually the "clean" one, not a
        # "(1)"/"copy"-suffixed duplicate download)
        members.sort(key=lambda p: (-p.stat().st_size, len(p.name)))
        keeper, dupes = members[0], members[1:]

        ext = keeper.suffix.lower()
        type_dir = dest_root / ext.lstrip(".")
        stem = clean_component(keeper.stem) or "untitled"
        dur = probe_duration(keeper) if kind == "audio" else None
        dur_tag = format_duration(dur)

        already_placed = False
        target = type_dir / f"{stem}{ext}"
        if target.exists():
            # resuming after a partial apply? if what's already there is THIS
            # same recording, it's already correctly placed -- don't move it
            # again or invent a duplicate-looking sibling name for it. (The
            # dupes loop below still runs, so any remaining duplicate members
            # still get parked.)
            existing_key = content_key(target, audio_minutes, log)
            if existing_key == (kind, h):
                log(f"  already sorted: {target.name}")
                already_placed = True

        if not already_placed:
            if target.name.lower() in claimed[type_dir] or target.exists():
                target = unique_dest(type_dir, stem, ext, dur_tag, h)
            claimed[type_dir].add(target.name.lower())

            note = "audio-content match" if kind == "audio" else "byte-hash fallback"
            if target.stem != stem:
                note += "; renamed (name clash with a different recording)"
            plan.append({"op": "move", "src": keeper, "dst": target,
                         "size": keeper.stat().st_size, "hash": h, "note": note})

        for d in dupes:
            try:
                rel = d.relative_to(library)
            except ValueError:
                rel = d.relative_to(d.anchor)
            dup_target = library / "_DUPLICATES" / rel
            k = 2
            base_dup = dup_target
            while dup_target.exists() or any(e["dst"] == dup_target for e in plan):
                dup_target = base_dup.with_stem(f"{base_dup.stem} ({k})")
                k += 1
            plan.append({"op": "move", "src": d, "dst": dup_target,
                        "size": d.stat().st_size, "hash": h,
                        "note": f"identical audio to {keeper.name} -- parked, not deleted"})

    return plan


def write_report(plan, path):
    lines = ["MEDIA TYPE SORT PLAN", "=" * 72]
    moves = [e for e in plan if "_DUPLICATES" not in str(e["dst"])]
    dupes = [e for e in plan if "_DUPLICATES" in str(e["dst"])]
    lines.append(f"{len(moves)} file(s) to sort, {len(dupes)} true duplicate(s) to park\n")
    lines.append("SORT:")
    for e in moves:
        lines.append(f"  {e['src']}\n    -> {e['dst']}   ({e['note']})")
    if dupes:
        lines.append("\nPARKED IN _DUPLICATES (yours to clear):")
        for e in dupes:
            lines.append(f"  {e['src']}\n    -> {e['dst']}   ({e['note']})")
    text = "\n".join(lines)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, "utf-8")
    return text


def apply_plan(plan, log=print):
    man = Manifest("media-type-sort")
    done = failed = 0
    for e in plan:
        try:
            apply_op("move", e["src"], e["dst"])
            man.record("move", e["src"], e["dst"], e["size"], e["hash"], e["note"])
            done += 1
            log(f"moved: {Path(e['src']).name} -> {e['dst']}")
        except Exception as ex:
            failed += 1
            log(f"FAIL {e['src']}: {ex}")
    mp = man.save()
    log(f"\n  {done} moved, {failed} failed.\n  manifest: {mp}")
    return mp


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", nargs="+")
    ap.add_argument("--library")
    ap.add_argument("--label", default="4K Video Downloader")
    ap.add_argument("--exts", help="comma-separated, overrides the default type list")
    ap.add_argument("--audio-minutes", type=int, default=3)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert")
    ap.add_argument("--report", default=str(MANIFEST_DIR / "media_type_sort_plan.txt"))
    args = ap.parse_args()

    if args.revert:
        from mediaforge.manifest import revert
        u, s, np_ = revert(args.revert, log=print)
        print(f"reverted {u}, skipped {s}\nnew manifest: {np_}")
        return
    if not args.scan or not args.library:
        ap.error("need --scan and --library (or --revert)")

    exts = ({("." + e.strip(".").lower()) for e in args.exts.split(",")}
           if args.exts else DEFAULT_EXTS)
    library = Path(args.library).expanduser().resolve()
    library.mkdir(parents=True, exist_ok=True)
    scan_roots = [Path(s).expanduser().resolve() for s in args.scan]

    plan = build_plan(scan_roots, library, args.label, exts, args.audio_minutes)
    write_report(plan, args.report)
    moves = sum(1 for e in plan if "_DUPLICATES" not in str(e["dst"]))
    dupes = len(plan) - moves
    print(f"\n{'=' * 56}\n  sort  {moves}\n  dupe  {dupes}\n  plan -> {args.report}")
    if args.apply:
        print("\napplying…")
        apply_plan(plan)
    else:
        print("\ndry run -- re-run with --apply")


if __name__ == "__main__":
    main()
