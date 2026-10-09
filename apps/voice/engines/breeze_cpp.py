"""TTS through Breeze-TTS-2.cpp's `breeze-server` (Breeze TTS 2, a 3B GGUF).

The near-human voice. Loading the row starts one server on a free local port
(the model lives in that process, about 3 GB at q4_k); close() stops it. The
server stays in the voice backend's process group, so Forge stopping the
backend (killpg) stops it too. Each backend keeps its own pid file,
<row>@<backend pid>.pid, so the next load (or clear_stale before a memory
check) stops a server a crashed backend left behind but never one a live
backend, such as a second scratch backend, is using.

Cloning: the row's `ref` clip and `ref_text` become the saved voice named by
`default_voice` (a few kB, <model dir>/voices/<name>.breeze, made once). Any
other saved voice in that folder is a voice id too; an unknown one falls back
to the default. A voice profile (profiles.py, the row's `profiles` folder, in
one of its `languages`) is a voice as well: its calm clip is saved on first
use as p-<id>-<hash of the clip and its words>, so a new calm clip makes a new
saved voice. Moods come from the spoken direction, not from mood clips. The model has no speed control, so speed is ignored; the
server has no thread flag, so `threads` goes in as OMP_NUM_THREADS.
API: Breeze-TTS-2.cpp v0.1.0 docs/server.md and docs/voices.md.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import numpy as np

import expressive
import profiles
from engines import pick_file

RATE = 24000


def state_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "forge" / "voice"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def multipart(fields: dict[str, str], files: dict[str, Path]) -> tuple[bytes, str]:
    """A multipart/form-data body and its Content-Type."""
    b = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        head = f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'
        parts.append(head.encode() + v.encode() + b"\r\n")
    for k, p in files.items():
        head = (
            f'--{b}\r\nContent-Disposition: form-data; name="{k}"; '
            f'filename="{p.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'
        )
        parts.append(head.encode() + p.read_bytes() + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={b}"


def parent_pid(pid: int) -> int | None:
    """A process's parent pid from /proc/<pid>/stat, or None."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return int(stat[stat.rindex(")") + 2 :].split()[1])
    except (OSError, ValueError, IndexError):
        return None


def _stop(pid: int, binary: Path) -> None:
    """SIGTERM, then SIGKILL, a process that is still `binary`."""
    try:
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return
    if str(binary) not in [os.fsdecode(a) for a in argv[:2]]:
        return
    for sig, wait in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 2.0)):
        try:
            os.kill(pid, sig)
        except OSError:
            break
        end = time.monotonic() + wait
        while time.monotonic() < end and Path(f"/proc/{pid}").exists():
            time.sleep(0.1)
        if not Path(f"/proc/{pid}").exists():
            break


def stop_stale(sd: Path, row_id: str, binary: Path, mine: bool = True) -> None:
    """Stop the servers pid files in `sd` name for a row, unless a live backend
    owns them. A file <row>@<backend>.pid holds "<server pid> <backend pid>":
    a server whose parent is still that backend stays, except one of this
    process's own when `mine` (a load replacing a server it lost track of).
    Anything else that is still `binary` is stopped and its file removed; an
    old <row>.pid (the server pid alone) counts as left behind."""
    files = [sd / f"{row_id}.pid", *sorted(sd.glob(f"{glob.escape(row_id)}@*.pid"))]
    for pf in files:
        try:
            nums = [int(x) for x in pf.read_text().split()[:2]]
            pid = nums[0]
        except (OSError, ValueError, IndexError):
            pf.unlink(missing_ok=True)
            continue
        owner = nums[1] if len(nums) > 1 else None
        if owner is not None and parent_pid(pid) == owner:
            if owner != os.getpid() or not mine:
                continue
        _stop(pid, binary)
        pf.unlink(missing_ok=True)


