"""
ffmpeg / ffprobe wrapper -- adapted from MediaForge's ffrunner.py.

* probe_media()     -> duration, has_audio, dimensions
* video_encode_args -> the -c:v flags for cpu / vaapi / qsv
* FFJob             -> runs ffmpeg with `-progress pipe:1`, parses % from a
                       known total duration, streams log lines, kills instantly.
"""

import json
import re
import signal
import subprocess
import threading
import time

from .config import ffmpeg_caps


def probe_media(path):
    """{'duration': secs, 'has_audio': bool, 'width': int|None, 'height': int|None}."""
    ff = ffmpeg_caps()
    out = {"duration": 0.0, "has_audio": False, "width": None, "height": None}
    if not ff["ffprobe"]:
        return out
    try:
        r = subprocess.run(
            [
                ff["ffprobe"],
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(r.stdout or "{}")
    except Exception:
        return out
    try:
        out["duration"] = float(data.get("format", {}).get("duration", 0) or 0)
    except Exception:
        pass
    for s in data.get("streams", []):
        if s.get("codec_type") == "audio":
            out["has_audio"] = True
        elif s.get("codec_type") == "video":
            out["width"] = s.get("width")
            out["height"] = s.get("height")
    return out


def video_encode_args(settings):
    """Return (pre_input_args, video_codec_args) for the chosen encoder.
    pre_input_args go before the first -i (hwaccel init)."""
    enc = settings.get("encoder", "cpu")
    crf = str(settings.get("crf", 18))
    preset = settings.get("preset", "medium")
    threads = str(settings.get("threads", 0))
    if enc == "vaapi":
        return (
            ["-vaapi_device", "/dev/dri/renderD128"],
            ["-c:v", "h264_vaapi", "-qp", crf, "-pix_fmt", "vaapi"],
        )
    if enc == "qsv":
        return ([], ["-c:v", "h264_qsv", "-global_quality", crf, "-preset", preset])
    return (
        [],
        [
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            crf,
            "-pix_fmt",
            "yuv420p",
            "-threads",
            threads,
        ],
    )


class FFJob:
    """One ffmpeg invocation with progress + instant kill."""

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

    def run(self, stdin_bytes_iter=None):
        """stdin_bytes_iter: optional iterable of bytes chunks fed to ffmpeg's
        stdin (used for the Python overlay rawvideo stream)."""
        self.on_line("$ " + " ".join(self.cmd))
        cmd = (
            self.cmd[:1]
            + ["-hide_banner", "-progress", "pipe:2", "-nostats"]
            + self.cmd[1:]
        )
        # progress -> stderr (pipe:2), log also stderr; stdout kept clean in case
        # ffmpeg is asked to write to pipe:1. We parse stderr for both.
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if stdin_bytes_iter is not None else None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=False,
            bufsize=0,
        )
        proc = self.proc
        assert proc.stderr is not None

        feeder_exc = {}

        def feed():
            assert proc.stdin is not None and stdin_bytes_iter is not None
            try:
                for chunk in stdin_bytes_iter:
                    if self._killed:
                        break
                    proc.stdin.write(chunk)
                proc.stdin.close()
            except BrokenPipeError:
                pass
            except Exception as e:  # pragma: no cover - defensive
                feeder_exc["e"] = e
                try:
                    proc.stdin.close()
                except Exception:
                    pass

        feeder = None
        if stdin_bytes_iter is not None:
            feeder = threading.Thread(target=feed, daemon=True)
            feeder.start()

        # ffmpeg -progress keys we consume or silently drop (they'd spam the log)
        drop = (
            "frame=",
            "fps=",
            "stream_",
            "bitrate=",
            "total_size=",
            "speed=",
            "dup_frames=",
            "drop_frames=",
            "out_time=",
            "out_time_ms=",
            "out_time_us=",
            "progress=",
        )
        for raw in proc.stderr:
            if self._killed:
                break
            line = raw.decode("utf-8", "replace").rstrip()
            if not line:
                continue
            m = re.match(r"out_time_(?:us|ms)=(\d+)", line)  # value is microseconds
            if m and self.duration > 0:
                self.on_progress(min(int(m.group(1)) / 1e6 / self.duration, 0.999))
            elif line == "progress=end":
                self.on_progress(1.0)
            elif not line.startswith(drop):
                self.on_line(line)

        self.returncode = self.proc.wait()
        if feeder:
            feeder.join(timeout=2)
        if self._killed:
            self.on_line("[killed]")
        if feeder_exc:
            raise feeder_exc["e"]
        return self.returncode
