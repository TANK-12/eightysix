"""The models scene uses, declared in one place.

Every entry is downloaded through `panelforge.models.ensure` from the named
project's own Hugging Face repo, and every caller has a classical fallback,
so a missing, blocked or over-budget model only lowers quality.

Adding a model = one entry here plus the code that reads it.
Set PANELFORGE_SCENE_MODELS=off to run fully classical (the unit tests do).
"""

from __future__ import annotations

import os
import threading

import numpy as np
from dataclasses import dataclass
from pathlib import Path

from .. import models

HF = "https://huggingface.co"


@dataclass(frozen=True)
class ModelSpec:
    key: str
    repo: str
    file: str
    approx_mb: int
    purpose: str

    @property
    def url(self) -> str:
        return f"{HF}/{self.repo}/resolve/main/{self.file}"

    @property
    def source(self) -> str:
        return f"{HF}/{self.repo}"

    @property
    def local_name(self) -> str:
        return "scene-" + self.key


MODELS: dict[str, ModelSpec] = {
    spec.key: spec
    for spec in (
        ModelSpec(
            "person",
            "deepghs/anime_person_detection",
            "person_detect_v1.3_s/model.onnx",
            45,
            "people boxes (YOLOv8, one class)",
        ),
        ModelSpec(
            "face",
            "deepghs/anime_face_detection",
            "face_detect_v1.4_s/model.onnx",
            45,
            "face boxes (YOLOv8, one class)",
        ),
        ModelSpec(
            "seg",
            "skytnt/anime-seg",
            "isnetis.onnx",
            177,
            "character foreground mask (ISNet)",
        ),
        ModelSpec(
            "ccip_feat",
            "deepghs/ccip_onnx",
            "ccip-caformer-24-randaug-pruned/model_feat.onnx",
            151,
            "character identity embedding (CCIP)",
        ),
        ModelSpec(
            "ccip_metrics",
            "deepghs/ccip_onnx",
            "ccip-caformer-24-randaug-pruned/model_metrics.onnx",
            1,
            "CCIP pairwise difference head",
        ),
        ModelSpec(
            "depth_base",
            "onnx-community/depth-anything-v2-base",
            "onnx/model.onnx",
            390,
            "relative depth (Depth Anything V2 Base, fp32)",
        ),
    )
}

# Thresholds published next to the models (threshold.json / metrics.json).
PERSON_THRESHOLD = 0.324
FACE_THRESHOLD = 0.25  # published 0.307; lower finds more realistic manhwa faces
CCIP_SAME_THRESHOLD = 0.178  # CCIP difference below this = same character

_sessions: dict[str, object] = {}
_failed: dict[str, str] = {}
_fallbacks: dict[str, str] = {}  # models that run on CPU although a GPU was asked for
_guard = threading.Lock()


def enabled() -> bool:
    return os.environ.get("PANELFORGE_SCENE_MODELS", "on").lower() not in (
        "off",
        "0",
        "no",
    )


def path(key: str) -> Path | None:
    """Local file for a model, downloading it once. None when unavailable."""
    if not enabled():
        return None
    spec = MODELS[key]
    try:
        return models.ensure(
            spec.local_name,
            spec.url,
            filename=Path(spec.file).name,
            approx_mb=spec.approx_mb,
            source=spec.source,
            wanted_by="scene",
        )
    except Exception as e:  # network, budget: fall back to classical
        _failed[key] = f"{type(e).__name__}: {e}"
        return None


class _OpenVinoSession:
    """The onnxruntime-shaped bit of API detectors use, over OpenVINO on the
    Intel iGPU. Measured 2026-09-17: depth model 0.96 s on the Iris Xe against
    3.9 s on CPU."""

    def __init__(self, path: Path, device: str):
        import openvino as ov

        core = ov.Core()
        if device not in core.available_devices:
            raise RuntimeError(
                f"OpenVINO device {device} not available: {core.available_devices}"
            )
        model = core.read_model(str(path))
        self._name = model.inputs[0].get_any_name()
        self._compiled = core.compile_model(model, device)
        self.device = device

    def get_inputs(self):
        return [type("In", (), {"name": self._name})()]

    def run(self, _outputs, feed: dict):
        req = self._compiled.create_infer_request()
        req.infer(feed)
        return [
            np.asarray(req.get_output_tensor(i).data)
            for i in range(len(self._compiled.outputs))
        ]


# Models whose input shape changes per panel: OpenVINO recompiles for every new
# shape (about 8 s each), so the iGPU loses. Measured 2026-09-17 on one page:
# depth 14 s on GPU against 6.6 s on CPU; faces 1.6 s -> 0.2 s and
# segmentation 2.5 s -> 0.23 s the other way.
CPU_ONLY = {"depth_base", "depth"}


def device() -> str:
    """PANELFORGE_SCENE_DEVICE: GPU (default, the iGPU through OpenVINO) or CPU."""
    return os.environ.get("PANELFORGE_SCENE_DEVICE", "GPU").upper()


def session(key: str):
    """A cached model session (OpenVINO on the iGPU when possible, else
    onnxruntime on CPU), or None (the caller falls back)."""
    with _guard:
        if key in _sessions:
            return _sessions[key]
        if key in _failed:
            return None
        p = path(key)
        if p is None:
            return None
        if device() != "CPU" and key not in CPU_ONLY:
            try:
                sess = _OpenVinoSession(p, device())
                _sessions[key] = sess
                return sess
            except Exception as e:  # no openvino, no iGPU, or an unsupported op: CPU
                _fallbacks[key] = f"{type(e).__name__}: {e}"[:200]
        try:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            # Leave most cores to the desktop: scene runs as a background job.
            opts.intra_op_num_threads = 4
            opts.inter_op_num_threads = 1
            sess = ort.InferenceSession(
                str(p), opts, providers=["CPUExecutionProvider"]
            )
        except Exception as e:
            _failed[key] = f"{type(e).__name__}: {e}"
            return None
        _sessions[key] = sess
        return sess


def status() -> dict:
    """Which models are loaded, missing or failed (shown in the job log)."""
    out = {}
    for key in MODELS:
        if key in _sessions:
            sess = _sessions[key]
            dev = getattr(sess, "device", "CPU")
            out[key] = f"loaded on {dev}" + (
                f" (fell back: {_fallbacks[key]})" if key in _fallbacks else ""
            )
        else:
            out[key] = _failed.get(key, "not loaded" if enabled() else "off")
    return out
