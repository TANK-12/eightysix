"""Voice profiles: a cloned or designed voice is one folder,
models/voice/profiles/<id>/, holding profile.json and its clips.

    {
      "label": "Harbour",
      "language": "en",
      "clips": {"calm": {"wav": "calm.wav", "text": "the words in the clip"},
                "angry": {"wav": "angry.wav", "text": "..."}},
      "private": false,
      "source": "where the clips came from"
    }

"calm" is the voice itself and must be there; any other clip is the same
voice in a mood (a tag from shared/voice_emotions.json). A line whose mood has
no clip clones the calm one. "private": true marks a voice cloned from a real
person without their consent (an Eighty Six voice actor, say): it may speak on
this laptop, but nothing made with it should be shared.

The cloning engines (engines/audio_cpp.py) list a row's voices from here: every
profile in one of the row's "languages". Making profiles (voice venv):

    cd ~/Forge/apps/voice
    .venv/bin/python profiles.py list
    .venv/bin/python profiles.py add <id> clip.wav --text "words" --language en
    .venv/bin/python profiles.py add <id> angry.wav --mood angry --text "..."
    .venv/bin/python profiles.py design <id> --model irodori-anime \\
        --describe "落ち着いた若い女性の指揮官" --text "..."
    .venv/bin/python profiles.py moods <id> --model auk-flash [--only angry,sad]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
CALM = "calm"
RATE = 24000


def load(folder: Path | None) -> dict[str, dict]:
    """Every usable profile under `folder` by id; clip paths made absolute.
    A folder with a bad name, bad json or no calm clip is skipped."""
    out: dict[str, dict] = {}
    if folder is None or not Path(folder).is_dir():
        return out
    for d in sorted(Path(folder).iterdir()):
        if not ID.match(d.name) or not (d / "profile.json").is_file():
            continue
        try:
            p = json.loads((d / "profile.json").read_text())
            clips = {}
            for mood, c in (p.get("clips") or {}).items():
                wav = d / str(c["wav"])
                if wav.resolve().parent == d.resolve() and wav.is_file():
                    clips[str(mood)] = {"wav": wav, "text": str(c.get("text") or "")}
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
        if CALM not in clips:
            continue
        out[d.name] = dict(p, id=d.name, dir=d, clips=clips)
    return out


def for_languages(found: dict[str, dict], languages: list[str]) -> dict[str, dict]:
    """The profiles in one of `languages` (all of them when it is empty)."""
    if not languages:
        return found
    return {k: p for k, p in found.items() if p.get("language") in languages}


def clip(profile: dict, mood: str | None) -> tuple[Path, str]:
    """The reference clip and its words for a mood, else the calm clip."""
    c = profile["clips"].get(mood or CALM) or profile["clips"][CALM]
    return c["wav"], c["text"]


# ------------------------------------------------------------------ making


def _write(d: Path, p: dict) -> None:
    keep = {k: v for k, v in p.items() if k not in ("id", "dir", "clips")}
    keep["clips"] = {
        m: {"wav": Path(c["wav"]).name, "text": c["text"]}
        for m, c in sorted(p.get("clips", {}).items())
    }
    tmp = d / "profile.json.tmp"
    tmp.write_text(json.dumps(keep, ensure_ascii=False, indent=1) + "\n")
    tmp.replace(d / "profile.json")


def _read(d: Path) -> dict:
    try:
        p = json.loads((d / "profile.json").read_text())
    except (OSError, ValueError):
        p = {}
    p["clips"] = {
        m: {"wav": d / c["wav"], "text": c.get("text", "")}
        for m, c in (p.get("clips") or {}).items()
    }
    return p


def to_wav(src: Path, dest: Path) -> None:
    """Any audio file to 24 kHz mono 16-bit wav (ffmpeg)."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src)]
    cmd += ["-ac", "1", "-ar", str(RATE), "-sample_fmt", "s16", str(dest)]
    subprocess.run(cmd, check=True)


def _set_aside(d: Path, p: dict) -> Path:
    """Move a profile's clips and a copy of its profile.json into old-<time>/
    in its folder: a new calm clip is a new voice, and the old mood clips
    would still speak in the old one."""
    old = d / time.strftime("old-%Y%m%d-%H%M%S")
    n = 1
    while old.exists():
        n += 1
        old = d / time.strftime(f"old-%Y%m%d-%H%M%S-{n}")
    old.mkdir()
    for c in p["clips"].values():
        src = Path(c["wav"])
        # only the profile's own clips: a hand-edited path elsewhere stays put
        if src.is_file() and src.resolve().is_relative_to(d.resolve()):
            shutil.move(str(src), old / src.name)
    if (d / "profile.json").is_file():
        shutil.copy2(d / "profile.json", old / "profile.json")
    p["clips"] = {}
    return old


