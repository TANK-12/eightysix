"""Acchan's voice: replies read aloud and a microphone that types for you.

Nothing is installed for this (Emerson, 2026-09-27: "make the Jan in Acchan
have TTS and STT using stuff I already have"):

  speaking   Kokoro, through nyarch/forge_tts.py run by NovelForge's own
             virtualenv (kokoro_onnx and the 325 MB model are already there);
             Piper from the same virtualenv when a Piper voice is picked or
             Kokoro is missing.
  hearing    whisper.cpp's whisper-cli and the ggml-tiny.en model that the
             Nyarch Assistant flatpak already built and downloaded; ffmpeg
             turns the browser's recording into the 16 kHz WAV it wants.

The shared Forge voice service (apps/voice, port 8467) is tried first for
both halves; the paths above are the fallback when it is not running.

Both run at a lower priority (nice) with a few threads, so a chat with voice
does not stall the rest of the laptop.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import json
from pathlib import Path

HOME = Path.home()
FORGE = HOME / "Forge"
NOVELFORGE_PY = FORGE / "apps" / "novelforge" / ".venv" / "bin" / "python"
KOKORO_SCRIPT = FORGE / "nyarch" / "forge_tts.py"
PIPER = FORGE / "apps" / "novelforge" / ".venv" / "bin" / "piper"
PIPER_VOICES = HOME / "NovelMakerData" / "tts_voices"
WHISPER_DIR = (
    HOME / ".var/app/moe.nyarchlinux.assistant/config/models/whisper/whisper.cpp"
)
WHISPER_CLI = WHISPER_DIR / "build" / "bin" / "whisper-cli"
WHISPER_MODEL = WHISPER_DIR / "models" / "ggml-tiny.en.bin"

# voice id -> label; "piper:<model>" is a Piper voice file in PIPER_VOICES
VOICES = {
    "am_michael": "Michael (Kokoro)",
    "af_heart": "Heart (Kokoro)",
    "af_bella": "Bella (Kokoro)",
    "bf_emma": "Emma, British (Kokoro)",
    "bm_george": "George, British (Kokoro)",
    "piper:en_US-ryan-high": "Ryan (Piper, lighter)",
}
DEFAULT_VOICE = "am_michael"
MAX_SPOKEN = 1500  # characters read aloud from one reply
THREADS = "4"


SERVICE = os.environ.get("FORGE_VOICE_URL", "http://127.0.0.1:8467")
SERVICE_TIMEOUT = 90


class VoiceError(RuntimeError):
    pass


def _service(path: str, data: bytes, content_type: str) -> bytes | None:
    """POST to the shared voice service; None when it is down or refuses,
    so the caller falls back to the local engines."""
    request = urllib.request.Request(
        SERVICE + path,
        data=data,
        headers={"Content-Type": content_type, "X-Forge": "1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=SERVICE_TIMEOUT) as answer:
            return answer.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None


def service_up() -> bool:
    try:
        with urllib.request.urlopen(SERVICE + "/api/status", timeout=1) as answer:
            return answer.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def status() -> dict:
    """Which halves work on this laptop."""
    kokoro = NOVELFORGE_PY.exists() and KOKORO_SCRIPT.exists()
    shared = service_up()
    return {
        "service": shared,
        "speak": shared or kokoro or PIPER.exists(),
        "listen": shared
        or WHISPER_CLI.exists()
        and WHISPER_MODEL.exists()
        and bool(shutil.which("ffmpeg")),
        "voices": VOICES,
    }


def speech_text(reply: str) -> str:
    """The part of a reply worth hearing: code blocks are named, not read;
    links keep their words; markup goes."""
    text = re.sub(r"```.*?(```|$)", " (the code is in the chat) ", reply, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "a link", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^\s{0,3}(#+|[-*>]|\d+\.)\s+", "", text, flags=re.M)
    text = re.sub(r"[*_~|]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_SPOKEN:
        cut = text[:MAX_SPOKEN]
        text = cut[: cut.rfind(" ")] if " " in cut else cut
    return text


def _run(cmd: list[str], timeout: int, env: dict | None = None) -> None:
    try:
        done = subprocess.run(
            ["nice", "-n", "10", *cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise VoiceError(f"{Path(cmd[0]).name} took longer than {timeout} s") from exc
    if done.returncode != 0:
        raise VoiceError((done.stderr or done.stdout).strip()[-300:] or "failed")


def speak(text: str, voice: str = DEFAULT_VOICE) -> bytes:
    """WAV bytes of `text` spoken (already cleaned by the caller or not)."""
    words = speech_text(text)
    if not words:
        raise VoiceError("Nothing to say.")
    body = json.dumps({"text": words, "app": "acchan"}).encode()
    wav = _service("/api/tts", body, "application/json")
    if wav and wav[:4] == b"RIFF":
        return wav
    return _speak_local(words, voice)


def _speak_local(words: str, voice: str) -> bytes:
    """The old path: Kokoro or Piper from NovelForge's virtualenv."""
    with tempfile.TemporaryDirectory(prefix="acchan-voice-") as tmp:
        out = Path(tmp) / "say.wav"
        piper = voice.startswith("piper:") or not KOKORO_SCRIPT.exists()
        if piper:
            name = voice.split(":", 1)[1] if voice.startswith("piper:") else ""
            model = PIPER_VOICES / f"{name or 'en_US-ryan-high'}.onnx"
            src = Path(tmp) / "say.txt"
            src.write_text(words)
            _run(
                [
                    "sh",
                    "-c",
                    f'"{PIPER}" --model "{model}" --output_file "{out}" < "{src}"',
                ],
                timeout=120,
            )
        else:
            env = {
                **os.environ,
                "FORGE_TTS_VOICE": voice if voice in VOICES else DEFAULT_VOICE,
                "OMP_NUM_THREADS": THREADS,
            }
            _run(
                [str(NOVELFORGE_PY), str(KOKORO_SCRIPT), str(out), words],
                timeout=120,
                env=env,
            )
        return out.read_bytes()


