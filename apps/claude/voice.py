"""Speaking replies aloud with Kokoro, without installing it twice.

Kokoro (kokoro-onnx and its model files) already lives in PanelForge's venv
and ~/NovelMakerData/tts_voices, shared with NovelForge. So this app starts
PanelForge's Python on ``tts_worker.py`` and talks to it over stdin/stdout,
one JSON line each way. The worker is started on the first request, runs at
low priority on 2 threads (local-compute-contention: the laptop must stay
usable), and is stopped after IDLE_SECONDS without a request, handing its
memory back.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

APP = Path(__file__).resolve().parent
PYTHON = Path(
    os.environ.get("FORGE_KOKORO_PYTHON")
    or APP.parent / "panelforge" / ".venv" / "bin" / "python"
)
WORKER = APP / "tts_worker.py"
IDLE_SECONDS = 300
MAX_CHARS = 700
SERVICE_URL = os.environ.get("FORGE_VOICE_URL", "http://127.0.0.1:8467")


def service_tts(text: str, voice: str = "", speed: float = 1.0) -> bytes | None:
    """WAV bytes from the Forge voice service (apps/voice), or None when it
    is not running or fails, so the caller falls back to its own worker."""
    body = {"text": text, "app": "claude", "speed": speed}
    if voice:
        body["voice"] = voice
    request = urllib.request.Request(
        f"{SERVICE_URL}/api/tts",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Forge": "1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as r:
            data = r.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return data if data[:4] == b"RIFF" else None


def clean_text(text: str, limit: int = MAX_CHARS) -> str:
    """Markdown to something worth hearing: no code, links as their words,
    no symbols, cut at a sentence end near the limit."""
    text = re.sub(r"```.*?```", " (code) ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "a link", text)
    text = re.sub(r"^\s*\|.*\|\s*$", "", text, flags=re.M)  # tables
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"[*_~>#|]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[: end + 1] if end > limit // 3 else cut.rsplit(" ", 1)[0] + "…").strip()


class Voice:
    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.proc: subprocess.Popen | None = None
        self.last_used = 0.0
        self._lock = threading.Lock()
        self._watch: threading.Thread | None = None

    def available(self) -> tuple[bool, str]:
        if not PYTHON.exists():
            return False, f"Kokoro's Python was not found at {PYTHON}"
        return True, ""

    def _start(self) -> subprocess.Popen:
        env = {**os.environ, "OMP_NUM_THREADS": "2", "ORT_NUM_THREADS": "2"}
        self.proc = subprocess.Popen(
            [str(PYTHON), str(WORKER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
            preexec_fn=lambda: os.nice(10),
        )
        if self._watch is None or not self._watch.is_alive():
            self._watch = threading.Thread(target=self._idle_loop, daemon=True)
            self._watch.start()
        return self.proc

    def _idle_loop(self) -> None:
        while True:
            time.sleep(15)
            with self._lock:
                if self.proc is None:
                    return
                if time.time() - self.last_used > IDLE_SECONDS:
                    self._stop_locked()
                    return

    def _stop_locked(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def say(self, text: str, voice: str, speed: float = 1.0) -> Path:
        """Synthesize to a WAV file and return its path. RuntimeError on failure."""
        spoken = clean_text(text)
        if not spoken:
            raise RuntimeError("Nothing to say")
        ok, why = self.available()
        if not ok:
            raise RuntimeError(why)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        for old in sorted(self.out_dir.glob("*.wav"))[:-20]:
            old.unlink(missing_ok=True)  # keep the last 20 clips only
        out = self.out_dir / f"{int(time.time())}-{uuid.uuid4().hex[:6]}.wav"
        request = {"text": spoken, "voice": voice, "speed": speed, "out": str(out)}
        with self._lock:
            self.last_used = time.time()
            proc = (
                self.proc if self.proc and self.proc.poll() is None else self._start()
            )
            assert proc.stdin and proc.stdout
            try:
                proc.stdin.write(json.dumps(request) + "\n")
                proc.stdin.flush()
                line = proc.stdout.readline()
            except (BrokenPipeError, OSError) as e:
                self._stop_locked()
                raise RuntimeError(f"The voice worker stopped ({e})")
            self.last_used = time.time()
        if not line:
            self.stop()
            raise RuntimeError("The voice worker exited without speaking")
        answer = json.loads(line)
        if not answer.get("ok"):
            raise RuntimeError(answer.get("error") or "Kokoro failed")
        return out
