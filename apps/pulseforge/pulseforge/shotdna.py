"""
What is actually *in* a video clip -- measured, so the editor can choose shots
on more than "this one is busy".

`clips.motion_curve()` already answers one question: how much is moving. That
is enough to put busy footage on the loud part of a song, and not enough for
anything else. To cut like an editor you want to know whether a shot is a
close-up or a landscape, which way the camera is travelling, whether it is warm
or cold, whether it is sharp or a smeared mess, and what colours are in it.

One decode pass produces all of it. The clip is streamed out of ffmpeg at 8 fps
and 256x144 -- small enough that a twenty-minute file costs seconds, large
enough that edges and colour survive -- and every half second becomes one
`segment` with:

    motion       how much changed, 0..1
    flow_dx/dy   which way, in frame-widths per second (camera travel)
    flow_mag     how fast, regardless of direction
    brightness   mean luma, 0..1
    contrast     spread of luma, 0..1
    saturation   0..1
    warmth       -1 cold .. +1 warm
    palette      three dominant colours
    detail       edge density, 0..1
    subject      how concentrated the interest is in the middle, 0..1
    sharpness    0..1; low means blurred or motion-smeared
    shot_scale   "close" | "medium" | "wide"
    action       one number combining motion, travel and edge churn
    quality      is this frame worth showing at all

**There is no face detection here, deliberately.** OpenCV's stock cascade is
trained on photographs of real faces and is close to useless on animation,
which is the footage this is mostly for, and the anime-trained cascades are
third-party model files. So shot scale is estimated from the picture's own
structure instead: a close-up is large smooth areas with the detail bunched in
the middle, a wide shot is fine detail spread evenly to the edges. That works
on live action and animation alike and needs no model.

Also here: letterbox detection, so black bars are cropped rather than scaled
up, and internal scene cuts read off the same pass rather than a second full
decode.

Everything is cached on disk by path, size and mtime, so a clip folder is
analysed once.
"""

import hashlib
import json
import os
import subprocess

import numpy as np

from .config import DATA_ROOT, ffmpeg_caps

try:  # pragma: no cover - exercised by every real call; absence is the branch
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

SHOT_CACHE_DIR = DATA_ROOT / "cache" / "shots"
SHOT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_FPS = 8.0
SAMPLE_W, SAMPLE_H = 256, 144
FLOW_W, FLOW_H = 128, 72
WINDOW_S = 0.5
CACHE_VERSION = 2  # bump to invalidate every cached analysis


def cache_path(path):
    try:
        st = os.stat(path)
        key = f"{path}:{st.st_size}:{int(st.st_mtime)}:v{CACHE_VERSION}"
    except OSError:
        key = f"{path}:missing:v{CACHE_VERSION}"
    return SHOT_CACHE_DIR / (hashlib.sha1(key.encode()).hexdigest()[:20] + ".json")


# --------------------------------------------------------------------------
# decode
# --------------------------------------------------------------------------
def _stream_frames(path, max_seconds=0):
    """Yield (H, W, 3) uint8 frames at SAMPLE_FPS, streamed.

    Read a frame at a time rather than capturing the whole decode: at this size
    a long clip is a gigabyte of pixels, and holding it would cost more memory
    than the renderer itself uses."""
    ff = ffmpeg_caps()["ffmpeg"]
    if not ff:
        return
    cmd = [ff, "-v", "error"]
    if max_seconds:
        cmd += ["-t", str(float(max_seconds))]
    cmd += [
        "-i",
        str(path),
        "-vf",
        f"fps={SAMPLE_FPS},scale={SAMPLE_W}:{SAMPLE_H}:flags=bilinear",
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "-",
    ]
    nbytes = SAMPLE_W * SAMPLE_H * 3
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=nbytes * 4
    )
    try:
        while True:
            buf = proc.stdout.read(nbytes) if proc.stdout else b""
            if not buf or len(buf) < nbytes:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape(SAMPLE_H, SAMPLE_W, 3)
    finally:
        try:
            if proc.stdout:
                proc.stdout.close()
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            pass


# --------------------------------------------------------------------------
# per-frame measurements
# --------------------------------------------------------------------------
def _luma(rgb):
    f = rgb.astype(np.float32)
    return 0.2126 * f[..., 0] + 0.7152 * f[..., 1] + 0.0722 * f[..., 2]


