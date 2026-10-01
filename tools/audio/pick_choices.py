#!/usr/bin/env python3
"""Turn the downloaded library into choices for each game sound (lane B4 part 2).

For every rule in choices.json: score the library (library.json from fetch_library.py), cut the
best few to length, peak-normalise them to -1 dBFS, write them as Ogg into assets/audio/lib/<entry>/
(mono for sounds placed in the world, stereo for 2D ones) and list them in that data/sounds.json
entry as "choices", after the synth take ("Made here") and an "Off" choice. "choice" is the default
from the rule. Emerson then picks and levels each one in Settings > Audio > Sounds.

Run: tools/audio/pick_choices.py [--dry]
"""

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "tools/audio"
LIB_OUT = ROOT / "assets/audio/lib"
SOUNDS = ROOT / "data/sounds.json"


def score(sound: dict, rule: dict) -> float:
    title = (
        re.sub(r"([a-z])([A-Z])", r"\1 \2", sound["title"]).replace("_", " ").lower()
    )
    words = set(re.findall(r"[a-z]+", title))
    s = 2.0 * len(set(sound["tags"]) & set(rule["tags"]))
    s += 3.0 * sum(1 for w in rule["words"] if w in words or w in title)
    s -= 10.0 * sum(1 for w in rule["not"] if w in title)
    return s


def levels(path: Path, seconds: float = 3600.0) -> tuple[float, float]:
    """(mean, peak) level in dBFS of the first `seconds` of a file."""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-t", str(seconds), "-i", str(path)]
        + ["-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
    ).stderr
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", out)
    peak = re.search(r"max_volume: (-?[\d.]+) dB", out)
    return (
        float(mean.group(1)) if mean else -20.0,
        float(peak.group(1)) if peak else 0.0,
    )


PUNCH = "acompressor=threshold=-28dB:ratio=6:attack=3:release=150:makeup=1"


def convert(
    src: Path, dst: Path, max_s: float, mono: bool, mean_db: float, punch: bool
) -> None:
    """Cut to max_s and set the average level to mean_db (the synth take's, so the entry's
    volume_db keeps meaning the same loudness), never letting the peak pass -1 dBFS. With
    punch (guns, explosions) the take is compressed first and then raised to a -1 dBFS peak:
    a recorded shot is one sharp spike with little body, which reads as quiet in game.
    """
    if punch:
        squeezed = dst.with_suffix(".tmp.wav")
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-t", str(max_s)]
            + ["-i", str(src), "-af", PUNCH, str(squeezed)],
            check=True,
        )
        convert(squeezed, dst, max_s, mono, 0.0, False)
        squeezed.unlink()
        return
    mean, peak = levels(src, max_s)
    gain = min(mean_db - mean, -1.0 - peak)
    fade = min(0.25, max_s * 0.1)
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-t",
            str(max_s),
            "-i",
            str(src),
        ]
        + ["-af", f"volume={gain}dB,afade=t=out:st={max(max_s - fade, 0)}:d={fade}"]
        + (["-ac", "1"] if mono else [])
        + ["-ar", "44100", "-c:a", "libvorbis", "-q:a", "6", str(dst)],
        check=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    spec = json.loads((HERE / "choices.json").read_text())
    sources = json.loads((HERE / "library_sources.json").read_text())
    library = json.loads(
        (Path(sources["library_dir"]).expanduser() / "library.json").read_text()
    )["entries"]
    sounds = json.loads(SOUNDS.read_text())
    entries = sounds["entries"]
    for event, rule in spec["rules"].items():
        if event not in entries:
            if "new" not in rule:
                continue
            entries[event] = dict(rule["new"], files=[])
        e = entries[event]
        two_d = bool(e.get("2d", False))
        synth = [c for c in e.get("choices", []) if c["id"] == "synth"]
        synth_files = synth[0]["files"] if synth else e.get("files", [])
        ranked = sorted(
            (
                (score(s, rule), key)
                for key, s in library.items()
                if 0 < s.get("seconds", 0) and (s["seconds"] <= rule["max_s"] * 2.5)
            ),
            reverse=True,
        )
        picks = [key for sc, key in ranked if sc > 2][: spec["count"]]
        choices = []
        if synth_files:
            choices.append(
                {"id": "synth", "label": "Made here (synth)", "files": synth_files}
            )
        like = entries.get(rule.get("loudness_like", event), e)
        like_files = [c for c in like.get("choices", []) if c["id"] == "synth"]
        ref = (like_files[0]["files"] if like_files else like.get("files", [])) or [""]
        target = (
            levels(ROOT / ref[0].replace("res://", ""))[0] if ref[0] else -20.0
        ) + float(rule.get("loudness_db", 0.0))
        out_dir = LIB_OUT / event
        if not args.dry and out_dir.exists():
            shutil.rmtree(out_dir)
        for n, key in enumerate(picks, 1):
            s = library[key]
            name = f"{n}_{re.sub(r'[^a-z0-9]+', '_', s['title'].lower())[:40].strip('_')}.ogg"
            if not args.dry:
                convert(
                    Path(s["path"]),
                    out_dir / name,
                    rule["max_s"],
                    not two_d,
                    target,
                    bool(rule.get("punch", False)),
                )
            label = f"{s['title']} ({s['source'].capitalize()})"
            choice = {
                "id": key,
                "label": label,
                "files": [f"res://assets/audio/lib/{event}/{name}"],
                "licence": s["licence"],
            }
            if "pitch" in rule:
                choice["pitch"] = rule["pitch"]
            choices.append(choice)
        choices.append({"id": "off", "label": "Off", "files": []})
        lib_choices = [c for c in choices if c["id"] not in ("synth", "off")]
        default = rule.get("default", "best")
        preferred = [
            c
            for c in lib_choices
            if rule.get("prefer", "\0") in c["label"].lower().replace("_", " ")
            or rule.get("prefer", "\0").replace(" ", "")
            in c["label"].lower().replace(" ", "")
        ]
        if default == "best" and lib_choices:
            e["choice"] = (preferred or lib_choices)[0]["id"]
        elif default == "off":
            e["choice"] = "off"
        else:
            e["choice"] = "synth" if synth_files else choices[0]["id"]
        e["choices"] = choices
        e["files"] = synth_files
        print(f"{event}: {len(lib_choices)} choices, default {e['choice']}")
        for c in lib_choices:
            print(f"    {c['label']}")
    if not args.dry:
        SOUNDS.write_text(json.dumps(sounds, indent=2, ensure_ascii=False) + "\n")
        # Godot must import the new files before the game (or a test) can load them
        subprocess.run(
            ["godot", "--headless", "--path", str(ROOT), "--import"],
            capture_output=True,
        )


if __name__ == "__main__":
    main()
