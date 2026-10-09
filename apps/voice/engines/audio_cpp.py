"""TTS through audio.cpp's `audiocpp_server`: one C++ (ggml) runtime for many
speech model families (AuK, Irodori-TTS, OmniVoice ...), built here from source
with Vulkan (models/voice/bin/audio.cpp-src; the prebuilt Linux binaries need
AVX-512, which this CPU lacks).

A row names the audio.cpp `family`, its `task` and any `session_options`;
loading the row starts one server on a free local port for that model, close()
stops it. The process rules are breeze_cpp's, with its helpers: the server
stays in the voice backend's process group, each backend keeps
<row>@<backend pid>.pid, and clear_stale stops what a dead backend left.

Voices are profiles (profiles.py, the row's `profiles` folder): a profile in
one of the row's `languages` is a voice id. The line's mood tag ("[angry] ...")
picks the profile's clip for that mood, else its calm clip, as the voice to
clone; the row's `expressive` style (expressive.py) writes the tags the way the
model reads them. Other row fields read here:
  options                      request options sent every time
  prompt                       words wrapped for the model: "...{text}..." (AuK)
  ref_text: true               also send the clip's words (OmniVoice)
  duration: "estimate"         send duration_sec worked out from the text (AuK,
                               which otherwise copies the clip's length)
  speed_option, speed_invert   how the speed setting reaches the model
  tasks                        more model ids for profiles.py, {"edit": "gen"}
  design_option, design_options  how profiles.py designs a voice: the request
                               option that carries the description
                               ("instruction" by default, AuK's is "instruct")
  backend, seed, load_timeout_s
API: audio.cpp v0.9.1 app/server/README.md.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import numpy as np

import expressive
import profiles
from engines.breeze_cpp import free_port, state_dir, stop_stale

SPEAK = "speak"
_CJK = re.compile(r"[぀-ヿ㐀-鿿豈-﫿가-힯]")
_WORD = re.compile(r"[A-Za-z0-9']+")


def estimate_seconds(text: str, row: dict | None = None) -> float:
    """How long the words take at an easy pace: per word, per CJK character."""
    r = row or {}
    words = len(_WORD.findall(_CJK.sub(" ", text)))
    chars = len(_CJK.findall(text))
    s = float(r.get("seconds_per_word") or 0.38) * words
    s += float(r.get("seconds_per_char") or 0.15) * chars
    return round(s + 0.5, 2)


def decode_audio(data: bytes) -> tuple[np.ndarray, int]:
    """A wav body (or audio.cpp's JSON with base64 wav) to float32 mono."""
    if data[:1] == b"{":
        d = json.loads(data)
        b64 = d.get("audio") or d.get("data") or d.get("audio_base64") or ""
        if not b64:
            raise RuntimeError(f"audio.cpp sent no audio: {data[:200]!r}")
        data = base64.b64decode(str(b64).split(",")[-1])
    with wave.open(io.BytesIO(data)) as w:
        rate, width, ch = w.getframerate(), w.getsampwidth(), w.getnchannels()
        raw = w.readframes(w.getnframes())
    if width == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f"audio.cpp sent {width * 8}-bit audio")
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, rate


def clear_stale(row: dict, files: dict[str, Path]) -> None:
    """Stop servers a dead backend left for this row (this process's own are
    left alone: one may be loading right now)."""
    stop_stale(state_dir(), row["id"], files["server"], mine=False)


