"""
Using a video clip as a shot's background.

Half the background-music videos out there are not a still at all -- they loop a
short clip. This is that, and it keeps the economics of the rest of the app:
frames are **streamed** out of one ffmpeg pipe rather than decoded into memory,
so a bed costs one frame of RAM rather than a gigabyte, exactly like the
per-frame decode `clips.motion_curve()` already does.

The interesting part is making an arbitrary clip loop. Almost nothing you find
loops on its own, so the last stretch is cross-dissolved into the first:

    decode the B frames that come *after* the bed  -> the tail
    stream the bed's N frames                      -> the body
    fade the tail out across the body's first B frames

Then the bed's last frame is followed, on repeat, by a picture that already
contains the frame that came after it -- so the cut lands in the middle of a
dissolve instead of on a jump. It costs one extra short decode and B frames of
buffer.

The camera drift, the marked regions, the emitters, the depth of field and the
grade all still apply on top. A video background is just a different source of
pixels for `layers.Backdrop`.
"""

import subprocess

import numpy as np

from .config import ffmpeg_caps
from .ffrunner import probe_media

MAX_BLEND_FRAMES = 24
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".gif")


def is_video(path):
    return str(path).lower().endswith(VIDEO_EXTS)


def _decode_cmd(path, w, h, fps, start, count, loop_input):
    ff = ffmpeg_caps()["ffmpeg"]
    if not ff:
        raise RuntimeError("ffmpeg not found on PATH")
    cmd = [ff, "-v", "error"]
    if loop_input:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-ss", f"{max(0.0, float(start)):.3f}", "-i", str(path)]
    # cover the frame the same way a still background is covered, then crop
    cmd += [
        "-vf",
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},fps={fps}",
        "-frames:v",
        str(int(count)),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    return cmd


def _read_frames(cmd, w, h, count):
    """Run a decode and yield frames as they arrive."""
    size = w * h * 3
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        for _ in range(count):
            buf = proc.stdout.read(size) if proc.stdout else b""
            if len(buf) < size:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()


class VideoSource:
    """A clip, delivered one frame at a time and made to loop."""

    def __init__(self, path, w, h, fps, n_frames, start=0.0, blend=0.5):
        self.path = str(path)
        self.w, self.h = int(w), int(h)
        self.fps = float(fps)
        self.n_frames = max(1, int(n_frames))
        self.start = float(start)

        info = probe_media(self.path)
        self.duration = float(info.get("duration") or 0.0)
        needed = (self.n_frames / self.fps) + float(blend)
        # short clip? let ffmpeg repeat the input rather than running dry
        self.loop_input = self.duration > 0 and self.duration < self.start + needed

        self.blend_frames = int(
            min(MAX_BLEND_FRAMES, max(0, round(float(blend) * self.fps)))
        )
        if self.blend_frames * 3 >= self.n_frames:
            self.blend_frames = max(0, self.n_frames // 3)

    def _tail(self):
        """The frames just past the end of the bed, used to hide the wrap."""
        if self.blend_frames <= 0:
            return []
        at = self.start + self.n_frames / self.fps
        cmd = _decode_cmd(
            self.path, self.w, self.h, self.fps, at, self.blend_frames, True
        )
        return [f.copy() for f in _read_frames(cmd, self.w, self.h, self.blend_frames)]

    def frames(self):
        """`n_frames` frames as float32, with the loop seam dissolved away."""
        tail = self._tail()
        cmd = _decode_cmd(
            self.path,
            self.w,
            self.h,
            self.fps,
            self.start,
            self.n_frames,
            self.loop_input,
        )
        blank = np.zeros((self.h, self.w, 3), dtype=np.float32)
        produced = 0
        for i, frame in enumerate(_read_frames(cmd, self.w, self.h, self.n_frames)):
            out = frame.astype(np.float32)
            if i < len(tail):
                # tail fully visible at the wrap, gone by the end of the blend
                a = 1.0 - (i / max(1, len(tail)))
                out = out * (1.0 - a) + tail[i].astype(np.float32) * a
            produced += 1
            yield out
        # a truncated decode must not shorten the bed
        for _ in range(self.n_frames - produced):
            yield blank.copy()