def save_clip(home: Path, pid: str, mood: str, wav: Path, text: str, **fields) -> Path:
    """Copy (converting) a clip into profile `pid` as its `mood` clip. A new
    calm clip first moves the old clips aside (old-<time>/), mood clips too."""
    if not ID.match(pid):
        raise ValueError(f"bad profile id {pid!r}: lower case letters, digits, - and _")
    if not re.match(r"^[a-z][a-z_-]{0,30}$", mood):
        raise ValueError(f"bad mood {mood!r}")
    d = Path(home) / pid
    d.mkdir(parents=True, exist_ok=True)
    p = _read(d)
    for k, v in fields.items():
        if v is not None:
            p[k] = v
    if mood != CALM and CALM not in p["clips"]:
        raise ValueError(f"{pid} has no calm clip yet: add that first")
    dest = d / f"{mood}.wav"
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t) / "clip.wav"
        to_wav(Path(wav), tmp)  # read first: the source may be the old calm clip
        if mood == CALM and p["clips"]:
            _set_aside(d, p)
        shutil.move(str(tmp), dest)
    p["clips"][mood] = {"wav": dest, "text": text}
    _write(d, p)
    return dest


def mood_list(style: dict, vocab_tags: dict) -> list[str]:
    """The moods a style can make: its edits, else its mapped mood tags."""
    if style.get("edits"):
        return [m for m in style["edits"] if m != CALM]
    moods = ("emotion", "delivery")
    return [
        m for m in style.get("map", {}) if vocab_tags.get(m, {}).get("kind") in moods
    ]


def _engine(model: str, tools: bool = True):
    """Load a model's engine; `tools` asks for design and edit (audio.cpp)."""
    import engines
    import service

    reg = service.load_registry()
    row = service.model_row(reg, model)
    if tools and row.get("engine") != "audio_cpp":
        raise SystemExit(f"{model} is not an audio.cpp model")
    need = int(row.get("ram_mb") or 0) + service.HEAVY_HEADROOM_MB
    if service.mem_available_mb() < need:
        raise SystemExit(f"not enough free memory for {model} (needs {need} MB)")
    return row, engines.load(row, service.model_files(row), 6)


def main(argv: list[str] | None = None) -> int:
    import expressive
    import service

    home = service.models_home() / "voice" / "profiles"
    ap = argparse.ArgumentParser(prog="profiles", description="Forge voice profiles")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    a = sub.add_parser("add", help="add a clip (calm first, then moods)")
    a.add_argument("id")
    a.add_argument("wav", type=Path)
    a.add_argument("--text", required=True, help="the words in the clip")
    a.add_argument("--mood", default=CALM)
    a.add_argument("--language")
    a.add_argument("--label")
    a.add_argument("--source")
    a.add_argument("--private", action="store_true")
    g = sub.add_parser("design", help="make a calm clip from a description")
    g.add_argument("id")
    g.add_argument("--model", required=True)
    g.add_argument("--describe", required=True)
    g.add_argument("--text", required=True)
    g.add_argument("--label")
    m = sub.add_parser("moods", help="make missing mood clips from the calm one")
    m.add_argument("id")
    m.add_argument("--model", required=True)
    m.add_argument("--only", default="")
    m.add_argument("--redo", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        for pid, p in load(home).items():
            flag = " private" if p.get("private") else ""
            moods = ",".join(sorted(p["clips"]))
            print(
                f"{pid:<20} {p.get('language', '?'):<3} {moods}{flag}  {p.get('label', '')}"
            )
        return 0
    if args.cmd == "add":
        if args.mood == CALM and not args.language and not (home / args.id).exists():
            raise SystemExit("a new profile needs --language (en, ja ...)")
        dest = save_clip(
            home,
            args.id,
            args.mood,
            args.wav,
            args.text,
            language=args.language,
            label=args.label,
            source=args.source,
            private=True if args.private else None,
        )
        print(dest)
        return 0
    row, eng = _engine(args.model)
    try:
        langs = row.get("languages") or []
        if args.cmd == "design":
            with tempfile.TemporaryDirectory() as t:
                out = Path(t) / "calm.wav"
                eng.design(args.text, args.describe, out)
                save_clip(
                    home,
                    args.id,
                    CALM,
                    out,
                    args.text,
                    language=langs[0] if langs else None,
                    label=args.label or args.id,
                    source=f"designed with {row['id']}: {args.describe}",
                )
            print(home / args.id / "calm.wav")
            return 0
        prof = load(home).get(args.id)
        if prof is None:
            raise SystemExit(f"no profile {args.id} (see: profiles.py list)")
        st = expressive.style(row.get("expressive") or "")
        wanted = [x for x in args.only.split(",") if x] or mood_list(
            st, expressive.vocab()["tags"]
        )
        calm_wav, calm_text = clip(prof, CALM)
        for mood in wanted:
            if mood in prof["clips"] and not args.redo:
                continue
            with tempfile.TemporaryDirectory() as t:
                out = Path(t) / f"{mood}.wav"
                if st.get("edits", {}).get(mood):
                    eng.edit(calm_wav, st["edits"][mood], out)
                else:
                    import engines

                    audio, rate = eng.synthesize(f"[{mood}] {calm_text}", args.id, 1.0)
                    out.write_bytes(engines.wav_bytes(audio, rate))
                save_clip(home, args.id, mood, out, calm_text)
            print(f"{args.id}: {mood}", flush=True)
        return 0
    finally:
        eng.close()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
