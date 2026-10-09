#!/usr/bin/env python3
"""Speak text with the Kokoro voices NovelForge already has installed.

Nyarch Assistant runs inside a Flatpak sandbox that has no ONNX runtime, and
installing a second copy of Kokoro there would cost a few hundred megabytes for
no benefit.  Instead the assistant's "custom command" text-to-speech handler
shells out to this script through `flatpak-spawn --host`, and this script runs
inside NovelForge's virtualenv, which already carries `kokoro_onnx`,
`onnxruntime` and the 325 MB voice model.

Usage:
    forge_tts.py <output.wav> <text...>

Environment:
    FORGE_TTS_VOICE   Kokoro voice id, default "am_michael"
    FORGE_TTS_SPEED   playback speed 0.5-2.0, default "1.0"
    FORGE_TTS_MODEL   directory holding kokoro-v1.0.onnx and voices-v1.0.bin
"""

import os
import re
import sys
import wave

HOME = os.path.expanduser("~")
DEFAULT_MODEL_DIR = os.path.join(HOME, "NovelMakerData", "tts_voices")
SAMPLE_RATE = 24000
# Kokoro's phonemiser degrades on very long inputs, so feed it a paragraph at a
# time.  This is well under the limit while still sounding continuous.
MAX_CHUNK_CHARS = 400


def find_model_dir() -> str:
    """Return the directory holding the Kokoro model, or exit with a message."""
    candidates = [
        os.environ.get("FORGE_TTS_MODEL", ""),
        DEFAULT_MODEL_DIR,
        os.path.join(
            HOME,
            ".var/app/moe.nyarchlinux.assistant/config/models/kokoro_cache",
        ),
    ]
    for directory in candidates:
        if not directory:
            continue
        model = os.path.join(directory, "kokoro-v1.0.onnx")
        voices = os.path.join(directory, "voices-v1.0.bin")
        if os.path.exists(model) and os.path.exists(voices):
            return directory
    sys.exit(
        "No Kokoro model found. Looked in: " + ", ".join(c for c in candidates if c)
    )


def split_text(text: str) -> list[str]:
    """Break text into chunks Kokoro reads cleanly, preferring sentence ends."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?;:])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > MAX_CHUNK_CHARS:
            cut = sentence.rfind(" ", 0, MAX_CHUNK_CHARS)
            cut = cut if cut > 0 else MAX_CHUNK_CHARS
            chunks.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if len(current) + len(sentence) + 1 > MAX_CHUNK_CHARS:
            if current:
                chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def synthesise(text: str, out_path: str) -> None:
    """Render text to a 16-bit mono WAV at Kokoro's native sample rate."""
    import numpy as np
    from kokoro_onnx import Kokoro

    model_dir = find_model_dir()
    kokoro = Kokoro(
        os.path.join(model_dir, "kokoro-v1.0.onnx"),
        os.path.join(model_dir, "voices-v1.0.bin"),
    )
    voice = os.environ.get("FORGE_TTS_VOICE", "am_michael")
    speed = max(0.5, min(2.0, float(os.environ.get("FORGE_TTS_SPEED", "1.0"))))

    parts = []
    for chunk in split_text(text):
        samples, _rate = kokoro.create(chunk, voice=voice, speed=speed, lang="en-us")
        audio = np.asarray(samples, dtype=np.float32)
        parts.append((np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with wave.open(out_path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        for part in parts:
            out.writeframes(part.tobytes())
            # A short breath between paragraphs stops sentences running together.
            out.writeframes(b"\x00\x00" * int(SAMPLE_RATE * 0.15))


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    out_path = sys.argv[1]
    text = " ".join(sys.argv[2:])
    synthesise(text, out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