class Engine:
    def __init__(self, row: dict, files: dict[str, Path], threads: int):
        self.row = row
        self.server = files["server"]
        self.model = files["model"]
        self.profiles_dir = files.get("profiles")
        self.languages = list(row.get("languages") or [])
        self.default_voice = row.get("default_voice") or ""
        self.style = expressive.style(row.get("expressive") or "")
        self.tasks = dict(row.get("tasks") or {})
        sd = state_dir()
        sd.mkdir(parents=True, exist_ok=True)
        self.pidfile = sd / f"{row['id']}@{os.getpid()}.pid"
        self.config = sd / f"{row['id']}@{os.getpid()}.json"
        self.log_path = sd / f"{row['id']}.log"
        stop_stale(sd, row["id"], self.server)
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        entries = [self._entry(SPEAK, row.get("task") or "tts")]
        entries += [self._entry(k, v) for k, v in self.tasks.items()]
        cfg = {
            "host": "127.0.0.1",
            "port": self.port,
            "backend": row.get("backend") or "vulkan",
            "device": 0,
            "threads": max(1, int(threads)),
            "lazy_load": True,
            "max_loaded_models": 1,
            "models": entries,
        }
        self.config.write_text(json.dumps(cfg, ensure_ascii=False))
        runtime = files.get("runtime") or self.server.parent
        with open(self.log_path, "wb") as log:
            self.proc: subprocess.Popen | None = subprocess.Popen(
                [str(self.server), "--config", str(self.config), "--no-ui"],
                cwd=str(runtime),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        self.pidfile.write_text(f"{self.proc.pid} {os.getpid()}\n")
        try:
            self._wait_ready(float(row.get("load_timeout_s") or 120))
        except BaseException:
            self.close()
            raise

    def _entry(self, mid: str, task: str) -> dict:
        e = {"id": mid, "family": self.row["family"], "path": str(self.model)}
        e.update(task=task, mode="offline")
        if self.row.get("session_options"):
            e["session_options"] = dict(self.row["session_options"])
        return e

    def _log_tail(self) -> str:
        try:
            return self.log_path.read_text(errors="replace").strip()[-300:]
        except OSError:
            return ""

    def _wait_ready(self, timeout: float) -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.proc is None or self.proc.poll() is not None:
                raise RuntimeError(f"audiocpp_server stopped: {self._log_tail()}")
            try:
                with urllib.request.urlopen(self.url + "/health", timeout=2):
                    return
            except OSError:
                time.sleep(0.25)
        raise RuntimeError(f"audiocpp_server did not start within {timeout:.0f} s")

    def _post(self, path: str, body: dict, timeout: float = 600) -> bytes:
        req = urllib.request.Request(
            self.url + path,
            data=json.dumps(body, ensure_ascii=False).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"audiocpp_server said {e.code}: {e.read()[:200]!r}")

    # ------------------------------------------------------------ voices

    def voice_profiles(self) -> dict[str, dict]:
        found = profiles.load(self.profiles_dir)
        return profiles.for_languages(found, self.languages)

    def voices(self) -> list[str]:
        return sorted(self.voice_profiles())

    def profile(self, voice: str) -> dict:
        found = self.voice_profiles()
        p = found.get(voice) or found.get(self.default_voice)
        if p is None and found:
            p = found[sorted(found)[0]]
        if p is None:
            langs = ", ".join(self.languages) or "any language"
            raise RuntimeError(f"no voice profile in {langs}: add one (profiles.py)")
        return p

    # ------------------------------------------------------------ speech

    def request(self, text: str, voice: str, speed: float) -> dict:
        """The /v1/audio/speech body for one line (no server needed)."""
        from engines import InputError

        pieces = expressive.parse(text)
        say = expressive.render(pieces, self.style)
        if not re.search(r"\w", say):
            raise InputError("nothing to say")
        prof = self.profile(voice)
        self.used_voice = prof["id"]
        wav, words = profiles.clip(prof, expressive.mood(pieces))
        row = self.row
        opts = dict(row.get("options") or {})
        sp = float(speed or 1.0)
        if row.get("duration") == "estimate":
            opts["duration_sec"] = round(estimate_seconds(say, row) / sp, 2)
        elif row.get("speed_option") and sp != 1.0:
            opts[row["speed_option"]] = round(
                1 / sp if row.get("speed_invert") else sp, 3
            )
        prompt = row.get("prompt") or "{text}"
        if '"{text}"' in prompt:
            say = say.replace('"', "'")
        body = {"model": SPEAK, "input": prompt.replace("{text}", say)}
        body["voice_ref"] = {"type": "path", "path": str(wav)}
        if row.get("ref_text") and words:
            body["reference_text"] = words
        if row.get("seed") is not None:
            body["seed"] = int(row["seed"])
        body["options"] = opts
        return body

    def synthesize(self, text: str, voice: str, speed: float) -> tuple[np.ndarray, int]:
        audio, rate = decode_audio(
            self._post("/v1/audio/speech", self.request(text, voice, speed))
        )
        if len(audio) < rate // 20:
            raise RuntimeError("audio.cpp made no audio")
        return audio, rate

    # ------------------------------------------------------- profile tools

    def design(self, text: str, describe: str, out: Path) -> Path:
        """A new voice from a description, speaking `text`, saved to `out`."""
        row = self.row
        opts = dict(row.get("options") or {})
        opts.update(row.get("design_options") or {})
        opts[row.get("design_option") or "instruction"] = describe
        if row.get("duration") == "estimate":
            opts["duration_sec"] = estimate_seconds(text, row)
        mid = "design" if "design" in self.tasks else SPEAK
        body = {"model": mid, "input": text, "options": opts}
        if row.get("seed") is not None:
            body["seed"] = int(row["seed"])
        return self._save(self._post("/v1/audio/speech", body), out)

    def edit(self, src: Path, instruction: str, out: Path) -> Path:
        """An AuK-style edit of a clip by an instruction, saved to `out`."""
        if "edit" not in self.tasks:
            raise RuntimeError(f"{self.row['id']} has no edit task")
        body = {"model": "edit", "request": {"text": instruction, "audio": str(src)}}
        if self.row.get("seed") is not None:
            body["request"]["seed"] = int(self.row["seed"])
        return self._save(self._post("/v1/tasks/run", body), out)

    def _save(self, data: bytes, out: Path) -> Path:
        import engines

        audio, rate = decode_audio(data)
        if len(audio) < rate // 20:
            raise RuntimeError("audio.cpp made no audio")
        Path(out).write_bytes(engines.wav_bytes(audio, rate))
        return Path(out)

    def close(self) -> None:
        p, self.proc = self.proc, None
        if p is None:
            return
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=5)
        try:  # only our own files: a newer server may own them by now
            if self.pidfile.read_text().split()[0] == str(p.pid):
                self.pidfile.unlink()
                self.config.unlink(missing_ok=True)
        except (OSError, IndexError):
            pass