def transcribe(audio: bytes, suffix: str = ".webm") -> str:
    """What was said in a recording (any format ffmpeg reads)."""
    if not audio:
        raise VoiceError("The recording was empty.")
    kind = {".wav": "audio/wav", ".ogg": "audio/ogg", ".m4a": "audio/mp4"}.get(
        suffix, "audio/webm"
    )
    heard = _service("/api/stt?app=acchan", audio, kind)
    if heard is not None:
        try:
            said = json.loads(heard).get("text")
        except (ValueError, AttributeError):
            said = None
        if isinstance(said, str):
            return re.sub(r"\s+", " ", said).strip()
    return _transcribe_local(audio, suffix)


def _transcribe_local(audio: bytes, suffix: str) -> str:
    """The old path: ffmpeg to 16 kHz, then Nyarch's whisper-cli."""
    with tempfile.TemporaryDirectory(prefix="acchan-voice-") as tmp:
        raw = Path(tmp) / f"in{suffix if suffix.startswith('.') else '.webm'}"
        raw.write_bytes(audio)
        wav = Path(tmp) / "in16.wav"
        _run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(raw),
                "-ar",
                "16000",
                "-ac",
                "1",
                str(wav),
            ],
            timeout=60,
        )
        txt = Path(tmp) / "out"
        _run(
            [
                str(WHISPER_CLI),
                "-m",
                str(WHISPER_MODEL),
                "-t",
                THREADS,
                "-nt",
                "-np",
                "-otxt",
                "-of",
                str(txt),
                "-f",
                str(wav),
            ],
            timeout=120,
        )
        heard = Path(f"{txt}.txt").read_text(errors="replace")
    heard = re.sub(r"\[(BLANK_AUDIO|MUSIC|NOISE)[^\]]*\]", " ", heard)
    return re.sub(r"\s+", " ", heard).strip()
