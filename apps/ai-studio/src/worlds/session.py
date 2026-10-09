"""World sessions: one worker subprocess per session, talking through files.

``SessionManager`` starts a runner's worker, queues moves, reports new frames
and stops it. Only one session runs at a time (the graphics chip is shared).
The file protocol is in ``protocol.py``.
"""

import os
import re
import secrets
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

from . import camera, protocol

SESSION_ID = re.compile(r"^[a-z0-9-]{6,64}$")
FRAME_NAME = re.compile(r"^\d{6}\.png$")


class WorldError(Exception):
    """A world request that cannot be done; the message is plain and shown."""

    status_code = 400


class WorldNotFound(WorldError):
    status_code = 404


class WorldBusy(WorldError):
    status_code = 409


class WorldCannotRun(WorldError):
    status_code = 409


class SessionManager:
    def __init__(self, root):
        self.root = Path(root)
        self._procs = {}
        self._lock = threading.Lock()

    # -- helpers -------------------------------------------------------------

    def _dir(self, sid):
        if not isinstance(sid, str) or not SESSION_ID.match(sid):
            raise WorldNotFound("No such world session")
        d = self.root / sid
        if not (d / protocol.JOB).is_file():
            raise WorldNotFound("No such world session")
        return d

    def _alive(self, sid):
        proc = self._procs.get(sid)
        return proc is not None and proc.poll() is None

    def running(self):
        """Ids of sessions whose worker is still running."""
        return [sid for sid in list(self._procs) if self._alive(sid)]

    # -- API -----------------------------------------------------------------

    def start(self, runner, entry, prompt="", image=None, actions=None, settings=None):
        """Start a session; returns the first poll() result.

        ``image`` is a path to a start picture (copied into the session),
        ``actions`` the first moves (see camera.ACTIONS), ``settings``
        overrides for the entry's settings.
        """
        if actions:
            try:
                actions = camera.check_actions(actions)
            except ValueError as e:
                raise WorldError(str(e)) from None
        if image is not None and not Path(image).is_file():
            raise WorldError("The start picture was not found")
        with self._lock:
            if self.running():
                raise WorldBusy("A world is already running. Stop it first.")
            ok, note = runner.status(entry)
            if not ok:
                raise WorldCannotRun(note)
            job = runner.build_job(entry, prompt=prompt, settings=settings or {})
            sid = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
            d = self.root / sid
            (d / protocol.FRAMES).mkdir(parents=True)
            if image is not None:
                dest = d / ("input" + (Path(image).suffix.lower() or ".png"))
                shutil.copyfile(image, dest)
                job["image"] = str(dest)
            job.update(
                id=sid,
                model_id=entry["id"],
                runner=runner.id,
                prompt=prompt,
                actions=actions or [],
                created=time.time(),
            )
            protocol.write_json(d / protocol.JOB, job)
            protocol.write_status(d, "starting", "Getting the world ready", chunk=0)
            with open(d / protocol.LOG, "ab") as log:
                proc = subprocess.Popen(
                    runner.command(d),
                    cwd=str(runner.cwd() or d),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,  # own process group: stop() ends sd too
                    env=runner.env(),
                )
            self._procs[sid] = proc
        return self.poll(sid)

    def step(self, sid, actions):
        """Queue the next moves; the worker picks them up when it is free."""
        d = self._dir(sid)
        try:
            actions = camera.check_actions(actions)
        except ValueError as e:
            raise WorldError(str(e)) from None
        state = (protocol.read_json(d / protocol.STATUS, {}) or {}).get("state")
        if state in protocol.FINAL_STATES or not self._alive(sid):
            raise WorldError("This world has stopped. Start a new one.")
        with self._lock:
            seq = len(protocol.read_actions(d)) + 1
            protocol.append_actions(d, seq, actions)
        return self.poll(sid)

    def poll(self, sid, since=0):
        """State plus the names of frames after the first ``since``."""
        d = self._dir(sid)
        job = protocol.read_json(d / protocol.JOB, {}) or {}
        status = protocol.read_json(d / protocol.STATUS, {}) or {}
        state = status.get("state", "starting")
        if state not in protocol.FINAL_STATES:
            proc = self._procs.get(sid)
            if proc is None:
                protocol.write_status(
                    d, "stopped", "The app restarted while this world was running"
                )
            elif proc.poll() is not None:
                protocol.write_status(
                    d, "failed", "The world runner stopped unexpectedly"
                )
            status = protocol.read_json(d / protocol.STATUS, {}) or {}
            state = status.get("state")
        frames = protocol.frame_names(d)
        since = max(0, int(since or 0))
        queued = len(protocol.read_actions(d)) - int(status.get("seq_done", 0) or 0)
        return {
            "id": sid,
            "model_id": job.get("model_id"),
            "state": state,
            "message": status.get("message", ""),
            "chunk": status.get("chunk", 0),
            "frame_count": len(frames),
            "frames": frames[since:],
            "since": since,
            "fps": (job.get("settings") or {}).get("fps", 16),
            "queued_steps": max(0, queued),
            "created": job.get("created"),
        }

    def frame_path(self, sid, name):
        d = self._dir(sid)
        if not isinstance(name, str) or not FRAME_NAME.match(name):
            raise WorldNotFound("No such frame")
        path = d / protocol.FRAMES / name
        if not path.is_file():
            raise WorldNotFound("No such frame")
        return path

    def stop(self, sid, grace=5.0):
        """Ask the worker to finish, then end its process group if it lingers."""
        d = self._dir(sid)
        (d / protocol.STOP).touch()
        proc = self._procs.get(sid)
        if proc is not None and proc.poll() is None:
            try:
                proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                for sig, wait in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 3.0)):
                    try:
                        os.killpg(proc.pid, sig)
                    except ProcessLookupError:
                        break
                    try:
                        proc.wait(timeout=wait)
                        break
                    except subprocess.TimeoutExpired:
                        continue
        status = protocol.read_json(d / protocol.STATUS, {}) or {}
        if status.get("state") not in protocol.FINAL_STATES:
            protocol.write_status(d, "stopped", "Stopped")
        return self.poll(sid)

    def list(self):
        """Every session on disk, newest first (without frame lists)."""
        if not self.root.is_dir():
            return []
        out = []
        for d in sorted(self.root.iterdir(), reverse=True):
            if SESSION_ID.match(d.name) and (d / protocol.JOB).is_file():
                info = self.poll(d.name)
                info["frames"] = []
                out.append(info)
        return out

    def make_clip(self, sid, fps=None):
        """Join the session's frames into ``walk.mp4`` (ffmpeg); return its path."""
        d = self._dir(sid)
        if not protocol.frame_names(d):
            raise WorldError("This world has no frames yet")
        fps = int(fps or self.poll(sid)["fps"])
        out = d / "walk.mp4"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-framerate", str(fps),
            "-i", str(d / protocol.FRAMES / "%06d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            str(out),
        ]  # fmt: skip
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not out.is_file():
            raise WorldError("Could not join the frames into a clip")
        return out
