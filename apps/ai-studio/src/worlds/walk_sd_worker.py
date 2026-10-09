"""Worker for the approximate walk-through (runner ``walk-sd``).

Run as ``python walk_sd_worker.py <session_dir>``. For each step of moves it
warps the current frame along the camera path (a flat 2D stand-in: zoom for
walking, shifts for stepping and turning, grey where nothing is known yet),
hands those frames to the sd CLI as a VACE control video with the current
frame as reference, and adds the new frames to the session. The last frame
starts the next step, so the walk is built a piece at a time.

Speaks the protocol in protocol.py; uses only the stdlib, Pillow, and the sd
binary named in job.json.
"""

import os
import signal
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import camera  # noqa: E402  # pyright: ignore[reportMissingImports]
import protocol  # noqa: E402  # pyright: ignore[reportMissingImports]
from PIL import Image  # noqa: E402

IDLE_TIMEOUT = 30 * 60  # a session with no new move for this long finishes
GREY = (127, 127, 127)
NEGATIVE = "blurry, static, distorted, warped, low quality, text, watermark"
SD_FLAG = {"diffusion": "--diffusion-model", "t5xxl": "--t5xxl", "vae": "--vae"}


def fit(path, width, height):
    """The start picture cropped to the walk's shape and resized."""
    img = Image.open(path).convert("RGB")
    want = width / height
    w, h = img.size
    if w / h > want:
        nw = round(h * want)
        img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = round(w / want)
        img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return img.resize((width, height), Image.Resampling.LANCZOS)


def control_frames(current, poses, folder, width, height):
    folder.mkdir(parents=True, exist_ok=True)
    img = Image.open(current).convert("RGB")
    for i, pose in enumerate(poses):
        zoom, ux, uy = camera.warp(poses[0], pose, width, height)
        data = camera.affine_for_pil(zoom, ux, uy, width, height)
        out = img.transform(
            (width, height),
            Image.Transform.AFFINE,
            data,
            resample=Image.Resampling.BICUBIC,
            fillcolor=GREY,
        )
        out.save(folder / f"{i:04d}.png")


def sd_command(job, current, control, out_dir):
    s = job["settings"]
    cmd = [job["sd_bin"], "-M", "vid_gen"]
    for p in job["parts"].values():
        if p["role"] in SD_FLAG:
            cmd += [SD_FLAG[p["role"]], p["path"]]
    cmd += [
        "-p", job.get("prompt") or "a calm walk through the scene",
        "-n", s.get("negative", NEGATIVE),
        "-W", str(s.get("width", 512)),
        "-H", str(s.get("height", 288)),
        "--video-frames", str(s.get("frames", 17)),
        "--steps", str(s.get("steps", 12)),
        "--cfg-scale", str(s.get("cfg_scale", 5.0)),
        "--sampling-method", str(s.get("sampler", "euler")),
        "--flow-shift", str(s.get("flow_shift", 3.0)),
        "-s", str(s.get("seed", -1)),
        "-o", str(out_dir / "frame_%03d.png"),
    ]  # fmt: skip
    if current is not None:
        cmd += ["-i", str(current), "--control-video", str(control)]
    return cmd + [str(a) for a in s.get("sd_args", [])]


def watch_parent(session_dir, parent, interval=2.0):
    """End this worker, and the sd run in its process group, when the app
    that started it is gone: the worker has its own session, so otherwise it
    would outlive the app and keep holding the memory."""

    def loop():
        while True:
            time.sleep(interval)
            if os.getppid() != parent:
                try:
                    protocol.write_status(
                        Path(session_dir), "stopped", "Stopped: AI Studio closed"
                    )
                finally:
                    os.killpg(os.getpgrp(), signal.SIGTERM)

    threading.Thread(target=loop, daemon=True).start()


def run(session_dir):
    d = Path(session_dir)
    watch_parent(d, os.getppid())
    job: dict = protocol.read_json(d / protocol.JOB) or {}
    s = job["settings"]
    width, height, frames = (
        s.get("width", 512),
        s.get("height", 288),
        s.get("frames", 17),
    )
    (d / "pid").write_text(str(os.getpid()))
    current = None
    if job.get("image"):
        current = d / "current.png"
        fit(job["image"], width, height).save(current)
        protocol.add_frame(d, current)
    pose = dict(camera.START)
    pending = job.get("actions") or None
    seq_done = 0
    chunk = 0
    while True:
        if pending is None:
            protocol.write_status(
                d, "waiting", "Ready for your next move", chunk=chunk, seq_done=seq_done
            )
            rec = protocol.wait_for_actions(d, seq_done, IDLE_TIMEOUT)
            if rec == "stop":
                protocol.write_status(d, "stopped", "Stopped", chunk=chunk)
                return 0
            if rec == "timeout":
                protocol.write_status(
                    d, "done", "Finished after a long wait", chunk=chunk
                )
                return 0
            seq_done, pending = rec["seq"], rec["actions"]
        chunk += 1
        protocol.write_status(
            d, "working", "Drawing the next part of the walk", chunk=chunk
        )
        poses, end = camera.plan_chunk(pose, pending, frames)
        cdir = d / "chunks" / f"{chunk:04d}"
        out_dir = cdir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        control = cdir / "control"
        if current is not None:
            control_frames(current, poses, control, width, height)
        cmd = sd_command(job, current, control, out_dir)
        print("step", chunk, pending, flush=True)
        rc = subprocess.run(cmd, stdin=subprocess.DEVNULL).returncode
        if protocol.stop_requested(d):
            protocol.write_status(d, "stopped", "Stopped", chunk=chunk)
            return 0
        made = sorted(out_dir.glob("*.png"))
        if rc != 0 or not made:
            protocol.write_status(
                d, "failed", "The video engine stopped with an error", chunk=chunk
            )
            return 1
        for f in made[1:] if current is not None else made:
            protocol.add_frame(d, f)
        current = d / "current.png"
        shutil.copyfile(made[-1], current)
        shutil.rmtree(control, ignore_errors=True)
        pose, pending = end, None
        protocol.write_status(
            d, "waiting", "Ready for your next move", chunk=chunk, seq_done=seq_done
        )


if __name__ == "__main__":
    session = sys.argv[1]
    try:
        sys.exit(run(session))
    except Exception as e:  # report any crash in the session, then fail
        protocol.write_status(session, "failed", "The walk stopped with an error")
        print(repr(e), file=sys.stderr, flush=True)
        raise
