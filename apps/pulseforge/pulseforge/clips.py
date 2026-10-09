"""
Clip-pool handling for the montage / AMV scene.

Scans a folder of video files, probes them, detects scene-change timestamps
with ffmpeg (`select='gt(scene,T)'`), and measures a per-clip **motion curve**
(mean absolute frame-to-frame difference on a tiny greyscale decode). The
montage scene uses the song's beat track to decide *when* to cut and the
motion curve to decide *what* each cut shows -- busy shots on loud sections,
still shots on quiet ones.

Not yet: face detection (needs a model dependency), LLM-assisted ordering.
Seams: `scene_cuts()`, `motion_curve()`, `pick_segment()`.
"""

import hashlib
import os
import subprocess

import numpy as np

from .config import AUDIO_EXTS, MOTION_CACHE_DIR, ffmpeg_caps

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".avi", ".ts"}


def scan_pool(path):
    """Return a sorted list of absolute video paths under `path` (one level deep)."""
    if not path or not os.path.isdir(path):
        return []
    out = []
    for root, _dirs, files in os.walk(path):
        for f in files:
            if os.path.splitext(f)[1].lower() in VIDEO_EXTS:
                out.append(os.path.join(root, f))
        # one level deep is enough; keep it predictable
        break
    return sorted(out)


def probe_clip(path):
    ff = ffmpeg_caps()
    dur = 0.0
    if ff["ffprobe"]:
        try:
            r = subprocess.run(
                [
                    ff["ffprobe"],
                    "-v",
                    "quiet",
                    "-of",
                    "csv=p=0",
                    "-show_entries",
                    "format=duration",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            dur = float((r.stdout or "0").strip() or 0)
        except Exception:
            pass
    return {"path": path, "name": os.path.basename(path), "duration": dur}


def scene_cuts(path, threshold=0.3, max_scan_seconds=0):
    """Timestamps (seconds) where ffmpeg sees a scene change. Empty list on any
    failure -- the caller falls back to fixed-interval sampling."""
    ff = ffmpeg_caps()
    if not ff["ffmpeg"]:
        return []
    cmd = [ff["ffmpeg"], "-v", "info"]
    if max_scan_seconds:
        cmd += ["-t", str(max_scan_seconds)]
    cmd += [
        "-i",
        str(path),
        "-vf",
        f"select='gt(scene,{threshold})',showinfo",
        "-f",
        "null",
        "-",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    except Exception:
        return []
    times = []
    for line in (r.stderr or "").splitlines():
        if "pts_time:" in line:
            try:
                times.append(float(line.split("pts_time:")[1].split()[0]))
            except (ValueError, IndexError):
                pass
    return times


_MW, _MH, _MFPS = 64, 36, 8  # tiny greyscale decode for the motion probe


def motion_curve(path, window_s=0.5):
    """A normalised (0..1) motion score per `window_s` seconds of the clip:
    mean absolute frame-to-frame luma difference. Cached on disk by path+mtime.
    Empty array on any failure -- the caller then treats motion as unknown."""
    try:
        st = os.stat(path)
        key = hashlib.sha1(
            f"{path}:{st.st_size}:{int(st.st_mtime)}:{window_s}".encode()
        )
        cache = MOTION_CACHE_DIR / (key.hexdigest()[:20] + ".npy")
    except OSError:
        return np.array([])
    if cache.exists():
        try:
            return np.load(cache)
        except Exception:
            pass
    ff = ffmpeg_caps()
    if not ff["ffmpeg"]:
        return np.array([])
    cmd = [
        ff["ffmpeg"],
        "-v",
        "error",
        "-i",
        str(path),
        "-vf",
        f"fps={_MFPS},scale={_MW}:{_MH},format=gray",
        "-f",
        "rawvideo",
        "-",
    ]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=300).stdout
    except Exception:
        return np.array([])
    frame = _MW * _MH
    n = len(raw) // frame
    if n < 2:
        return np.array([])
    arr = (
        np.frombuffer(raw[: n * frame], dtype=np.uint8)
        .reshape(n, _MH, _MW)
        .astype(np.float32)
    )
    diff = np.abs(np.diff(arr, axis=0)).mean(axis=(1, 2))  # per-frame motion
    per_win = max(1, int(round(window_s * _MFPS)))
    n_win = max(1, len(diff) // per_win)
    curve = np.array(
        [diff[i * per_win : (i + 1) * per_win].mean() for i in range(n_win)]
    )
    if curve.max() > 1e-6:
        curve = curve / np.percentile(curve, 95)
    curve = np.clip(curve, 0.0, 1.0)
    try:
        np.save(cache, curve)
    except Exception:
        pass
    return curve


def segment_motion(curve, start, dur, window_s=0.5):
    """Mean motion of the [start, start+dur] window of a clip, from its curve."""
    if curve is None or len(curve) == 0:
        return 0.5  # unknown -> neutral
    a = int(start / window_s)
    b = max(a + 1, int((start + dur) / window_s))
    seg = curve[a:b]
    return float(seg.mean()) if len(seg) else float(curve.mean())


def pick_segment(clip, want, cuts, cursor):
    """Choose a [start, start+want] window inside `clip`.

    Prefers to start on a detected scene cut that leaves room for `want`
    seconds; otherwise walks forward through the clip from `cursor`."""
    dur = clip["duration"]
    if dur <= 0.2:
        return 0.0, max(0.2, want)
    usable = [t for t in cuts if t + want <= dur]
    if usable:
        # first cut at/after the cursor, wrapping around
        ahead = [t for t in usable if t >= cursor]
        start = ahead[0] if ahead else usable[0]
    else:
        start = cursor % max(0.1, dur - want) if dur > want else 0.0
    return max(0.0, min(start, max(0.0, dur - want))), min(want, dur)


__all__ = [
    "scan_pool",
    "probe_clip",
    "scene_cuts",
    "motion_curve",
    "segment_motion",
    "pick_segment",
    "VIDEO_EXTS",
    "AUDIO_EXTS",
]
