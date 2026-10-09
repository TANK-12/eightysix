"""ffmpeg: frame pipe encoder (VAAPI on the Iris Xe, else libx264), concat, mux, probe."""

import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path

DRI = "/dev/dri/renderD128"


@lru_cache(maxsize=1)
def vaapi_ok() -> bool:
    """Try a tiny h264_vaapi encode once per process."""
    if os.environ.get("PANELFORGE_NO_VAAPI") or not os.path.exists(DRI):
        return False
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-vaapi_device",
        DRI,
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=64x64:rate=30",
        "-frames:v",
        "3",
        "-vf",
        "format=nv12,hwupload",
        "-c:v",
        "h264_vaapi",
        "-f",
        "null",
        "-",
    ]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def encoder_name(preview: bool = False) -> str:
    return "h264_vaapi" if vaapi_ok() else "libx264"


def _video_args(preview: bool) -> list[str]:
    if vaapi_ok():
        return [
            "-vf",
            "format=nv12,hwupload",
            "-c:v",
            "h264_vaapi",
            "-qp",
            "27" if preview else "19",
        ]
    return [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast" if preview else "medium",
        "-crf",
        "26" if preview else "18",
        "-pix_fmt",
        "yuv420p",
    ]


class FrameWriter:
    """Pipe BGRA frames into an mp4."""

    def __init__(self, path: Path, size: tuple[int, int], fps: int, preview=False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tmp = self.path.with_name(self.path.stem + ".part.mp4")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        if vaapi_ok():
            cmd += ["-vaapi_device", DRI]
        cmd += [
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgra",
            "-s",
            f"{size[0]}x{size[1]}",
            "-r",
            str(fps),
            "-i",
            "-",
            *_video_args(preview),
            "-r",
            str(fps),
            "-movflags",
            "+faststart",
            str(self.tmp),
        ]
        self.size = size
        self.frames = 0
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def write(self, frame) -> None:
        assert (
            frame.shape[1] == self.size[0] and frame.shape[0] == self.size[1]
        ), frame.shape
        assert self.proc.stdin is not None
        self.proc.stdin.write(frame.tobytes())
        self.frames += 1

    def close(self) -> Path:
        assert self.proc.stdin is not None and self.proc.stderr is not None
        self.proc.stdin.close()
        err = self.proc.stderr.read().decode(errors="replace")
        if self.proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed: {err[-800:]}")
        os.replace(self.tmp, self.path)
        return self.path

    def abort(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        self.proc.kill()
        self.proc.wait()
        if self.tmp.exists():
            self.tmp.unlink()


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr.decode(errors='replace')[-800:]}")


def concat(clips: list[Path], out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(c).resolve()}'\n" for c in clips))
    tmp = out.with_name(out.stem + ".part.mp4")
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(tmp),
        ]
    )
    lst.unlink()
    os.replace(tmp, out)
    return out


def mux_audio(video: Path, wav: Path, out: Path) -> Path:
    tmp = out.with_name(out.stem + ".mux.mp4")
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-i",
            str(wav),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(tmp),
        ]
    )
    os.replace(tmp, out)
    return out


def hstack_grid(
    videos: list[Path], labels: list[str], out: Path, cols: int, cell: tuple[int, int]
) -> Path:
    """Tile videos into a labelled grid (all must share fps)."""
    n = len(videos)
    inputs, filters = [], []
    for i, (v, lab) in enumerate(zip(videos, labels)):
        inputs += ["-i", str(v)]
        safe = lab.replace(":", "\\:").replace("'", "")
        filters.append(
            f"[{i}:v]scale={cell[0]}:{cell[1]}:force_original_aspect_ratio=decrease,"
            f"pad={cell[0]}:{cell[1]}:(ow-iw)/2:(oh-ih)/2:color=0x101014,"
            f"drawtext=text='{safe}':fontfile=/usr/share/fonts/noto/NotoSans-Bold.ttf:"
            f"fontsize={max(14, cell[1] // 16)}:fontcolor=white:borderw=2:x=12:y=10[v{i}]"
        )
    rows = (n + cols - 1) // cols
    layout = "|".join(
        f"{(i % cols) * cell[0]}_{(i // cols) * cell[1]}" for i in range(n)
    )
    stack = "".join(f"[v{i}]" for i in range(n))
    if n == 1:
        filters.append("[v0]copy[out]")
    else:
        filters.append(f"{stack}xstack=inputs={n}:layout={layout}:fill=0x101014[out]")
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            "-movflags",
            "+faststart",
            str(out),
        ]
    )
    _ = rows
    return out


def probe(path: Path) -> dict:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
    )
    d = json.loads(r.stdout or b"{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    num, _, den = (v.get("r_frame_rate") or "0/1").partition("/")
    return {
        "duration": float((d.get("format") or {}).get("duration") or 0),
        "width": v.get("width"),
        "height": v.get("height"),
        "fps": float(num) / float(den or 1) if num else 0.0,
        "codec": v.get("codec_name"),
        "frames": int(v.get("nb_frames") or 0),
        "audio": any(s.get("codec_type") == "audio" for s in d.get("streams", [])),
    }
