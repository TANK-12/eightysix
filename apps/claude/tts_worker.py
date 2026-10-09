# pyright: reportMissingImports=false
# (runs under PanelForge's venv, which has onnxruntime and kokoro_onnx; this app's does not)
"""Kokoro worker for voice.py. Runs under PanelForge's venv (which has
kokoro-onnx), reads one JSON request per line on stdin, writes a WAV file,
and answers with one JSON line on stdout. Loads the model once."""

import json
import os
import sys
import wave
from pathlib import Path

MODEL = Path(
    os.environ.get("KOKORO_MODEL")
    or Path.home() / "NovelMakerData/tts_voices/kokoro-v1.0.onnx"
)
VOICES = Path(
    os.environ.get("KOKORO_VOICES")
    or Path.home() / "NovelMakerData/tts_voices/voices-v1.0.bin"
)


def main() -> None:
    kokoro = None
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if kokoro is None:
                import numpy as np  # noqa: F401  (kokoro needs it)
                import onnxruntime as ort
                from kokoro_onnx import Kokoro

                options = ort.SessionOptions()
                options.intra_op_num_threads = 2
                options.inter_op_num_threads = 1
                session = ort.InferenceSession(
                    str(MODEL), options, providers=["CPUExecutionProvider"]
                )
                kokoro = Kokoro.from_session(session, str(VOICES))
            voice = request.get("voice") or "af_heart"
            lang = "en-gb" if voice[:1] == "b" else "en-us"
            samples, rate = kokoro.create(
                request["text"],
                voice=voice,
                speed=float(request.get("speed", 1.0)),
                lang=lang,
            )
            import numpy as np

            pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
            with wave.open(request["out"], "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(rate)
                w.writeframes(pcm)
            answer = {
                "ok": True,
                "out": request["out"],
                "seconds": round(len(samples) / rate, 2),
            }
        except Exception as e:  # reported to the app, never fatal to the worker
            answer = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        sys.stdout.write(json.dumps(answer) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
