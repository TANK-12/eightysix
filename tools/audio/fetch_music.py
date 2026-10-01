#!/usr/bin/env python3
"""Download the 86 music in music_sources.json into ~/Music/86/ and list it in data/music.json.

Personal use only: the files stay outside the repo and are never shipped or shared. Tracks already
on disk are skipped. Run: tools/audio/fetch_music.py
"""

import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
MUSIC_JSON = HERE.parent.parent / "data" / "music.json"


def main() -> None:
    spec = json.loads((HERE / "music_sources.json").read_text())
    out = Path(spec["out_dir"]).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    registry = json.loads(MUSIC_JSON.read_text())
    for track in spec["tracks"]:
        key = re.sub(r"[^a-z0-9]+", "_", track["title"].lower()).strip("_")
        path = out / f"{key}.mp3"
        if not path.exists():
            subprocess.run(
                ["yt-dlp", "-q", "--no-playlist", "-f", "bestaudio", "-x"]
                + ["--audio-format", "mp3", "--audio-quality", "160K"]
                + ["-o", str(out / f"{key}.%(ext)s"), track["yt"]],
                check=False,
            )
        if not path.exists():
            print(f"missing: {track['title']}")
            continue
        registry["entries"][key] = {
            "title": track["title"],
            "label": track["title"],
            "path": "~/" + str(path.relative_to(Path.home())),
            "language": track["language"],
            "kind": track["kind"],
            "loop": True,
            "loop_start_s": 0,
            "loop_end_s": None,
            "use": track["use"],
            "source": "https://youtu.be/" + track["yt"],
        }
        print(f"ok {path.stat().st_size / 1e6:.1f} MB  {track['title']}")
    MUSIC_JSON.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    total = sum(p.stat().st_size for p in out.glob("*.mp3")) / 1e6
    print(f"{len(registry['entries'])} tracks, {total:.0f} MB in {out}")


if __name__ == "__main__":
    main()
