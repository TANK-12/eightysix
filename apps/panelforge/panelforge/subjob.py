"""Run a job's work in a child process, so a crash in native code (a model
runtime, tesseract, an image codec) fails that one job instead of killing
the whole app. Session 4 lost a server to "longjmp causes uninitialized
stack frame" from inside an analyze job; Emerson's own PanelForge would die
the same way.

The child is `python -m panelforge.subjob <kind> <chapter_dir> [args]`. It
runs the same pipeline function with a job stand-in whose log/progress calls
become lines on stdout ("LOG ...", "PROGRESS 0.42", "RESULT {json}"); the
parent relays them into the real Job and kills the child on cancel.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

WORK = {
    "detect": ("panelforge.detect.pipeline", "run_detect"),
    "analyze": ("panelforge.scene.pipeline", "run_analyze"),
}


class _ChildJob:
    """The job object handed to the pipeline inside the child."""

    def log(self, msg: str) -> None:
        print("LOG " + msg.replace("\n", " "), flush=True)

    def progress(self, frac: float) -> None:
        print(f"PROGRESS {frac:.4f}", flush=True)

    def check(self) -> None:
        pass  # the parent kills the process to cancel

    def cancelled(self) -> bool:
        return False


GPU_KINDS = ("analyze",)  # jobs whose models run on the iGPU through OpenVINO


def _free_the_gpu(job) -> None:
    """Release Jan's loaded models before a GPU job.

    A loaded Jan model (llama.cpp on Vulkan) and the scene models (OpenVINO
    on OpenCL) share the one Iris Xe; with a model loaded the OpenCL kernel
    build fails (CL_BUILD_PROGRAM_FAILURE) or the process segfaults --
    measured 2026-09-19 on chapters 2 and 3. The router stays; the model
    reloads on its next request (about 2 s).
    """
    try:
        import forge_jan  # shared; on sys.path when the app runs
    except ImportError:
        return
    for model in forge_jan.loaded_models():
        if forge_jan.release(model):
            job.log(f"released Jan model {model} to free the GPU")
            time.sleep(2.0)


def run_in_child(job, kind: str, chapter_dir: Path, **kwargs: Any) -> Any:
    """Call from the parent's job thread: returns the pipeline's result. A
    GPU job that fails on the GPU is run once more on the CPU."""
    if kind in GPU_KINDS:
        _free_the_gpu(job)
    try:
        return _run_in_child(job, kind, chapter_dir, None, **kwargs)
    except RuntimeError as e:
        if kind not in GPU_KINDS or job.cancelled():
            raise
        job.log(f"{kind} failed on the GPU ({str(e)[:120]}); running again on the CPU")
        return _run_in_child(job, kind, chapter_dir, "CPU", **kwargs)


def _run_in_child(
    job, kind: str, chapter_dir: Path, device: str | None, **kwargs: Any
) -> Any:
    cmd = [
        sys.executable,
        "-m",
        "panelforge.subjob",
        kind,
        str(chapter_dir),
        json.dumps(kwargs),
    ]
    env = dict(os.environ)
    if device:
        env["PANELFORGE_SCENE_DEVICE"] = device
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
        env=env,
    )
    result: Any = None
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            if job.cancelled():
                proc.kill()
                break
            line = line.rstrip("\n")
            if line.startswith("LOG "):
                job.log(line[4:])
            elif line.startswith("PROGRESS "):
                job.progress(float(line[9:]))
            elif line.startswith("RESULT "):
                result = json.loads(line[7:])
        code = proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
    if job.cancelled():
        from .jobs import Cancelled

        raise Cancelled()
    err = (proc.stderr.read() if proc.stderr else "")[-3000:]
    if code != 0:
        tail = err.strip().splitlines()[-8:]
        raise RuntimeError(
            f"{kind} worker exited with code {code}: " + " | ".join(tail)
        )
    return result


def main(argv: list[str]) -> int:
    kind, chapter_dir = argv[0], Path(argv[1])
    kwargs = json.loads(argv[2]) if len(argv) > 2 else {}
    module, func = WORK[kind]
    import importlib

    fn = getattr(importlib.import_module(module), func)
    t0 = time.time()
    result = fn(chapter_dir, _ChildJob(), **kwargs)
    print("LOG " + f"{kind} finished in {time.time() - t0:.0f}s", flush=True)
    print("RESULT " + json.dumps(result, default=str), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
