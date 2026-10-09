"""
The timeline: several songs, several backgrounds, and how they line up.

A v3 project is a **playlist** of songs and a list of **shots**. This module is
what turns those two lists into a plan the renderer can execute:

* `build_audio()` glues the playlist into one track -- butted together, with a
  gap, or overlapped with a crossfade -- and reports where each song starts, so
  a title can appear exactly when its song does.
* `plan_shots()` places the backgrounds along that track. A shot can hold for
  one song or for a fixed number of seconds, and if there are fewer shots than
  songs the list simply cycles.
* `text_filter()` builds the `drawtext` chain, one entry per song with an
  `enable` window, which is how the caption changes as the mix moves on.

Nothing here renders pixels. It produces numbers and filter strings; the
renderer in `render.py` does the work.
"""

import math
import os
import re
import subprocess

from . import ambience
from .config import ffmpeg_caps
from .ffrunner import probe_media

TRANSITIONS = {
    "cut": None,
    "dissolve": "fade",
    "fade_black": "fadeblack",
    "fade_white": "fadewhite",
    "wipe_left": "wipeleft",
    "wipe_right": "wiperight",
    "slide_left": "slideleft",
    "slide_up": "slideup",
    "circle": "circleopen",
    "smooth": "smoothleft",
    "pixelize": "pixelize",
}


def transitions_as_list():
    return [
        {"id": k, "label": k.replace("_", " ").capitalize(), "xfade": v}
        for k, v in TRANSITIONS.items()
    ]


# --------------------------------------------------------------------------
# audio
# --------------------------------------------------------------------------
def song_durations(paths):
    return [max(0.0, float(probe_media(p)["duration"])) for p in paths]


# --------------------------------------------------------------------------
# levelling
# --------------------------------------------------------------------------
_LOUDNESS_CACHE: dict = {}


