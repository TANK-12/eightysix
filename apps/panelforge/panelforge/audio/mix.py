"""The audio/render hand-off (CONTRACTS.md): render calls mix_timeline and
muxes the wav it returns with ffmpeg. This is the only function helper-5's
code should need to import from panelforge.audio.

    from panelforge.audio.mix import mix_timeline
    wav = mix_timeline(chapter_dir, timeline_doc, out_wav_path)

Reads script.json from chapter_dir itself (lines' rendered audio, sfx, music)
and places everything according to `timeline_doc` (timeline.json's shape):
shots with a start time and duration, each carrying line refs ({line_id, at})
and sfx ids; a top-level "music" list of music ids from script.json.

Layering: dialogue and SFX are laid straight into the mix; music is rendered
into its own buffer first and ducked under any dialogue region before being
added in, so voices always cut through. A soft limiter runs last so nothing
clips even if several loud things land on the same beat.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import store
from ..music import generate as music_generate
from ..sfx import recipes as sfx_recipes
from . import dsp, policy


def _resolve_audio_path(chapter_dir: Path, ref: str) -> Path | None:
    if not ref:
        return None
    for base in (
        chapter_dir,
        chapter_dir.parent.parent,
        chapter_dir.parent.parent.parent,
    ):
        p = (base / ref).resolve()
        if p.exists():
            return p
    p = Path(ref)
    return p if p.exists() else None


def _load_clip(chapter_dir: Path, ref: str) -> tuple[np.ndarray, int] | None:
    p = _resolve_audio_path(chapter_dir, ref)
    if p is None:
        return None
    return dsp.read_wav(p)


def _sfx_clip(chapter_dir: Path, sfx: dict) -> tuple[np.ndarray, int] | None:
    sound = sfx.get("sound", "")
    if sound.startswith("synth:"):
        name = sound.split(":", 1)[1]
        params = sfx.get("params", {})
        try:
            return sfx_recipes.render(name, **params)
        except KeyError:
            return None
    return _load_clip(chapter_dir, sound)


def _music_clip(
    chapter_dir: Path, music: dict, seconds: float
) -> tuple[np.ndarray, int]:
    track = music.get("track")
    if track:
        loaded = _load_clip(chapter_dir, track)
        if loaded is not None:
            samples, sr = loaded
            if samples.shape[0] / sr < seconds:
                samples = music_generate.tile_to_length(
                    dsp.to_stereo(samples), sr, seconds
                )
            return samples, sr
    mood = music.get("mood", "calm")
    loop, sr = music_generate.generate(mood if mood in music_generate.MOODS else "calm")
    return music_generate.tile_to_length(loop, sr, max(seconds, 1.0)), sr


def _shot_time_range(
    timeline: dict, from_panel: str | None, to_panel: str | None
) -> tuple[float, float]:
    shots = timeline.get("shots", [])
    if not shots:
        return 0.0, 0.0
    if not from_panel and not to_panel:
        start = shots[0]["start"]
        end = max(s["start"] + s["dur"] for s in shots)
        return start, end
    in_range = False
    start = end = None
    for s in shots:
        if s.get("panel_id") == from_panel:
            in_range = True
        if in_range:
            if start is None:
                start = s["start"]
            end = s["start"] + s["dur"]
        if s.get("panel_id") == to_panel:
            break
    if start is None or end is None:
        return 0.0, 0.0
    return start, end


def mix_timeline(chapter_dir: Path, timeline: dict, out_wav: Path) -> Path:
    chapter_dir = Path(chapter_dir)
    script = store.read(
        chapter_dir / "script.json", {"lines": [], "sfx": [], "music": []}
    )
    lines_by_id = {ln["id"]: ln for ln in script.get("lines", [])}
    sfx_by_id = {x["id"]: x for x in script.get("sfx", [])}
    music_by_id = {m["id"]: m for m in script.get("music", [])}

    shots = timeline.get("shots", [])
    total_s = max((s["start"] + s["dur"] for s in shots), default=0.0) + 1.0
    sr = dsp.SR
    n = max(1, int(total_s * sr))
    dialogue_buf = np.zeros((n, 2), dtype=np.float32)
    sfx_buf = np.zeros((n, 2), dtype=np.float32)
    music_buf = np.zeros((n, 2), dtype=np.float32)
    voice_regions: list[tuple[float, float]] = []

    voices = (timeline.get("settings") or {}).get("sound", "full") == "full"
    pol = policy.read()  # sound effects and music only when asked for, or by hand
    for shot in shots:
        shot_start = float(shot.get("start", 0.0))
        for lref in shot.get("lines", []) if voices else []:
            line = lines_by_id.get(lref.get("line_id"))
            if not line or not line.get("audio") or line.get("muted"):
                continue  # muted: keeps its place in the timing, makes no sound
            clip = _load_clip(chapter_dir, line["audio"])
            if clip is None:
                continue
            samples, csr = clip
            samples = dsp.to_stereo(samples)
            at = shot_start + float(lref.get("at", 0.0))
            dsp.mix_into(dialogue_buf, samples, int(at * sr))
            voice_regions.append((at, samples.shape[0] / csr))

        for sfx_id in shot.get("sfx", []):
            sfx = sfx_by_id.get(sfx_id)
            if not sfx or not policy.plays(sfx, "sfx", pol):
                continue
            clip = _sfx_clip(chapter_dir, sfx)
            if clip is None:
                continue
            samples, csr = clip
            samples = dsp.to_stereo(samples)
            at_field = sfx.get("at", "panel-start")
            at = (
                shot_start
                if at_field == "panel-start"
                else shot_start + float(at_field)
            )
            if sfx.get("gain_db"):
                samples = dsp.gain_db(samples, sfx["gain_db"])
            dsp.mix_into(sfx_buf, samples, int(at * sr))

    for music_id in timeline.get("music", []):
        music = music_by_id.get(music_id)
        if not music or not policy.plays(music, "music", pol):
            continue
        start, end = _shot_time_range(
            timeline, music.get("from_panel"), music.get("to_panel")
        )
        seconds = max(1.0, end - start)
        samples, csr = _music_clip(chapter_dir, music, seconds)
        samples = dsp.to_stereo(samples)
        if music.get("gain_db"):
            samples = dsp.gain_db(samples, music["gain_db"])
        dsp.mix_into(music_buf, samples, int(start * sr))

    music_buf = dsp.duck(music_buf, sr, voice_regions, amount_db=-10.0)

    mixed = dialogue_buf + sfx_buf + music_buf
    mixed = dsp.limiter(mixed, ceiling=0.98)
    dsp.write_wav(Path(out_wav), mixed, sr)
    return Path(out_wav)
