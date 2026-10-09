"""Character voices for a game: a cast file maps the game's speakers to voice
profiles (profiles.py) and renders the game's lines to clips through the Voice
API, so the voices stay one shared thing in Forge.

A cast is one file, casts/<name>.json (casts/eightysix.json is the example):

    lines          glob of the game's dialogue files (read only, never edited)
    format         field names in those files: entries, speaker, note, channel
    out            folder for the clips, relative to ~/Forge (outputs/ is not in git)
    skip_channels  channels that are read on screen, not heard
    languages      per language: model (speaks the lines), text (the line
                   field with its words), and what makes stand-in voices:
                   preset_model (a ready voice reads the sample) or
                   design_model (a voice designed from a description)
    note_moods     delivery notes that are not tags: {"very quiet": "whisper"}
    speakers       per speaker id and language: voice (a profile id); a
                   stand-in also has sample (the words of its clip) and either
                   preset (a voice of preset_model) or describe (cast.py voices)

A line's mood is the longest note_moods phrase in its note, else the first
note word that is a tag in shared/voice_emotions.json ("cheerful" is happy).
Clips land in <out>/<language>/<line id>.wav with manifest.json beside them
(an id with other characters than letters, digits, ".", "_" and "-" gets a
short hash on its file name, so two ids never share a file). A line already
made with the same words, model and voice clips (the calm clip and the mood
clip, with their words) is skipped. A line with no words ("...") is skipped,
and a clip that came back in another voice or model (X-Voice-Fell-Back,
X-Voice-Voice, X-Voice-Model) is not kept.

    cd ~/Forge/apps/voice
    .venv/bin/python cast.py list
    .venv/bin/python cast.py voices eightysix [--lang en]
    .venv/bin/python cast.py render eightysix --lang en [--speaker lena]
        [--only <line id>,...] [--limit 20] [--dry-run] [--redo] [--url URL]
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import io
import json
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import expressive
import profiles

HERE = Path(__file__).resolve().parent
FORGE = HERE.parent.parent
CASTS = HERE / "casts"
URL = "http://127.0.0.1:8467"
FIELDS = {
    "entries": "entries",
    "speaker": "speaker",
    "note": "note",
    "channel": "channel",
}


def load(name: str, folder: Path = CASTS) -> dict:
    p = Path(folder) / f"{name}.json"
    if not re.match(r"^[a-z0-9_-]+$", name) or not p.is_file():
        raise SystemExit(f"no cast {name!r} (see: cast.py list)")
    return dict(json.loads(p.read_text()), name=name)


def game_lines(cast: dict) -> list[dict]:
    """Every line in the game's files, by file then id."""
    f = dict(FIELDS, **(cast.get("format") or {}))
    out = []
    for path in sorted(glob.glob(str(Path(cast["lines"]).expanduser()))):
        entries = json.loads(Path(path).read_text()).get(f["entries"]) or {}
        for lid, e in sorted(entries.items()):
            if isinstance(e, dict):
                out.append(
                    {
                        "id": str(lid),
                        "speaker": str(e.get(f["speaker"]) or ""),
                        "note": str(e.get(f["note"]) or ""),
                        "channel": str(e.get(f["channel"]) or ""),
                        "entry": e,
                    }
                )
    return out


def mood_of(note: str, cast: dict) -> str | None:
    """The mood tag a delivery note asks for, if any."""
    words = " ".join(re.findall(r"[a-z']+", note.lower()))
    phrases = sorted((cast.get("note_moods") or {}).items(), key=lambda kv: -len(kv[0]))
    for phrase, mood in phrases:
        if re.search(rf"(?<![a-z']){re.escape(phrase)}(?![a-z'])", words):
            return mood or None
    names = expressive.vocab()["names"]
    for w in words.split():
        tag = names.get(w)
        if tag and expressive.kind(tag) in expressive.MOODS:
            return tag
    return None


