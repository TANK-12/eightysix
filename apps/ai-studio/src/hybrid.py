"""Keeps both the iGPU and the CPU busy during batch and longform generation.

Two sd-server processes run side by side: one on the Vulkan iGPU, one on the
CPU. Frame (or image) tasks go into one shared list; each backend has a
worker thread that takes the next task when it is free. Each worker keeps a
rolling average of its own seconds per task, which drives two rules:

- **Tail rule.** A slower worker leaves a task for the faster one when the
  faster one would finish *every* waiting task, this one included, before
  the slow one could finish just this one. Without it the CPU grabs the last
  frame of a scene and the whole job waits ~7 s for it while the GPU idles.
- **Failover.** A task that fails on one backend is tried once on the
  other. A backend that fails twice in a row (for example the CPU server
  never started, or crashed) is retired for the rest of the run, as long as
  another backend is still working. So a dead CPU server slows a job down
  instead of failing it.

`cancel()` drops every task not yet started; `run_all` then raises
`Cancelled`.
"""

import collections
import threading
import time

import config


class Cancelled(Exception):
    """The job was cancelled before this task ran."""


class Worker:
    def __init__(self, name, server_url):
        self.name = name
        self.server_url = server_url
        self.avg_seconds = 2.0 if name == "gpu" else 7.0  # seed with measured defaults
        self.busy_since = None  # time.time() when the current task started
        self.frames_done = 0
        self.failures_in_row = 0
        self.retired = False

    def record(self, seconds):
        # exponential moving average so it adapts if load changes
        self.avg_seconds = 0.7 * self.avg_seconds + 0.3 * seconds
        self.frames_done += 1

    def time_left_on_current(self, now):
        if self.busy_since is None:
            return 0.0
        return max(0.0, self.avg_seconds - (now - self.busy_since))


class HybridScheduler:
    """Runs callables fn(server_url) across the GPU (and optionally CPU)
    sd-servers. `run_all(tasks)` returns results in submission order."""

    MAX_FAILURES_IN_ROW = 2

    def __init__(self, use_cpu=True, gpu_url=None, cpu_url=None):
        self.gpu = Worker("gpu", gpu_url or config.GPU_SERVER_URL)
        self.cpu = Worker("cpu", cpu_url or config.CPU_SERVER_URL) if use_cpu else None
        self.workers = [w for w in (self.gpu, self.cpu) if w is not None]
        self._cond = threading.Condition()
        self._pending = collections.deque()  # [task_id, fn, tried-by names]
        self._results = {}
        self._threads = []
        self._next_id = 0
        self._stopped = False
        self.cancelled = False

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        for w in self.workers:
            t = threading.Thread(target=self._worker_loop, args=(w,), daemon=True)
            t.start()
            self._threads.append(t)

    def shutdown(self):
        """Stop the worker threads. Call once, after the last run_all() of a
        job (a longform job calls run_all once per block of frames and needs
        the same workers alive throughout)."""
        with self._cond:
            self._stopped = True
            self._cond.notify_all()
        for t in self._threads:
            t.join(timeout=5)

    def cancel(self):
        """Drop every task not yet started. Running tasks finish."""
        with self._cond:
            self.cancelled = True
            while self._pending:
                task_id, _fn, _tried = self._pending.popleft()
                self._results[task_id] = (None, Cancelled(), "-", 0.0)
            self._cond.notify_all()

    # -- dispatch ----------------------------------------------------------

    def _alive(self):
        return [w for w in self.workers if not w.retired]

    def _pick(self, worker, now):
        """Index of the task `worker` should take now, or None to wait."""
        if worker.retired or not self._pending:
            return None
        others = [w for w in self._alive() if w is not worker]
        for idx, (_tid, _fn, tried) in enumerate(self._pending):
            if worker.name in tried and any(w.name not in tried for w in others):
                continue  # failed here before: let the other backend try it
            # only backends that may still run this task count: one it
            # already failed on must not hold it back from this one
            faster = [
                w
                for w in others
                if w.avg_seconds < worker.avg_seconds and w.name not in tried
            ]
            for f in faster:
                queued = len(self._pending)
                f_done = f.time_left_on_current(now) + f.avg_seconds * queued
                if f_done <= worker.avg_seconds:
                    return None  # tail rule: the faster one finishes it all sooner
            return idx
        return None

    def _worker_loop(self, worker):
        while True:
            with self._cond:
                while True:
                    if self._stopped or worker.retired:
                        return
                    idx = self._pick(worker, time.time())
                    if idx is not None:
                        break
                    self._cond.wait(timeout=0.1)
                task_id, fn, tried = self._pending[idx]
                del self._pending[idx]
                worker.busy_since = time.time()
            t0 = time.time()
            try:
                result, error = fn(worker.server_url), None
            except Exception as e:  # handed back to run_all's caller
                result, error = None, e
            elapsed = time.time() - t0
            with self._cond:
                worker.busy_since = None
                if error is None:
                    worker.failures_in_row = 0
                    worker.record(elapsed)
                    self._results[task_id] = (result, None, worker.name, elapsed)
                else:
                    worker.failures_in_row += 1
                    tried = tried | {worker.name}
                    others = [w for w in self._alive() if w is not worker]
                    if worker.failures_in_row >= self.MAX_FAILURES_IN_ROW and others:
                        worker.retired = True
                    retry = not isinstance(error, Cancelled) and not self.cancelled
                    if retry and any(w.name not in tried for w in others):
                        self._pending.appendleft((task_id, fn, tried))
                    else:
                        self._results[task_id] = (None, error, worker.name, elapsed)
                self._cond.notify_all()

    def run_all(self, tasks, progress_cb=None):
        """tasks: callables fn(server_url) -> result. Returns a list of
        (result, worker_name, elapsed) in the same order as `tasks`. Waits for
        every task, then raises the first error (so the caller's checkpoints
        of the tasks that worked are kept). Raises Cancelled if cancelled.
        Safe to call many times on one scheduler: task ids never repeat."""
        with self._cond:
            if self.cancelled:
                raise Cancelled()
            ids = list(range(self._next_id, self._next_id + len(tasks)))
            self._next_id += len(tasks)
            for task_id, fn in zip(ids, tasks):
                self._pending.append((task_id, fn, frozenset()))
            self._cond.notify_all()

        results = [None] * len(tasks)
        done = 0
        while done < len(tasks):
            with self._cond:
                popped = []
                while not popped:
                    popped = [
                        (pos, self._results.pop(tid))
                        for pos, tid in enumerate(ids)
                        if results[pos] is None and tid in self._results
                    ]
                    if not popped:
                        self._cond.wait(timeout=0.5)
            for pos, res in popped:
                results[pos] = res
                done += 1
                if progress_cb and res[1] is None:
                    progress_cb(pos, res[2], res[3], done, len(tasks))

        finished = [r for r in results if r is not None]  # every slot is filled by now
        errors = [r[1] for r in finished if r[1] is not None]
        if self.cancelled or any(isinstance(e, Cancelled) for e in errors):
            raise Cancelled()
        if errors:
            raise errors[0]
        return [(r[0], r[2], r[3]) for r in finished]

    def stats(self):
        return {
            w.name: {
                "avg_seconds": round(w.avg_seconds, 2),
                "frames_done": w.frames_done,
                "retired": w.retired,
            }
            for w in self.workers
        }
