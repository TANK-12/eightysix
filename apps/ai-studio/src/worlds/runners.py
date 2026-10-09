"""World runners: one per project family, in a small registry.

A catalog entry picks its runner with ``"engine": "world:<runner-id>"``.
Each runner answers ``status(entry) -> (can_run, plain note)``, builds a job
for a session, and names the worker command the session starts.

- ``walk-sd``: the approximate walk-through. Runs here, through the
  stable-diffusion.cpp binary the app already ships (Wan2.1 VACE 1.3B).
- ``inspatio``, ``worldcrafter``, ``evoke``: real world models, PyTorch
  projects. They would run from ``models/worlds/runtime/<runner>/`` with
  their own virtualenv and an adapter script that speaks ``protocol.py``.
  Nothing installs that runtime yet; ``RuntimeSpec`` records exactly what it
  would be, for Emerson to review (docs/WORLDS.md).
"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import config  # pyright: ignore[reportMissingImports]

HERE = Path(__file__).resolve().parent
WORLDS_DIR = config.MODELS_DIR / "worlds"
PART_DIRS = [
    getattr(config, "PARTS_DIR", config.MODELS_DIR / "parts"),
    getattr(config, "LEGACY_MODEL_DIR", config.MODELS_DIR / "sd" / "catalog"),
    config.MODELS_DIR / "sd",
]

NOTE_READY = "Ready"
NOTE_NO_ENGINE = "Needs the image engine, not set up yet"
NOTE_ENGINE_UPDATE = "Needs an engine update"
NOTE_NO_RUNTIME = "Needs the 3D world runtime, not set up yet"
NOTE_NVIDIA = "Needs an NVIDIA graphics card"
NOTE_DOWNLOAD = "Download it first"


def has_nvidia():
    """True when an NVIDIA driver is loaded (never on this laptop)."""
    return Path("/proc/driver/nvidia/version").exists() or bool(
        shutil.which("nvidia-smi")
    )


def part_path(p):
    """Where a stored part lives, or None when it is not downloaded."""
    for folder in PART_DIRS:
        candidate = Path(folder) / p["filename"]
        if candidate.is_file():
            return candidate
    return None


def sd_binary(entry):
    """The sd CLI for an entry's engine build."""
    builds = getattr(config, "ENGINE_BUILDS", None)
    if not builds:
        return config.SD_BIN
    build = entry.get("engine_build") or getattr(
        config, "DEFAULT_ENGINE_BUILD", "current"
    )
    b = builds.get(build) or builds["current"]
    return Path(b["dir"]) / b["cli"]


_HELP_CACHE = {}


def _sd_help(binary):
    key = (str(binary), binary.stat().st_mtime)
    if key not in _HELP_CACHE:
        try:
            proc = subprocess.run(
                [str(binary), "--help"], capture_output=True, text=True, timeout=20
            )
            _HELP_CACHE[key] = proc.stdout + proc.stderr
        except (OSError, subprocess.TimeoutExpired):
            _HELP_CACHE[key] = ""
    return _HELP_CACHE[key]


@dataclass(frozen=True)
class RuntimeSpec:
    """What a PyTorch runtime would install. Nothing here runs by itself."""

    python: str
    index_url: str
    packages: tuple
    extra_steps: tuple = ()
    verified_download_bytes: dict = field(default_factory=dict)
    approx_disk: str = ""
    sources: tuple = ()
    press_to_install: bool = False
    why_not: str = ""


REQUEST_SETTINGS = frozenset(
    ("seed", "steps", "cfg_scale", "frames", "width", "height", "fps")
)


class Runner:
    id = ""
    label = ""
    needs_nvidia = False
    runtime = None

    def status(self, entry) -> tuple[bool, str]:
        return False, NOTE_NO_RUNTIME

    def build_job(self, entry, prompt="", settings=None) -> dict[str, Any]:
        """Job dict for a session; raises WorldCannotRun when parts are missing."""
        from .session import WorldCannotRun

        paths: dict[str, Any] = {}
        for p in entry.get("parts", []):
            path = part_path(p)
            if path is None:
                raise WorldCannotRun(NOTE_DOWNLOAD)
            paths[p["filename"]] = {
                "role": p["role"],
                "path": str(path),
                "dest": p.get("dest"),
            }
        merged = dict(entry.get("settings") or {})
        # A request may only change these; engine arguments (sd_args) and
        # anything else come from the catalog entry alone.
        merged.update(
            {k: v for k, v in (settings or {}).items() if k in REQUEST_SETTINGS}
        )
        return {"parts": paths, "settings": merged}

    def command(self, session_dir):
        raise NotImplementedError

    def cwd(self) -> Path | None:
        return None

    def env(self):
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        return env


class WalkSdRunner(Runner):
    """Approximate walk-through with the sd binary (Wan2.1 VACE 1.3B)."""

    id = "walk-sd"
    label = "Walk-through with the video engine"

    def status(self, entry) -> tuple[bool, str]:
        binary = sd_binary(entry)
        if not binary.is_file():
            return False, NOTE_NO_ENGINE
        if "--control-video" not in _sd_help(binary):
            return False, NOTE_ENGINE_UPDATE
        return True, NOTE_READY

    def build_job(self, entry, prompt="", settings=None) -> dict[str, Any]:
        job = super().build_job(entry, prompt=prompt, settings=settings)
        job["sd_bin"] = str(sd_binary(entry))
        return job

    def command(self, session_dir):
        return [sys.executable, str(HERE / "walk_sd_worker.py"), str(session_dir)]