def plan(cast: dict, lang: str, home: Path, only=(), speaker="") -> list[dict]:
    """What each line would be: its words with the mood tag, model and voice,
    or why it is skipped."""
    langs = cast.get("languages") or {}
    if lang not in langs:
        raise SystemExit(f"{cast['name']} has no language {lang!r}")
    spec = langs[lang]
    found = profiles.load(home)
    skip = set(cast.get("skip_channels") or [])
    out = []
    for ln in game_lines(cast):
        if (only and ln["id"] not in only) or (speaker and ln["speaker"] != speaker):
            continue
        item = {"id": ln["id"], "speaker": ln["speaker"], "model": spec["model"]}
        words = str(ln["entry"].get(spec.get("text") or "text") or "").strip()
        sp = ((cast.get("speakers") or {}).get(ln["speaker"]) or {}).get(lang) or {}
        voice = sp.get("voice") or ""
        if ln["channel"] in skip:
            item["skip"] = f"{ln['channel']} line, read not heard"
        elif not words:
            item["skip"] = f"no {lang} words"
        elif not re.search(r"\w", expressive.plain(words)):
            item["skip"] = "nothing to say (no words)"
        elif not voice:
            item["skip"] = f"no {lang} voice for {ln['speaker'] or 'no speaker'}"
        elif voice not in found:
            item["skip"] = f"voice {voice} not made yet (cast.py voices)"
        else:
            mood = mood_of(ln["note"], cast)
            item.update(
                voice=voice,
                text=words,
                mood=mood,
                said=f"[{mood}] {words}" if mood else words,
                clip_key=clip_key(found[voice], mood),
                stand_in=bool(sp.get("describe") or sp.get("preset")),
                private=bool(found[voice].get("private")),
            )
        out.append(item)
    return out


def clip_key(prof: dict, mood: str | None) -> str:
    """The reference clips a line is made from, so a new one remakes it: the
    calm clip (Breeze clones only that one) and the mood clip when there is
    one, each with its time stamp and words."""
    used = dict([profiles.clip(prof, None), profiles.clip(prof, mood)])
    return "|".join(
        f"{Path(w).name}:{Path(w).stat().st_mtime_ns}:"
        + hashlib.sha1(t.encode()).hexdigest()[:8]
        for w, t in used.items()
    )


