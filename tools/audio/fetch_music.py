#!/usr/bin/env python3
"""Download the 86 music in music_sources.json into assets/audio/86/ (out_dir, relative to the project) and rebuild data/music.json from it.

Personal use only: the files stay outside the repo and are never shipped or shared. Tracks already
on disk are skipped; a track dropped from the list leaves the registry (its file is reported, not
removed). The hand-listed "free" set (it ships with the game) is kept. Run:
tools/audio/fetch_music.py
"""

import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MUSIC_JSON = ROOT / "data" / "music.json"


def main() -> None:
    spec = json.loads((HERE / "music_sources.json").read_text())
    out = ROOT / Path(spec["out_dir"]).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    registry = json.loads(MUSIC_JSON.read_text())
    # the "free" set is listed by hand (it ships with the game), so it is kept
    registry["entries"] = {
        k: e for k, e in registry["entries"].items() if e.get("set") == "free"
    }
    for track in spec["tracks"]:
        key = re.sub(r"[^a-z0-9]+", "_", track["title"].lower()).strip("_")
        path = out / f"{key}.mp3"
        if not path.exists():
            # a full URL: an id that starts with "-" would be read as an option
            subprocess.run(
                ["yt-dlp", "-q", "--no-playlist", "-f", "bestaudio", "-x"]
                + ["--audio-format", "mp3", "--audio-quality", "160K"]
                + [
                    "-o",
                    str(out / f"{key}.%(ext)s"),
                    "https://youtu.be/" + track["yt"],
                ],
                check=False,
            )
        if not path.exists():
            print(f"missing: {track['title']}")
            continue
        registry["entries"][key] = {
            "title": track["title"],
            "label": track["title"],
            "path": (
                str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
            ),
            "language": track["language"],
            "kind": track["kind"],
            "set": track.get("set", "ost"),
            "order": track.get("order", 1000),
            "use": track["use"],
            "source": "https://youtu.be/" + track["yt"],
        }
        if track.get("set") == "extra":
            registry["entries"][key]["show_if"] = "audio.music_extras"
        print(f"ok {path.stat().st_size / 1e6:.1f} MB  {track['title']}")
    MUSIC_JSON.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    listed = {Path(e["path"]).name for e in registry["entries"].values()}
    for p in sorted(out.glob("*.mp3")):
        if p.name not in listed:
            print(f"not listed any more: {p}")
    total = sum(p.stat().st_size for p in out.glob("*.mp3")) / 1e6
    print(f"{len(registry['entries'])} tracks, {total:.0f} MB in {out}")


if __name__ == "__main__":
    main()
