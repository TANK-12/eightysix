"""Measure how far the system-sound visualiser lags the sound.

Makes a silent PulseAudio null sink (no speakers involved), points cava at
its monitor with the config shared/forge_music.py writes, plays tone bursts
into the sink, and times each burst from the moment it is written to the
moment cava's levels reach half of their peak. The JS smoothing the pages
put on top (the hub, the desktop, the widgets) is then replayed over the
same recorded cava frames at a 60 Hz screen, so the figure is the whole way
from sound to drawn bar.

    python3 tools/vis_latency.py [--fps 30 --nr 77] [--trials 5] [--json]

The sink is removed again at the end, and the default output is left alone.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

FORGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FORGE / "shared"))
import forge_music  # noqa: E402

RATE = 48000
SINK = "forge_vis_latency"


def tone(seconds: float) -> bytes:
    """A low, a mid and a high tone together, so most bars move."""
    n = int(RATE * seconds)
    out = bytearray()
    for i in range(n):
        t = i / RATE
        s = (
            0.35 * math.sin(2 * math.pi * 70 * t)
            + 0.25 * math.sin(2 * math.pi * 900 * t)
            + 0.15 * math.sin(2 * math.pi * 5000 * t)
        )
        v = int(max(-1.0, min(1.0, s)) * 32000)
        out += struct.pack("<hh", v, v)
    return bytes(out)


def run_cava(fps: int, nr: int, frames: list) -> subprocess.Popen:
    conf = forge_music.cava_config(32, fps)
    conf = conf.replace("noise_reduction = 77", f"noise_reduction = {nr}")
    conf = conf.replace("source = auto", f"source = {SINK}.monitor")
    fd, path = tempfile.mkstemp(prefix="forge-vislat-", suffix=".conf")
    with os.fdopen(fd, "w") as f:
        f.write(conf)
    cmd = ["cava", "-p", path]
    if shutil.which("stdbuf"):
        cmd = ["stdbuf", "-oL"] + cmd
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    )

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            v = forge_music.parse_frame(line, 32)
            if v is not None:
                frames.append((time.monotonic(), sum(v) / len(v)))
        os.unlink(path)

    threading.Thread(target=pump, daemon=True).start()
    return proc


def run_parec(frames: list) -> subprocess.Popen:
    """The monitor's raw sound, read 5 ms at a time: the floor any reader of
    the sink has, cava or not."""
    proc = subprocess.Popen(
        [
            "parec",
            f"--device={SINK}.monitor",
            "--format=s16le",
            f"--rate={RATE}",
            "--channels=1",
            "--latency-msec=5",
            "--raw",
        ],
        stdout=subprocess.PIPE,
    )

    def pump() -> None:
        assert proc.stdout is not None
        while True:
            buf = proc.stdout.read(2 * RATE // 200)
            if not buf:
                break
            n = len(buf) // 2
            peak = max(abs(x) for x in struct.unpack(f"<{n}h", buf[: 2 * n]))
            frames.append((time.monotonic(), peak / 32768))

    threading.Thread(target=pump, daemon=True).start()
    return proc


def onsets(trials: int, quiet: float, loud: float) -> tuple[list[float], list]:
    """Play `trials` bursts into the sink; returns their start times."""
    play = subprocess.Popen(
        [
            "pacat",
            "--playback",
            f"--device={SINK}",
            "--format=s16le",
            f"--rate={RATE}",
            "--channels=2",
            "--latency-msec=10",
            "--raw",
        ],
        stdin=subprocess.PIPE,
    )
    assert play.stdin is not None
    chunk = RATE // 100  # 10 ms
    silence = bytes(4 * chunk)
    burst = tone(loud)
    starts = []
    for _ in range(trials):
        for _ in range(int(quiet * 100)):
            play.stdin.write(silence)
            play.stdin.flush()
        # pacat blocks once its 10 ms buffer is full, so the write of the
        # first loud chunk happens about when the sink starts playing it
        starts.append(time.monotonic() + 0.010)
        for i in range(0, len(burst), 4 * chunk):
            play.stdin.write(burst[i : i + 4 * chunk])
            play.stdin.flush()
    for _ in range(int(quiet * 100)):
        play.stdin.write(silence)
    play.stdin.close()
    play.wait()
    return starts, []


# --- the pages' smoothing, replayed at a 60 Hz screen --------------------


def old_js(level: float, shown: float, _dt: float) -> float:
    """Before: 35% of the way each frame, whatever the frame rate."""
    return shown + (level - shown) * 0.35


def new_js(level: float, shown: float, dt: float) -> float:
    """shared/forge_visual.js ForgeVisual.follow: quick up, slow down."""
    tau = 0.012 if level > shown else 0.16
    return shown + (level - shown) * (1 - math.exp(-dt / tau))


def replay(frames: list, smooth) -> list:
    """What a 60 Hz page draws from cava's frames through `smooth`."""
    if not frames:
        return []
    out, shown, i, latest = [], 0.0, 0, 0.0
    t, end, dt = frames[0][0], frames[-1][0], 1 / 60
    while t < end:
        while i < len(frames) and frames[i][0] <= t:
            latest = frames[i][1]
            i += 1
        shown = smooth(latest, shown, dt) if smooth else latest
        out.append((t, shown))
        t += dt
    return out


def lag(series: list, starts: list[float], loud: float) -> list[float]:
    """Per burst: seconds from its start to half of its peak."""
    out = []
    for s in starts:
        window = [(t, v) for t, v in series if s - 0.05 <= t <= s + loud]
        peak = max((v for _, v in window), default=0)
        if peak <= 0:
            continue
        hit = next((t for t, v in window if t >= s and v >= peak / 2), None)
        if hit is not None:
            out.append(hit - s)
    return out


def median(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--nr", type=int, default=77, help="cava noise_reduction")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    quiet, loud = 1.2, 0.8

    module = subprocess.run(
        [
            "pactl",
            "load-module",
            "module-null-sink",
            f"sink_name={SINK}",
            "sink_properties=device.description=forge-vis-latency",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    frames: list = []
    raw: list = []
    procs = []
    try:
        procs.append(run_cava(a.fps, a.nr, frames))
        procs.append(run_parec(raw))
        time.sleep(1.5)  # cava connects and settles
        starts, _ = onsets(a.trials, quiet, loud)
        time.sleep(0.3)
    finally:
        for proc in procs:
            proc.terminate()
            proc.wait()
        subprocess.run(["pactl", "unload-module", module], check=False)

    result = {
        "fps": a.fps,
        "noise_reduction": a.nr,
        "trials": len(starts),
        "raw_ms": round(1000 * median(lag(raw, starts, loud)), 1),
        "cava_ms": round(1000 * median(lag(frames, starts, loud)), 1),
        "old_js_ms": round(1000 * median(lag(replay(frames, old_js), starts, loud)), 1),
        "new_js_ms": round(1000 * median(lag(replay(frames, new_js), starts, loud)), 1),
    }
    if a.json:
        print(json.dumps(result))
    else:
        print(
            f"cava {a.fps} fps, noise_reduction {a.nr}: raw sound {result['raw_ms']} ms, "
            f"cava alone "
            f"{result['cava_ms']} ms, drawn with the old smoothing "
            f"{result['old_js_ms']} ms, with the new {result['new_js_ms']} ms "
            f"(median of {result['trials']} bursts, sound to half height)"
        )


if __name__ == "__main__":
    main()