def clip_name(line_id: str) -> str:
    """The clip's file name; ids that had to be changed get a short hash."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", line_id)
    if safe != line_id:
        safe += "-" + hashlib.sha1(line_id.encode()).hexdigest()[:6]
    return safe + ".wav"


def wav_seconds(data: bytes) -> float:
    try:
        with wave.open(io.BytesIO(data)) as w:
            return round(w.getnframes() / w.getframerate(), 2)
    except (wave.Error, EOFError, ZeroDivisionError):
        return 0.0


def speak(url: str, said: str, model: str, voice: str) -> tuple[bytes, dict]:
    """One line through the Voice API; header names come back lower case."""
    body = json.dumps({"text": said, "model": model, "voice": voice, "app": "cast"})
    req = urllib.request.Request(url.rstrip("/") + "/api/tts", data=body.encode())
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Forge", "1")
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read(), {k.lower(): v for k, v in r.headers.items()}


def render(cast: dict, lang: str, home: Path, url: str, **pick) -> dict:
    """Make the clips a plan asks for; returns counts and the failures."""
    limit, redo, dry = (
        pick.pop("limit", 0),
        pick.pop("redo", False),
        pick.pop("dry", False),
    )
    folder = FORGE / cast["out"] / lang
    mpath = folder / "manifest.json"
    try:
        manifest = json.loads(mpath.read_text())
    except (OSError, ValueError):
        manifest = {}
    made = manifest.setdefault("lines", {})
    manifest.update(cast=cast["name"], language=lang)
    counts: dict = {"made": 0, "kept": 0, "skipped": 0, "failed": [], "why": {}}
    todo = []
    for item in plan(cast, lang, home, **pick):
        if "skip" in item:
            counts["skipped"] += 1
            counts["why"][item["skip"]] = counts["why"].get(item["skip"], 0) + 1
            continue
        old = made.get(item["id"]) or {}
        same = all(
            old.get(k) == item[k] for k in ("said", "model", "voice", "clip_key")
        )
        if same and not redo and (folder / old.get("file", "-")).is_file():
            counts["kept"] += 1
            continue
        todo.append(item)
    if limit:
        todo = todo[:limit]
    if dry:
        return dict(counts, todo=todo)
    if not todo:
        return counts
    folder.mkdir(parents=True, exist_ok=True)
    for item in todo:
        name = clip_name(item["id"])
        t = time.monotonic()
        try:
            wav, headers = speak(url, item["said"], item["model"], item["voice"])
        except (OSError, urllib.error.URLError) as e:
            counts["failed"].append(f"{item['id']}: {e}")
            continue
        if headers.get("x-voice-fell-back"):
            why = headers["x-voice-fell-back"]
            counts["failed"].append(f"{item['id']}: fell back to the default ({why})")
            continue
        if headers.get("x-voice-model", item["model"]) != item["model"]:
            got = headers["x-voice-model"]
            counts["failed"].append(f"{item['id']}: {got} spoke, not {item['model']}")
            continue
        if headers.get("x-voice-voice", item["voice"]) != item["voice"]:
            got = headers["x-voice-voice"]
            counts["failed"].append(
                f"{item['id']}: voice {got} spoke, not {item['voice']}"
            )
            continue
        tmp = folder / (name + ".part")
        tmp.write_bytes(wav)
        tmp.replace(folder / name)
        made[item["id"]] = dict(
            {k: v for k, v in item.items() if k != "id"},
            file=name,
            seconds=wav_seconds(wav),
            made_in_s=round(time.monotonic() - t, 1),
        )
        counts["made"] += 1
        tmp = mpath.with_suffix(".json.part")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
        tmp.replace(mpath)
    return counts


def design_voices(cast: dict, lang: str, home: Path) -> list[str]:
    """Make the stand-in voices this language still lacks: a preset voice
    reads the sample (preset_model) or one is designed from its description
    (design_model). One model load for each kind."""
    import engines

    spec = (cast.get("languages") or {}).get(lang) or {}
    found = profiles.load(home)
    want = []
    for sid, per in sorted((cast.get("speakers") or {}).items()):
        sp = per.get(lang) or {}
        if sp.get("voice") and sp.get("sample") and sp["voice"] not in found:
            if sp.get("preset") or sp.get("describe"):
                want.append((sid, sp))
    done = []
    for kind, key in (("preset", "preset_model"), ("describe", "design_model")):
        group = [(sid, sp) for sid, sp in want if sp.get(kind)]
        if kind == "describe":
            group = [(sid, sp) for sid, sp in group if not sp.get("preset")]
        if not group:
            continue
        if not spec.get(key):
            raise SystemExit(f"{cast['name']} has no {key} for {lang}")
        row, eng = profiles._engine(spec[key], tools=kind == "describe")
        try:
            for sid, sp in group:
                with tempfile.TemporaryDirectory() as t:
                    out = Path(t) / "calm.wav"
                    if kind == "preset":
                        audio, rate = eng.synthesize(sp["sample"], sp["preset"], 1.0)
                        out.write_bytes(engines.wav_bytes(audio, rate))
                        how = f"read by {sp['preset']} of {row['id']}"
                    else:
                        eng.design(sp["sample"], sp["describe"], out)
                        how = f"designed with {row['id']}"
                    profiles.save_clip(
                        home,
                        sp["voice"],
                        profiles.CALM,
                        out,
                        sp["sample"],
                        language=lang,
                        label=sp.get("label") or f"{sid} (stand-in)",
                        source=f"stand-in {how} for {cast['name']}"
                        + (f": {sp['describe']}" if kind == "describe" else ""),
                    )
                done.append(sp["voice"])
                print(f"{sp['voice']}: made ({kind})", flush=True)
        finally:
            eng.close()
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="character voices for a game")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    v = sub.add_parser("voices", help="design the stand-in voices still missing")
    v.add_argument("cast")
    v.add_argument("--lang", default="")
    r = sub.add_parser("render", help="make clips of the game's lines")
    r.add_argument("cast")
    r.add_argument("--lang", default="en")
    r.add_argument("--speaker", default="")
    r.add_argument("--only", default="")
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--redo", action="store_true")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--url", default=URL)
    args = ap.parse_args(argv)
    import service

    home = service.models_home() / "voice" / "profiles"
    if args.cmd == "list":
        for p in sorted(CASTS.glob("*.json")):
            c = load(p.stem)
            print(
                f"{p.stem:<16} {', '.join(c.get('languages') or {})}  {c.get('label', '')}"
            )
        return 0
    cast = load(args.cast)
    if args.cmd == "voices":
        for lang in [args.lang] if args.lang else list(cast.get("languages") or {}):
            design_voices(cast, lang, home)
        return 0
    only = tuple(x for x in args.only.split(",") if x)
    res = render(
        cast,
        args.lang,
        home,
        args.url,
        only=only,
        speaker=args.speaker,
        limit=args.limit,
        redo=args.redo,
        dry=args.dry_run,
    )
    for item in res.pop("todo", []):
        print(
            f"{item['id']:<22} {item['speaker']:<8} {item['voice']:<12} {item['said']}"
        )
    fails, why = res.pop("failed"), res.pop("why")
    print(", ".join(f"{k} {v}" for k, v in res.items()), f"failed {len(fails)}")
    for reason, n in sorted(why.items(), key=lambda kv: -kv[1]):
        print(f"  skipped {n}: {reason}")
    for f in fails:
        print("  failed", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    sys.exit(main())
