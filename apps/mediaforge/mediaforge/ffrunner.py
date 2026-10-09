"""
ffmpeg / ffprobe wrapper.

* probe_streams()  -> structured audio / subtitle / video track lists
* build_encode_args() -> the -c:v / preset / hw-accel flags for the chosen encoder
* FFJob            -> runs ffmpeg with `-progress pipe:1`, parses % from duration,
                      streams log lines, and can be KILLED instantly.
"""

import json
import re
import signal
import subprocess
import threading
import time

from .config import ffmpeg_caps


def _run(cmd, timeout=30):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def probe_streams(path):
    """Return {'duration': secs, 'video': [...], 'audio': [...], 'subtitle': [...]}.
    Each track: {index (type-relative), abs_index, lang, title, codec, default}."""
    ff = ffmpeg_caps()
    out = {"duration": 0.0, "video": [], "audio": [], "subtitle": []}
    if not ff["ffprobe"]:
        return out
    try:
        r = _run([ff["ffprobe"], "-v", "quiet", "-print_format", "json",
                  "-show_format", "-show_streams", str(path)])
        data = json.loads(r.stdout or "{}")
    except Exception:
        return out
    try:
        out["duration"] = float(data.get("format", {}).get("duration", 0) or 0)
    except Exception:
        pass
    counters = {"video": 0, "audio": 0, "subtitle": 0}
    for s in data.get("streams", []):
        ct = s.get("codec_type")
        if ct not in counters:
            continue
        tags = s.get("tags", {}) or {}
        rel = counters[ct]
        counters[ct] += 1
        out[ct].append({
            "index": rel,
            "abs_index": s.get("index"),
            "lang": tags.get("language", "und"),
            "title": tags.get("title", ""),
            "codec": s.get("codec_name", "?"),
            "default": bool((s.get("disposition") or {}).get("default")),
            "channels": s.get("channels"),
            "width": s.get("width"),
            "height": s.get("height"),
        })
    return out


def track_label(t):
    bits = [f"{t['index']}", f"[{t['lang']}]"]
    if t.get("title"):
        bits.append(t["title"])
    bits.append(f"({t['codec']}"
                + (f", {t['channels']}ch" if t.get("channels") else "")
                + (f", {t['width']}x{t['height']}" if t.get("width") else "") + ")")
    if t.get("default"):
        bits.append("· default")
    return " ".join(bits)


def escape_for_filter(path):
    """FFmpeg's subtitles= filter needs paths escaped hard."""
    s = str(path).replace("\\", "/")
    s = s.replace("'", r"'\''") if False else s
    return s.replace(":", r"\:").replace("'", r"\'").replace("[", r"\[").replace("]", r"\]").replace(",", r"\,")


def build_encode_args(settings, want_filters=True):
    """Return (input_prefix_args, video_codec_args). input_prefix goes BEFORE -i
    (for hwaccel init), codec args after the maps."""
    fam = settings.get("encoder_family", "x264")
    hw = settings.get("hw_encoder", "cpu")
    crf = str(settings.get("crf", 22))
    preset = settings.get("preset", "medium")
    tune = settings.get("tune", "none")
    threads = str(settings.get("threads", 0))
    pre, vc = [], []

    if hw == "cpu":
        vc = ["-c:v", "libx265" if fam == "x265" else "libx264",
              "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p", "-threads", threads]
        if tune != "none":
            vc += ["-tune", tune]
    elif hw == "vaapi":
        pre = ["-vaapi_device", "/dev/dri/renderD128"]
        vc = ["-c:v", "hevc_vaapi" if fam == "x265" else "h264_vaapi", "-qp", crf]
        # the caller is responsible for appending  format=nv12,hwupload  to -vf
    elif hw == "qsv":
        vc = ["-c:v", "hevc_qsv" if fam == "x265" else "h264_qsv",
              "-global_quality", crf, "-preset", preset]
    elif hw == "nvenc":
        vc = ["-c:v", "hevc_nvenc" if fam == "x265" else "h264_nvenc",
              "-preset", "p5", "-rc", "vbr", "-cq", crf, "-pix_fmt", "yuv420p"]
    return pre, [x for x in vc if x is not None]


class FFJob:
    """One ffmpeg invocation with progress + kill."""

    def __init__(self, cmd, duration=0.0, on_line=None, on_progress=None):
        self.cmd = [str(c) for c in cmd]
        self.duration = duration or 0.0
        self.on_line = on_line or (lambda s: None)
        self.on_progress = on_progress or (lambda f: None)
        self.proc = None
        self._killed = False
        self.returncode = None

    def kill(self):
        self._killed = True
        p = self.proc
        if p and p.poll() is None:
            try:
                p.send_signal(signal.SIGINT)
                time.sleep(0.4)
                if p.poll() is None:
                    p.kill()
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

    def run(self):
        self.on_line("$ " + " ".join(self.cmd))
        # -progress to stdout, log to stderr
        cmd = self.cmd[:1] + ["-hide_banner", "-progress", "pipe:1", "-nostats"] + self.cmd[1:]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, bufsize=1)

        def pump_err():
            for line in self.proc.stderr:
                if self._killed:
                    return
                line = line.rstrip()
                if line:
                    self.on_line(line)
        t = threading.Thread(target=pump_err, daemon=True)
        t.start()

        cur_us = 0
        for line in self.proc.stdout:
            if self._killed:
                break
            line = line.strip()
            m = re.match(r"out_time_us=(\d+)", line)
            if m:
                cur_us = int(m.group(1))
                if self.duration > 0:
                    self.on_progress(min(cur_us / 1e6 / self.duration, 0.999))
            elif line == "progress=end":
                self.on_progress(1.0)
        self.returncode = self.proc.wait()
        t.join(timeout=1)
        if self._killed:
            self.on_line("[killed]")
        return self.returncode
