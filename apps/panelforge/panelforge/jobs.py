"""Background jobs: slow work (fetching, detection, AI, renders) runs here.

    job = jobs.start("detect", "Cutting panels", work, series=s, chapter=c)

`work(job)` runs on a thread. It calls job.log(), job.progress(0..1) and
checks job.cancelled() between steps. Status is mirrored to
~/PanelForgeData/jobs/<id>.json so the UI and a restarted backend can see
what happened. Jobs run one heavy job at a time per `lane` so the laptop
stays usable (lane "cpu" by default; fetches use lane "net").
"""

import threading
import time
import traceback
import uuid
from typing import Any, Callable

from . import paths, store

_jobs: dict[str, "Job"] = {}
_lanes: dict[str, threading.Lock] = {}
_guard = threading.Lock()


class Cancelled(Exception):
    pass


class Job:
    def __init__(self, kind: str, title: str, lane: str, meta: dict):
        self.id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.kind, self.title, self.lane, self.meta = kind, title, lane, meta
        self.state = "queued"  # queued | running | done | failed | cancelled
        self.frac = 0.0
        self.lines: list[str] = []
        self.result: Any = None
        self.error = ""
        self.created = time.time()
        self._cancel = threading.Event()

    def log(self, msg: str) -> None:
        self.lines.append(time.strftime("%H:%M:%S ") + msg)
        del self.lines[:-400]
        self._save()

    def progress(self, frac: float) -> None:
        self.frac = max(0.0, min(1.0, frac))

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def check(self) -> None:
        """Raise Cancelled if the user cancelled. Call between steps."""
        if self._cancel.is_set():
            raise Cancelled()

    def cancel(self) -> None:
        self._cancel.set()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "lane": self.lane,
            "meta": self.meta,
            "state": self.state,
            "progress": round(self.frac, 4),
            "log": self.lines[-60:],
            "result": self.result,
            "error": self.error,
            "created": self.created,
        }

    def _save(self) -> None:
        path = paths.JOBS_ROOT / f"{self.id}.json"
        try:
            try:
                store.write(path, self.to_dict())
            except (TypeError, ValueError):
                # a result that is not plain JSON still gets its status file
                store.write(
                    path, {**self.to_dict(), "result": repr(self.result)[:2000]}
                )
        except (OSError, TypeError, ValueError):
            pass


def start(
    kind: str,
    title: str,
    work: Callable[[Job], Any],
    lane: str = "cpu",
    **meta: Any,
) -> Job:
    job = Job(kind, title, lane, meta)
    with _guard:
        _jobs[job.id] = job
        lock = _lanes.setdefault(lane, threading.Lock())

    def run() -> None:
        with lock:
            if job.cancelled():
                job.state = "cancelled"
                job._save()
                return
            job.state = "running"
            job._save()
            try:
                job.result = work(job)
                job.state = "done"
                job.frac = 1.0
            except Cancelled:
                job.state = "cancelled"
            except Exception as e:  # reported to the UI, never swallowed
                job.state = "failed"
                job.error = f"{type(e).__name__}: {e}"
                job.lines.append(traceback.format_exc()[-2000:])
            job._save()

    threading.Thread(target=run, daemon=True, name=f"job-{job.id}").start()
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def all_jobs() -> list[dict]:
    return [j.to_dict() for j in sorted(_jobs.values(), key=lambda j: -j.created)]


def wait(job: Job, timeout: float = 600) -> Job:
    """For tests: block until the job leaves queued/running."""
    end = time.time() + timeout
    while job.state in ("queued", "running") and time.time() < end:
        time.sleep(0.05)
    return job
