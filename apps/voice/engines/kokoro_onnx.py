"""TTS through kokoro-onnx (Kokoro v1.0 onnx model and its voices file)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from engines import pick_file


class Engine:
    def __init__(self, row: dict, files: dict[str, Path], threads: int):
        import onnxruntime as ort
        from kokoro_onnx import Kokoro

        model = pick_file(files, ("model", "onnx"), ".onnx")
        voices = pick_file(files, ("voices",), ".bin")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, int(threads))
        session = ort.InferenceSession(
            str(model), opts, providers=["CPUExecutionProvider"]
        )
        self.kokoro: Any = Kokoro.from_session(session, str(voices))
        self.lang = row.get("lang") or "en-us"
        self.default_voice = row.get("default_voice") or "af_heart"

    def voices(self) -> list[str]:
        return sorted(self.kokoro.get_voices())

    def synthesize(self, text: str, voice: str, speed: float) -> tuple[np.ndarray, int]:
        samples, rate = self.kokoro.create(
            text, voice=voice or self.default_voice, speed=float(speed), lang=self.lang
        )
        return np.asarray(samples, dtype=np.float32), int(rate)

    def close(self) -> None:
        self.kokoro = None