def _detail_and_subject(gray):
    """(edge density 0..1, how centre-weighted those edges are 0..1).

    Two numbers off one edge map. Density says how much fine structure the
    frame has, which separates a landscape from a face. Concentration says
    where that structure sits: a portrait puts it in the middle third and
    leaves the corners empty, a landscape spreads it everywhere. Together they
    place a shot on the close-to-wide scale without knowing what a face is."""
    g = gray.astype(np.uint8)
    if cv2 is not None:
        edges = cv2.Canny(g, 60, 160) > 0
        gx = cv2.Sobel(gray.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
    else:  # pragma: no cover - numpy fallback keeps the module importable
        gx = np.diff(gray, axis=1, prepend=gray[:, :1])
        gy = np.diff(gray, axis=0, prepend=gray[:1, :])
        edges = (np.abs(gx) + np.abs(gy)) > 40
    density = float(edges.mean())

    # Where the interest sits is measured on the *continuous* gradient, not on
    # the edge map. A face, a soft-focus subject or a painted background all
    # have gently curved shading that Canny reports as nothing at all -- the
    # first test close-up came back with literally zero edges and was filed as
    # a wide shot. Gradient magnitude still sees the form.
    mag = np.hypot(gx, gy)
    h, w = mag.shape
    cy, cx = np.mgrid[0:h, 0:w]
    # a soft centre window rather than a hard middle third, so a subject
    # slightly off-centre is not scored as though it were in the corner
    wy = np.exp(-0.5 * (((cy - h / 2) / (h * 0.28)) ** 2))
    wx = np.exp(-0.5 * (((cx - w / 2) / (w * 0.28)) ** 2))
    win = wy * wx
    tot = float(mag.sum())
    centred = float((mag * win).sum() / tot) if tot > 1e-6 else 0.0
    baseline = float(win.mean())
    subject = float(np.clip((centred - baseline) / max(1e-6, 1.0 - baseline), 0.0, 1.0))
    return density, subject


def _sharpness(gray):
    """Laplacian variance, squashed to 0..1. Low means out of focus, motion
    smeared, or a dissolve caught mid-way -- all things not to cut to."""
    if cv2 is not None:
        lap = cv2.Laplacian(gray.astype(np.uint8), cv2.CV_32F)
    else:  # pragma: no cover
        lap = np.diff(gray, n=2, axis=1, prepend=gray[:, :1], append=gray[:, -1:])
    v = float(lap.var())
    return float(np.clip(v / 400.0, 0.0, 1.0))


def _palette(rgb, k=3):
    """The k dominant colours, by k-means on a subsample."""
    px = rgb.reshape(-1, 3)[::17].astype(np.float32)
    if px.shape[0] < k:
        return [[128, 128, 128]] * k
    if cv2 is not None:
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 8, 1.0)
        # OpenCV's own stubs type `bestLabels` and `flow` as UMat, but the
        # documented call passes None to let OpenCV allocate them.
        _c, labels, centers = cv2.kmeans(  # type: ignore[call-overload]
            px, k, None, crit, 2, cv2.KMEANS_PP_CENTERS  # type: ignore[arg-type]
        )
        counts = np.bincount(labels.ravel(), minlength=k)
        order = np.argsort(-counts)
        return [[int(v) for v in centers[i]] for i in order]
    means = px.mean(axis=0)  # pragma: no cover
    return [[int(v) for v in means]] * k  # pragma: no cover


def _flow(prev_gray, gray):
    """Mean optical flow, in frame-widths per second.

    This is what makes a whip-pan transition possible: if the outgoing shot is
    travelling left and the incoming one is too, a blurred wipe between them
    reads as one continuous movement instead of an effect."""
    if cv2 is None or prev_gray is None:  # pragma: no cover
        return 0.0, 0.0
    a = cv2.resize(prev_gray.astype(np.uint8), (FLOW_W, FLOW_H))
    b = cv2.resize(gray.astype(np.uint8), (FLOW_W, FLOW_H))
    flow = cv2.calcOpticalFlowFarneback(  # type: ignore[call-overload]
        a, b, None, 0.5, 2, 15, 2, 5, 1.2, 0  # type: ignore[arg-type]
    )
    dx = float(np.median(flow[..., 0])) / FLOW_W * SAMPLE_FPS
    dy = float(np.median(flow[..., 1])) / FLOW_H * SAMPLE_FPS
    return dx, dy


