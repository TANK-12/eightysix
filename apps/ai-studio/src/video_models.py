"""Real video models (catalog kind "video"): one sd CLI run per job.

sd-server has a /sdcpp/v1/vid_gen route, but a video model is loaded for one
long job and then not needed, so each job runs ``sd -M vid_gen`` as its own
process instead: it loads, generates, writes the file and exits, which frees
all its memory. The process runs in its own process group so Cancel stops it
and everything it started.

Before a job starts, the caller stops the image sd-servers to free RAM for
the video model (they start again on the next image request).
"""

import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

import config
import engine_flags

PROGRESS = re.compile(rb"\|\s*(\d+)/(\d+)\s*(?:-|\|)")
LOG_TAIL = 1500


class VideoBusy(Exception):
    pass


class VideoJob:
    def __init__(self, job_id, model_id, cmd, env, work_dir, out_path, on_done=None):
        self.job_id = job_id
        self.model_id = model_id
        self.cmd = cmd
        self.env = env
        self.work_dir = Path(work_dir)
        self.out_path = Path(out_path)
        self.on_done = on_done
        self.state = "running"
        self.message = "Loading the model"
        self.step = 0
        self.steps = 0
        self.url = None
        self.started = time.time()
        self.seconds = None
        self.proc = None
        self._cancel = threading.Event()
        self._proc_lock = threading.Lock()  # cancel vs. process start
        self.thread: threading.Thread | None = None

    def snapshot(self):
        return {
            "id": self.job_id,
            "model_id": self.model_id,
            "state": self.state,
            "message": self.message,
            "step": self.step,
            "steps": self.steps,
            "url": self.url,
            "seconds": (
                self.seconds
                if self.seconds is not None
                else round(time.time() - self.started, 1)
            ),
        }

    def _watch(self, stream, log):
        buf = b""
        while True:
            chunk = (
                stream.read1(4096) if hasattr(stream, "read1") else stream.read(4096)
            )
            if not chunk:
                break
            log.write(chunk)
            buf = (buf + chunk)[-4096:]
            found = PROGRESS.findall(buf)
            if found:
                step, steps = found[-1]
                self.step, self.steps = int(step), int(steps)
                self.message = "Generating"

    def run(self):
        log_path = self.work_dir / "sd.log"
        try:
            with open(log_path, "ab") as log:
                with self._proc_lock:
                    if self._cancel.is_set():
                        self.state, self.message = "cancelled", "Cancelled."
                        return
                    proc = subprocess.Popen(
                        self.cmd,
                        cwd=self.work_dir,
                        env=self.env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    self.proc = proc
                assert proc.stdout is not None
                self._watch(proc.stdout, log)
                rc = proc.wait()
            if self._cancel.is_set():
                self.state, self.message = "cancelled", "Cancelled."
            elif rc != 0 or not self.out_path.is_file():
                tail = log_path.read_bytes()[-LOG_TAIL:].decode(errors="replace")
                self.state = "failed"
                self.message = f"The video engine stopped (code {rc}).\n{tail}"
            else:
                self.message = "Finishing"
                final = _to_mp4(self.out_path)
                self.url = f"/outputs/{self.job_id}/{final.name}"
                self.state, self.message = "done", "Done."
                if self.on_done:
                    self.on_done(self)
        except Exception as e:
            self.state, self.message = "failed", str(e) or e.__class__.__name__
        finally:
            self.seconds = round(time.time() - self.started, 1)

    def cancel(self, wait=10.0):
        with self._proc_lock:
            self._cancel.set()
            proc = self.proc
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=wait)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.thread:
            self.thread.join(timeout=wait)


def _to_mp4(path):
    """The page plays mp4 everywhere; convert the engine's webm, keeping its
    sound. Falls back to the webm if ffmpeg is missing or fails."""
    mp4 = path.with_name("final.mp4")
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(path),
                "-vf",
                "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(mp4),
            ],
            capture_output=True,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired):
        return path
    return mp4 if proc.returncode == 0 and mp4.is_file() else path


_jobs = {}  # job_id -> VideoJob
_lock = threading.Lock()


def running_job():
    with _lock:
        return next((j for j in _jobs.values() if j.state == "running"), None)


def get_job(job_id):
    with _lock:
        return _jobs.get(job_id)


def start(
    job_id,
    entry,
    paths,
    prompt,
    negative_prompt="",
    frames=None,
    width=None,
    height=None,
    seed=-1,
    steps=None,
    init_image=None,
    before_start=None,
    on_done=None,
):
    """Start one video job in the background; raises VideoBusy if another
    is running (one at a time: each needs most of the RAM)."""
    with _lock:
        if any(j.state == "running" for j in _jobs.values()):
            raise VideoBusy("A video is being made. Wait for it or cancel it first.")
        work_dir = config.OUTPUTS_DIR / job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        out_path = work_dir / "raw.webm"
        cmd = engine_flags.video_cmd(
            entry,
            paths,
            prompt,
            out_path,
            negative_prompt=negative_prompt,
            frames=frames,
            width=width,
            height=height,
            seed=seed,
            steps=steps,
            init_image=init_image,
        )
        job = VideoJob(
            job_id,
            entry["id"],
            cmd,
            engine_flags.engine_env(entry),
            work_dir,
            out_path,
            on_done,
        )
        _jobs[job_id] = job
    if before_start:
        before_start()
    thread = threading.Thread(target=job.run, daemon=True)
    job.thread = thread
    thread.start()
    return job