def clear_stale(row: dict, files: dict[str, Path]) -> None:
    """Stop servers a dead backend left for this row (this process's own are
    left alone: one may be loading right now)."""
    stop_stale(state_dir(), row["id"], files["server"], mine=False)


class Engine:
    def __init__(self, row: dict, files: dict[str, Path], threads: int):
        self.model = pick_file(files, ("model", "gguf"), ".gguf")
        self.server = files["server"]
        self.ref = files.get("ref")
        self.ref_text = row.get("ref_text") or ""
        self.default_voice = row.get("default_voice") or "default"
        self.instruction = row.get("instruction") or ""
        self.style = (
            expressive.style(row["expressive"]) if row.get("expressive") else None
        )
        self.voices_dir = self.model.parent / "voices"
        self.voices_dir.mkdir(exist_ok=True)
        self.profiles_dir = files.get("profiles")
        self.languages = list(row.get("languages") or [])
        self._profile_voices: dict[tuple, str] = {}
        sd = state_dir()
        sd.mkdir(parents=True, exist_ok=True)
        self.pidfile = sd / f"{row['id']}@{os.getpid()}.pid"
        self.log_path = sd / f"{row['id']}.log"
        stop_stale(sd, row["id"], self.server)
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        cmd = [str(self.server), str(self.model), "--host", "127.0.0.1"]
        cmd += ["--port", str(self.port), "--ws-port", "-1"]
        cmd += ["--voices-dir", str(self.voices_dir)]
        if row.get("device") == "cpu":
            cmd.append("--cpu")
        env = dict(os.environ, OMP_NUM_THREADS=str(max(1, int(threads))))
        with open(self.log_path, "wb") as log:
            self.proc: subprocess.Popen | None = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
            )
        self.pidfile.write_text(f"{self.proc.pid} {os.getpid()}\n")
        try:
            self._wait_ready(float(row.get("load_timeout_s") or 240))
            if self.default_voice not in self.saved_voices():
                self._save_default_voice()
        except BaseException:
            self.close()
            raise

    def _call(self, method: str, path: str, body=None, ctype="", timeout=10.0):
        req = urllib.request.Request(self.url + path, data=body, method=method)
        if ctype:
            req.add_header("Content-Type", ctype)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), r.headers

    def _log_tail(self) -> str:
        try:
            return self.log_path.read_text(errors="replace").strip()[-300:]
        except OSError:
            return ""

    def _wait_ready(self, timeout: float) -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.proc is None or self.proc.poll() is not None:
                raise RuntimeError(f"breeze-server stopped: {self._log_tail()}")
            try:
                body, _ = self._call("GET", "/health", timeout=2)
                if json.loads(body).get("status") == "ok":
                    return
            except (OSError, ValueError):
                pass
            time.sleep(0.25)
        raise RuntimeError(f"breeze-server did not start within {timeout:.0f} s")

    def _save_default_voice(self) -> None:
        if not (self.ref and self.ref.exists() and self.ref_text):
            raise RuntimeError("the row needs a ref clip and ref_text for its voice")
        body, ctype = multipart(
            {"ref_text": self.ref_text, "name": self.default_voice},
            {"ref_audio": self.ref},
        )
        self._call("POST", "/v1/voices", body, ctype, timeout=120)

    def saved_voices(self) -> list[str]:
        body, _ = self._call("GET", "/v1/voices")
        return sorted(v["id"] for v in json.loads(body) if v.get("saved"))

    def voice_profiles(self) -> dict[str, dict]:
        found = profiles.load(self.profiles_dir)
        return profiles.for_languages(found, self.languages)

    def voices(self) -> list[str]:
        """The saved voices and the profiles (the p-... copies left out)."""
        saved = [v for v in self.saved_voices() if not v.startswith("p-")]
        return sorted(set(saved) | set(self.voice_profiles()))

    def voice_id(self, voice: str) -> str:
        """The server's voice for a voice name: a profile's saved copy (made
        here the first time), else the name itself (unknown ones end on the
        default through the server's 404)."""
        voice = voice or self.default_voice
        p = self.voice_profiles().get(voice)
        if voice == self.default_voice or p is None:
            return voice
        wav, words = profiles.clip(p, None)
        wav = Path(wav)
        if not words.strip():
            from engines import InputError

            raise InputError(f"voice {voice}: its calm clip has no words")
        st = wav.stat()
        key = (str(wav), st.st_mtime_ns, st.st_size, words)
        if key not in self._profile_voices:
            digest = hashlib.sha1(wav.read_bytes() + words.encode()).hexdigest()
            name = f"p-{voice}-{digest[:10]}"
            if name not in self.saved_voices():
                body, ctype = multipart(
                    {"ref_text": words, "name": name}, {"ref_audio": wav}
                )
                try:
                    self._call("POST", "/v1/voices", body, ctype, timeout=120)
                except urllib.error.HTTPError as e:
                    raise RuntimeError(
                        f"breeze-server would not take voice {voice}: "
                        f"{e.code} {e.read()[:200]!r}"
                    )
            self._profile_voices[key] = name
        return self._profile_voices[key]

    def direction(self, text: str) -> dict[str, str]:
        """The text and delivery fields for a line. With an expressive style
        (shared/voice_emotions.json) the mood tag becomes the spoken direction
        and laughs or sighs Breeze's own vocal tags, which need more cfg_scale."""
        fields = {"text": text}
        if self.instruction:
            fields["instruction"] = self.instruction
        st = self.style
        if st is None:
            return fields
        pieces = expressive.parse(text)
        fields["text"] = expressive.render(pieces, st)
        if not any(c.isalnum() for c in fields["text"]):
            from engines import InputError

            raise InputError("nothing to say")
        mood = expressive.mood(pieces)
        if mood and (st.get("instructions") or {}).get(mood):
            fields["instruction"] = st["instructions"][mood]
        marks = st.get("map") or {}
        if any(
            k == "tag" and expressive.kind(v) == "sound" and v in marks
            for k, v in pieces
        ):
            fields["cfg_scale"] = str(st.get("sound_cfg_scale") or 2.5)
        return fields

    def synthesize(self, text: str, voice: str, speed: float) -> tuple[np.ndarray, int]:
        fields = self.direction(text)
        fields["voice_id"] = self.voice_id(voice)
        self.used_voice = voice or self.default_voice
        remade = False
        busy_until = time.monotonic() + 60
        while True:
            body = urllib.parse.urlencode(fields).encode()
            try:
                pcm, headers = self._call(
                    "POST",
                    "/v1/audio/speech",
                    body,
                    "application/x-www-form-urlencoded",
                    timeout=180,
                )
                break
            except urllib.error.HTTPError as e:
                if e.code == 409 and time.monotonic() < busy_until:
                    time.sleep(0.5)
                    continue
                lost = fields["voice_id"]
                if e.code == 404 and lost.startswith("p-") and not remade:
                    remade = True  # the server lost a profile's copy: save it again
                    self._profile_voices = {
                        k: n for k, n in self._profile_voices.items() if n != lost
                    }
                    fields["voice_id"] = self.voice_id(voice)
                    continue
                if e.code == 404 and lost != self.default_voice:
                    fields["voice_id"] = self.used_voice = self.default_voice
                    continue
                raise RuntimeError(f"breeze-server said {e.code}: {e.read()[:200]!r}")
        rate = int(headers.get("X-Sample-Rate") or RATE)
        pcm = pcm[: len(pcm) // 2 * 2]
        if not pcm:
            raise RuntimeError("breeze-server sent no audio")
        return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0, rate

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
        try:  # only our own pid file: a newer server may own it by now
            if self.pidfile.read_text().split()[0] == str(p.pid):
                self.pidfile.unlink()
        except (OSError, IndexError):
            pass