def detect_letterbox(frames_sample):
    """{top,bottom,left,right} as fractions of the frame that are always black.

    Anime rips and phone footage both arrive with bars baked in. Scaling them
    up puts black stripes in the middle of a montage, so the montage crops
    them off instead."""
    if not frames_sample:
        return {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
    stack = np.stack([_luma(f) for f in frames_sample])
    rows = stack.max(axis=(0, 2))  # brightest this row ever gets
    cols = stack.max(axis=(0, 1))
    thresh = 26.0

    def _run(vec):
        top = 0
        while top < len(vec) and vec[top] < thresh:
            top += 1
        bot = 0
        while bot < len(vec) - top and vec[len(vec) - 1 - bot] < thresh:
            bot += 1
        return top, bot

    t, b = _run(rows)
    lft, rgt = _run(cols)
    h, w = len(rows), len(cols)
    # Never claim more than a third of the frame -- a genuinely dark shot must
    # not be cropped into nothing.
    cap_h, cap_w = h // 3, w // 3
    return {
        "top": round(min(t, cap_h) / h, 4),
        "bottom": round(min(b, cap_h) / h, 4),
        "left": round(min(lft, cap_w) / w, 4),
        "right": round(min(rgt, cap_w) / w, 4),
    }


# --------------------------------------------------------------------------
# the whole clip
# --------------------------------------------------------------------------
def _shot_scale(detail, subject):
    """Close, medium or wide, from how fine the detail is and where it sits.

    Detail is checked first and on its own. A frame with almost no fine
    structure is a big soft form filling the screen -- a face, a sky, a wall --
    and that is a close shot whatever the gradient is doing. Only once there is
    enough structure to place does it matter *where* that structure sits."""
    if detail < 0.045:
        return "close"
    if detail > 0.13:
        return "wide"
    if subject > 0.10:
        return "close"
    if subject < 0.04:
        return "wide"
    return "medium"


ACC_KEYS = (
    "n",
    "motion",
    "dx",
    "dy",
    "bright",
    "contrast",
    "sat",
    "warm",
    "detail",
    "subject",
    "sharp",
)


def _new_acc():
    """A fresh running total for one half-second window."""
    return {k: 0.0 for k in ACC_KEYS}


def analyse_clip(path, max_seconds=0, use_cache=True):
    """Everything above for one video file. Cached; safe to call repeatedly."""
    cp = cache_path(path)
    if use_cache and cp.exists():
        try:
            return json.loads(cp.read_text("utf-8"))
        except Exception:
            pass

    per_win = max(1, int(round(WINDOW_S * SAMPLE_FPS)))
    segs = []
    acc = _new_acc()
    acc_palette = [[128, 128, 128]]
    prev_gray = None
    n_frames = 0
    first_frames = []
    cuts = []

    def _flush(start_idx):
        if acc["n"] == 0:
            return
        n = acc["n"]
        d = acc["detail"] / n
        subj = acc["subject"] / n
        seg = {
            "start": round(start_idx / SAMPLE_FPS, 3),
            "end": round((start_idx + n) / SAMPLE_FPS, 3),
            "motion": round(float(np.clip(acc["motion"] / n / 40.0, 0, 1)), 4),
            "flow_dx": round(acc["dx"] / n, 4),
            "flow_dy": round(acc["dy"] / n, 4),
            "flow_mag": round(float(np.hypot(acc["dx"] / n, acc["dy"] / n)), 4),
            "brightness": round(acc["bright"] / n / 255.0, 4),
            "contrast": round(float(np.clip(acc["contrast"] / n / 80.0, 0, 1)), 4),
            "saturation": round(acc["sat"] / n, 4),
            "warmth": round(acc["warm"] / n, 4),
            "detail": round(d, 4),
            "subject": round(subj, 4),
            "sharpness": round(acc["sharp"] / n, 4),
            "palette": acc_palette,
            "shot_scale": _shot_scale(d, subj),
        }
        seg["action"] = round(
            float(
                np.clip(0.6 * seg["motion"] + 0.4 * min(1.0, seg["flow_mag"] * 3), 0, 1)
            ),
            4,
        )
        seg["quality"] = round(
            float(np.clip(0.55 * seg["sharpness"] + 0.45 * seg["contrast"], 0, 1)), 4
        )
        segs.append(seg)

    for i, rgb in enumerate(_stream_frames(path, max_seconds)):
        gray = _luma(rgb)
        if i % per_win == 0:
            _flush(i - per_win)
            acc = _new_acc()
            acc_palette = _palette(rgb)
        if len(first_frames) < 24 and i % 7 == 0:
            first_frames.append(rgb.copy())

        det, subj = _detail_and_subject(gray)
        f = rgb.astype(np.float32)
        mx = f.max(axis=2)
        mn = f.min(axis=2)
        acc["n"] += 1
        acc["detail"] += det
        acc["subject"] += subj
        acc["sharp"] += _sharpness(gray)
        acc["bright"] += float(gray.mean())
        acc["contrast"] += float(gray.std())
        acc["sat"] += float(np.mean((mx - mn) / np.maximum(mx, 1.0)))
        acc["warm"] += float(
            np.clip((f[..., 0].mean() - f[..., 2].mean()) / 64.0, -1, 1)
        )
        if prev_gray is not None:
            d = float(np.abs(gray - prev_gray).mean())
            acc["motion"] += d
            dx, dy = _flow(prev_gray, gray)
            acc["dx"] += dx
            acc["dy"] += dy
            # A frame that shares almost nothing with the one before it is a
            # cut. Read here for free rather than paying for a second decode.
            if d > 32.0:
                cuts.append(round(i / SAMPLE_FPS, 3))
        prev_gray = gray
        n_frames = i + 1

    _flush(max(0, (n_frames - 1) // per_win * per_win))

    out = {
        "path": str(path),
        "name": os.path.basename(str(path)),
        "duration": round(n_frames / SAMPLE_FPS, 3),
        "segments": segs,
        "cuts": cuts,
        "letterbox": detect_letterbox(first_frames),
        "version": CACHE_VERSION,
        "ok": bool(segs),
    }
    try:
        cp.write_text(json.dumps(out), encoding="utf-8")
    except Exception:
        pass
    return out


def segment_at(dna, t):
    """The segment covering time `t`, or None."""
    for s in dna.get("segments", []):
        if s["start"] <= t < s["end"]:
            return s
    segs = dna.get("segments") or []
    return segs[-1] if segs else None


def window_stats(dna, start, dur):
    """The average of every measurement over [start, start+dur].

    This is what the shot picker scores against: a candidate segment of a clip,
    summarised the same way a moment of the song is."""
    segs = [
        s
        for s in dna.get("segments", [])
        if s["end"] > start and s["start"] < start + dur
    ]
    if not segs:
        return None
    out = {}
    for k in (
        "motion",
        "flow_dx",
        "flow_dy",
        "flow_mag",
        "brightness",
        "contrast",
        "saturation",
        "warmth",
        "detail",
        "subject",
        "sharpness",
        "action",
        "quality",
    ):
        out[k] = float(np.mean([s.get(k, 0.0) for s in segs]))
    scales = [s.get("shot_scale", "medium") for s in segs]
    out["shot_scale"] = max(set(scales), key=scales.count)
    out["palette"] = segs[0].get("palette", [[128, 128, 128]])
    return out


def describe(stats):
    """A short plain-English label for the editor, e.g. "close-up, panning
    left, warm". Shown next to a shot so the automatic choice is legible."""
    if not stats:
        return "unknown"
    bits = [
        {"close": "close-up", "medium": "medium shot", "wide": "wide shot"}.get(
            stats.get("shot_scale", "medium"), "shot"
        )
    ]
    dx, dy = stats.get("flow_dx", 0.0), stats.get("flow_dy", 0.0)
    if stats.get("flow_mag", 0) > 0.06:
        if abs(dx) >= abs(dy):
            bits.append("panning right" if dx > 0 else "panning left")
        else:
            bits.append("tilting down" if dy > 0 else "tilting up")
    elif stats.get("motion", 0) > 0.35:
        bits.append("busy")
    elif stats.get("motion", 0) < 0.08:
        bits.append("still")
    if stats.get("warmth", 0) > 0.18:
        bits.append("warm")
    elif stats.get("warmth", 0) < -0.18:
        bits.append("cool")
    if stats.get("brightness", 0.5) < 0.22:
        bits.append("dark")
    if stats.get("sharpness", 1.0) < 0.12:
        bits.append("soft")
    return ", ".join(bits)


def analyse_pool(paths, max_seconds=0, progress=None):
    """Analyse a whole folder, reporting progress. Cached files cost nothing."""
    out = {}
    for i, p in enumerate(paths):
        try:
            out[p] = analyse_clip(p, max_seconds=max_seconds)
        except Exception as e:  # one unreadable file must not stop the pool
            out[p] = {"path": p, "segments": [], "ok": False, "error": str(e)}
        if progress:
            progress((i + 1) / max(1, len(paths)))
    return out


__all__ = [
    "analyse_clip",
    "analyse_pool",
    "segment_at",
    "window_stats",
    "describe",
    "detect_letterbox",
    "cache_path",
    "SHOT_CACHE_DIR",
]