class TorchRunner(Runner):
    """A PyTorch world-model project run from its own runtime folder."""

    def __init__(self, rid, label, needs_nvidia, runtime):
        self.id = rid
        self.label = label
        self.needs_nvidia = needs_nvidia
        self.runtime = runtime

    @property
    def runtime_dir(self):
        return WORLDS_DIR / "runtime" / self.id

    @property
    def python(self):
        return self.runtime_dir / ".venv" / "bin" / "python"

    @property
    def adapter(self):
        return self.runtime_dir / "aistudio_adapter.py"

    def status(self, entry) -> tuple[bool, str]:
        if self.needs_nvidia and not has_nvidia():
            return False, NOTE_NVIDIA
        if not (self.python.is_file() and self.adapter.is_file()):
            return False, NOTE_NO_RUNTIME
        return True, NOTE_READY

    def command(self, session_dir):
        return [str(self.python), str(self.adapter), str(session_dir)]

    def cwd(self) -> Path | None:
        return self.runtime_dir


_TORCH_CPU = "https://download.pytorch.org/whl/cpu"

RUNNERS = {
    r.id: r
    for r in (
        WalkSdRunner(),
        TorchRunner(
            "inspatio",
            "InSpatio-World runtime",
            needs_nvidia=False,
            runtime=RuntimeSpec(
                python="3.10 (uv python install 3.10; numpy 1.26 and decord 0.6 "
                "have no wheels for the system Python 3.14)",
                index_url=_TORCH_CPU,
                packages=(
                    "torch==2.10.0+cpu",
                    "torchvision==0.25.0+cpu",
                    "av==13.1.0",
                    "addict==2.4.0",
                    "decord==0.6.0",
                    "diffusers==0.37.0",
                    "easydict==1.13",
                    "einops==0.8.2",
                    "evo==1.34.3",
                    "ftfy==6.3.1",
                    "imageio==2.37.3",
                    "moviepy==1.0.3",
                    "numpy==1.26.4",
                    "omegaconf==2.3.0",
                    "opencv-python==4.11.0.86",
                    "Pillow==12.0.0",
                    "plyfile==1.1.3",
                    "pycolmap==4.0.2",
                    "regex==2026.2.28",
                    "safetensors==0.7.0",
                    "scipy==1.15.3",
                    "tqdm==4.67.3",
                    "transformers==4.57.6",
                    "trimesh==4.11.3",
                ),
                extra_steps=(
                    "pip install --no-deps depth-anything-3==0.1.1",
                    "unpack the code part into runtime/inspatio/src and apply "
                    "the CPU patch (docs/WORLDS.md)",
                    "write runtime/inspatio/aistudio_adapter.py (protocol.py)",
                ),
                verified_download_bytes={
                    "torch-2.10.0+cpu-cp310 wheel": 188832554,
                    "torchvision-0.25.0+cpu-cp310 wheel": 1923790,
                },
                approx_disk="about 2.5 GB for the runtime (reasoned, not measured)",
                sources=(
                    "https://github.com/inspatio/inspatio-world-v1.5/blob/main/environment.yml",
                    "https://download.pytorch.org/whl/cpu",
                ),
                press_to_install=False,
                why_not="Upstream code stops without CUDA; a CPU patch is "
                "needed and untested, and peak memory (text encoder about 11 GB "
                "plus the model and depth net) risks freezing a laptop with no "
                "swap. Needs Emerson's review first.",
            ),
        ),
        TorchRunner(
            "worldcrafter",
            "WorldCrafter runtime",
            needs_nvidia=True,
            runtime=RuntimeSpec(
                python="3.11",
                index_url="https://download.pytorch.org/whl/cu128",
                packages=("torch==2.10.0", "torchvision==0.25.0", "-e .[demo,xformers]",
                          "flash-attn-3==3.0.0"),  # fmt: skip
                sources=("https://github.com/TencentARC/WorldCrafter#readme",),
                why_not="Needs an NVIDIA card (CUDA 12.8, flash-attn 3, xformers).",
            ),
        ),
        TorchRunner(
            "evoke",
            "Evoke runtime",
            needs_nvidia=True,
            runtime=RuntimeSpec(
                python="3.10",
                index_url="https://download.pytorch.org/whl/cu124",
                packages=("torch==2.4.0", "torchvision==0.19.0", "flash-attn==2.8.3",
                          "deepspeed==0.14.5", "triton==3.0.0"),  # fmt: skip
                sources=(
                    "https://github.com/AlayaLab/Evoke/blob/main/requirements.txt",
                ),
                why_not="Needs NVIDIA cards (CUDA 12.4; flash-attn, deepspeed and "
                "triton are pinned as load-bearing by the README).",
            ),
        ),
    )
}


def runner_for(entry):
    """The runner named by an entry's engine ("world:<id>"), or None."""
    engine = str(entry.get("engine", ""))
    if not engine.startswith("world:"):
        return None
    return RUNNERS.get(engine.split(":", 1)[1])


def runtime_plan(runner_id):
    """What installing a runner's runtime would do, as a plain dict."""
    r = RUNNERS.get(runner_id)
    if r is None or r.runtime is None:
        return None
    spec = r.runtime
    return {
        "runner": r.id,
        "folder": str(getattr(r, "runtime_dir", WORLDS_DIR / "runtime" / r.id)),
        "python": spec.python,
        "index_url": spec.index_url,
        "packages": list(spec.packages),
        "extra_steps": list(spec.extra_steps),
        "verified_download_bytes": dict(spec.verified_download_bytes),
        "approx_disk": spec.approx_disk,
        "sources": list(spec.sources),
        "press_to_install": spec.press_to_install,
        "why_not": spec.why_not,
    }