def measure_loudness(path):
    """Integrated loudness in LUFS, or None if it cannot be measured.

    Cached by path and mtime: a playlist gets measured once, not on every
    render, and a re-encoded file is measured again.
    """
    try:
        stamp = (os.path.getmtime(path), os.path.getsize(path))
    except OSError:
        return None
    key = (str(path), stamp)
    if key in _LOUDNESS_CACHE:
        return _LOUDNESS_CACHE[key]

    ff = ffmpeg_caps()["ffmpeg"]
    if not ff:
        return None
    r = subprocess.run(
        [
            ff,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "ebur128",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    found = re.findall(r"^\s*I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", r.stderr, re.M)
    value = float(found[-1]) if found else None
    _LOUDNESS_CACHE[key] = value
    return value


def auto_gains(paths, target=None, limit=18.0):
    """The dB adjustment each song needs so the playlist sits level with itself.

    The job here is **relative**: make the tracks match each other. Absolute
    level is already handled by the `loudnorm` at the end of the render, and
    aiming every track at an absolute figure makes the cap fight the goal -- a
    playlist that is uniformly quiet would have every track clamped at the limit
    and stay exactly as uneven as it started. Levelling to the playlist's own
    median keeps the corrections small and symmetric.

    The cap still matters: a track needing more than `limit` dB is more likely
    mis-measured, or nearly silent, than genuinely that far off. 18 dB rather
    than something tighter, because a playlist gathered from different sources
    really can span that much, and a cap that cannot reach the correction is
    just a slower way of not levelling.
    """
    measured = [measure_loudness(p) for p in paths]
    usable = [m for m in measured if m is not None]
    if not usable:
        return [0.0] * len(paths)
    if target is None:
        target = float(sorted(usable)[len(usable) // 2])  # median
    return [
        0.0 if m is None else round(max(-limit, min(limit, float(target) - m)), 2)
        for m in measured
    ]


def audio_spans(durations, gap=0.0, crossfade=0.0):
    """Where each song sits on the finished timeline, and the total length."""
    spans = []
    t = 0.0
    for i, d in enumerate(durations):
        spans.append({"start": t, "duration": d, "end": t + d})
        t += d
        if i < len(durations) - 1:
            t += float(gap) - float(crossfade)
    return spans, max(0.0, t)


def expand_for_target(paths, durations, gap, crossfade, target_seconds):
    """Repeat the playlist until it reaches a target length.

    Six tracks becoming three hours is how these videos are actually made, and
    it needs no new files -- just the same list again. Returns the expanded
    list and how many passes it took.
    """
    target = float(target_seconds or 0.0)
    if target <= 0 or not paths:
        return list(paths), 1
    _spans, one_pass = audio_spans(durations, gap, crossfade)
    if one_pass <= 0.5:
        return list(paths), 1
    passes = max(1, min(400, math.ceil(target / one_pass)))
    return list(paths) * passes, passes


def mix_ambience(music_path, out_path, bed, level=0.25, seed=0, log=None):
    """Lay a generated ambient bed under the music.

    Thirty seconds is synthesised and repeated by ffmpeg, so an eight-hour video
    costs the same thirty seconds of numpy. `normalize=0` on the mix matters --
    without it `amix` halves both inputs and the music comes out quiet.
    """
    log = log or (lambda s: None)
    if not bed or bed == "none":
        return music_path
    ff = ffmpeg_caps()["ffmpeg"]
    amb_wav = os.path.join(os.path.dirname(str(out_path)), "ambience.wav")
    log(f"generating {bed} to sit under the music…")
    ambience.write_wav(bed, amb_wav, seconds=ambience.DEFAULT_SECONDS, seed=seed)

    vol = max(0.0, min(1.5, float(level)))
    cmd = [
        ff,
        "-y",
        "-i",
        str(music_path),
        "-stream_loop",
        "-1",
        "-i",
        amb_wav,
        "-filter_complex",
        f"[1:a]volume={vol:.3f}[amb];"
        f"[0:a][amb]amix=inputs=2:duration=first:normalize=0[out]",
        "-map",
        "[out]",
        "-c:a",
        "flac",
        "-compression_level",
        "3",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log(f"could not mix the ambience in ({r.stderr[-200:]}); carrying on without")
        return music_path
    return str(out_path)


def repeat_audio(path, out_path, passes, one_pass_seconds, log=None):
    """Repeat a finished pass to reach the target length.

    `-stream_loop` rather than a filter graph with twenty copies of the same
    input: the encoder sees one pass and repeats the decoded frames, so making a
    three-hour version of a ten-minute mix costs almost nothing.
    """
    log = log or (lambda s: None)
    if passes <= 1:
        return path, one_pass_seconds
    ff = ffmpeg_caps()["ffmpeg"]
    total = one_pass_seconds * passes
    how_long = (
        f"{total / 3600:.1f} hours" if total >= 3600 else f"{total / 60:.0f} minutes"
    )
    log(f"repeating the mix {passes}x to reach {how_long}…")
    cmd = [
        ff,
        "-y",
        "-stream_loop",
        str(int(passes) - 1),
        "-i",
        str(path),
        "-t",
        f"{total:.3f}",
        "-c:a",
        "flac",
        "-compression_level",
        "3",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log(f"could not repeat the mix ({r.stderr[-200:]}); using one pass")
        return path, one_pass_seconds
    return str(out_path), total


def repeat_spans(spans, passes, one_pass_seconds):
    """The same song list again for each pass, shifted along the timeline."""
    if passes <= 1:
        return list(spans)
    out = []
    for k in range(int(passes)):
        shift = k * one_pass_seconds
        for sp in spans:
            out.append(
                {
                    "start": sp["start"] + shift,
                    "duration": sp["duration"],
                    "end": sp["end"] + shift,
                    "pass": k,
                }
            )
    return out


def build_audio(paths, out_path, gap=0.0, crossfade=0.0, log=None, gains=None):
    """One audio file from the playlist. Returns (path, spans, duration).

    A single song with nothing to do to it is used where it lies -- no point
    rewriting an hour of audio to change nothing.
    """
    log = log or (lambda s: None)
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        raise RuntimeError("this project has no songs yet")

    durations = song_durations(paths)
    gap = max(0.0, float(gap or 0.0))
    crossfade = max(0.0, float(crossfade or 0.0))
    if crossfade > 0:
        crossfade = min(crossfade, min(durations) * 0.45 if durations else 0.0)
        gap = 0.0
    spans, total = audio_spans(durations, gap, crossfade)

    gains = list(gains or [])
    has_gain = any(abs(float(g or 0.0)) > 0.05 for g in gains)
    if len(paths) == 1 and not has_gain:
        return paths[0], spans, total

    ff = ffmpeg_caps()["ffmpeg"]
    cmd = [ff, "-y"]
    for p in paths:
        cmd += ["-i", str(p)]

    norm = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    parts = []
    for k in range(len(paths)):
        tail = f",apad=pad_dur={gap}" if (gap > 0 and k < len(paths) - 1) else ""
        # per-song trim goes on before anything else, so the join and the final
        # loudnorm both see tracks that already sit at the same level
        gain = float(gains[k]) if k < len(gains) and gains[k] else 0.0
        lead = f"volume={gain:.2f}dB," if abs(gain) > 0.05 else ""
        parts.append(f"[{k}:a]{lead}{norm}{tail}[a{k}]")

    if len(paths) == 1:
        parts.append("[a0]anull[aout]")
        last = "aout"
    elif crossfade > 0:
        prev = "a0"
        for k in range(1, len(paths)):
            label = "aout" if k == len(paths) - 1 else f"ax{k}"
            parts.append(
                f"[{prev}][a{k}]acrossfade=d={crossfade:.3f}:c1=tri:c2=tri[{label}]"
            )
            prev = label
        last = prev
    else:
        parts.append(
            "".join(f"[a{k}]" for k in range(len(paths)))
            + f"concat=n={len(paths)}:v=0:a=1[aout]"
        )
        last = "aout"

    log(f"joining {len(paths)} songs into one {total / 60:.1f} minute track…")
    cmd += [
        "-filter_complex",
        ";".join(parts),
        "-map",
        f"[{last}]",
        "-c:a",
        "flac",
        "-compression_level",
        "3",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"could not join the playlist: {r.stderr[-500:]}")
    return str(out_path), spans, total


# --------------------------------------------------------------------------
# shots along the timeline
# --------------------------------------------------------------------------
def plan_shots(shots, spans, total, default_loop=12.0):
    """Place each shot on the timeline.

    `hold` is either "song" -- this shot lasts exactly as long as the song at
    its position -- or a number of seconds. Fewer shots than songs is fine and
    common: the list cycles. The last shot is always stretched to cover any
    remainder so the video never runs out of picture before it runs out of
    music.
    """
    shots = [dict(s) for s in (shots or []) if s]
    if not shots:
        shots = [{}]
    if total <= 0:
        return []

    placed = []
    t = 0.0
    i = 0
    while t < total - 0.05 and len(placed) < 400:
        shot = dict(shots[i % len(shots)])
        hold = shot.get("hold", "song")
        if hold == "song" and spans:
            dur = spans[min(i, len(spans) - 1)]["duration"]
        else:
            try:
                dur = float(hold)
            except (TypeError, ValueError):
                dur = 60.0
        dur = max(1.0, dur)
        shot["index"] = len(placed)
        shot["start"] = t
        shot["duration"] = min(dur, total - t)
        shot["loop_seconds"] = float(shot.get("loop_seconds") or default_loop)
        shot["transition"] = shot.get("transition", "dissolve")
        shot["transition_s"] = float(shot.get("transition_s", 1.5) or 0.0)
        placed.append(shot)
        t += shot["duration"]
        i += 1

    if placed:
        placed[-1]["duration"] = max(1.0, total - placed[-1]["start"])
    return placed


# --------------------------------------------------------------------------
# captions that change with the song
# --------------------------------------------------------------------------
def _esc(s):
    return (
        str(s or "")
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "’")
        .replace("%", "\\%")
    )


_POS = {
    "bottom-left": ("{pad}", "h-th-{pad}"),
    "bottom-center": ("(w-tw)/2", "h-th-{pad}"),
    "top-left": ("{pad}", "{pad}"),
    "center": ("(w-tw)/2", "(h-th)/2"),
}


def text_filter(cards, spans, out_w, out_h, position="bottom-left", size="m", fade=1.2):
    """A `drawtext` per song, each only enabled while its song is playing."""
    if not cards or not spans:
        return ""
    scale = {"s": 0.026, "m": 0.036, "l": 0.052}.get(str(size), 0.036)
    title_px = max(14, int(out_h * scale))
    sub_px = max(12, int(title_px * 0.62))
    pad = max(18, int(out_h * 0.05))
    ax, ay = _POS.get(str(position), _POS["bottom-left"])
    ax = ax.format(pad=pad)
    ay = ay.format(pad=pad)

    parts = []
    # with a repeating playlist this list can be hundreds long; past a point a
    # filter graph of that size costs more than the captions are worth
    for i, span in enumerate(spans[:300]):
        card = cards[i % len(cards)] if cards else {}
        title = _esc(card.get("title"))
        sub = _esc(card.get("subtitle"))
        if not title and not sub:
            continue
        t0 = span["start"]
        t1 = span["end"]
        # hold the caption for the first stretch of each song, then let it go
        show = min(t1 - t0, max(6.0, min(14.0, (t1 - t0) * 0.25)))
        win = f"between(t,{t0:.2f},{t0 + show:.2f})"
        alpha = (
            f"if(lt(t-{t0:.2f},{fade}),(t-{t0:.2f})/{fade},"
            f"if(gt(t-{t0:.2f},{show - fade:.2f}),"
            f"({show:.2f}-(t-{t0:.2f}))/{fade},1))"
        )
        if title:
            parts.append(
                f"drawtext=text='{title}':fontcolor=white:fontsize={title_px}"
                f":x={ax}:y={ay}-{sub_px + 8 if sub else 0}:enable='{win}'"
                f":alpha='{alpha}':shadowcolor=black@0.6:shadowx=2:shadowy=2"
            )
        if sub:
            parts.append(
                f"drawtext=text='{sub}':fontcolor=white@0.82:fontsize={sub_px}"
                f":x={ax}:y={ay}:enable='{win}'"
                f":alpha='{alpha}':shadowcolor=black@0.6:shadowx=2:shadowy=2"
            )
    return ",".join(parts)
