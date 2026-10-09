"""Voice service core: registry, settings, models, audio, playback, mic, PTT, routing.

Everything here is used by web_app.py; the push-to-talk state machine (`PTT`)
is pure (no audio, no threads) so it is unit-tested on its own.

Environment (all optional, mostly for tests):
    FORGE_SHARED_DIR       shared folder (registry, forge_voice.py, sounds)
    FORGE_MODELS_DIR       model home (default ~/Forge/models)
    FORGE_VOICE_REGISTRY   registry file instead of shared/voice_registry.json
    FORGE_VOICE_SETTINGS   settings file instead of ~/.config/forge/voice.json
    FORGE_VOICE_CAPTURE    a wav file read instead of the microphone
    FORGE_VOICE_PLAYER     player command instead of pw-play (gets a wav path)
    FORGE_ACCHAN_URL       default http://127.0.0.1:8451
    FORGE_CLAUDE_URL       default http://127.0.0.1:8445
"""

from __future__ import annotations

import copy
import http.client
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any, Callable

import numpy as np

import engines
import expressive
import profiles

ROOT = Path(__file__).resolve().parent
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR", ROOT.parent.parent / "shared"))
APPS_DIR = ROOT.parent
RATE = 16000
MAX_SECONDS = 120
MAX_BYTES = 20 * 1024 * 1024


class VoiceError(Exception):
    """A failure with a plain message for the user (HTTP 503)."""


class BadInput(Exception):
    """Bad request (HTTP 400)."""


# ---------------------------------------------------------------- registry


def models_home() -> Path:
    return Path(
        os.environ.get("FORGE_MODELS_DIR") or Path.home() / "Forge" / "models"
    ).expanduser()


def registry_path() -> Path:
    env = os.environ.get("FORGE_VOICE_REGISTRY")
    if env:
        return Path(env)
    shared = SHARED_DIR / "voice_registry.json"
    return shared if shared.exists() else ROOT / "tests" / "fixture_registry.json"


def load_registry() -> dict:
    data = json.loads(registry_path().read_text())
    data.setdefault("models", [])
    data.setdefault("defaults", {})
    data.setdefault("wake", {})
    return data


def model_row(reg: dict, model_id: str) -> dict:
    for row in reg["models"]:
        if row.get("id") == model_id:
            return row
    raise BadInput(f"unknown model: {model_id}")


def model_files(row: dict) -> dict[str, Path]:
    """Absolute paths of a row's files (relative to the model home, or ~/abs)."""
    out = {}
    home = models_home()
    for name, rel in (row.get("files") or {}).items():
        p = Path(rel).expanduser()
        if not p.is_absolute():
            cand = home / p
            alt = home / "voice" / row.get("kind", "") / row.get("id", "") / p
            p = cand if cand.exists() or not alt.exists() else alt
        out[name] = p
    for name, rel in (row.get("reuse") or {}).items():
        if name not in out or not out[name].exists():
            out[name] = Path(rel).expanduser()
    return out


def row_voices(row: dict) -> list[str]:
    """A model's voice names: its "voices" list, and for a cloning row (a
    "profiles" folder in its files) the profiles in its languages."""
    names = list(row.get("voices") or [])
    if "profiles" in (row.get("files") or {}):
        found = profiles.load(model_files(row)["profiles"])
        found = profiles.for_languages(found, row.get("languages") or [])
        names = sorted(set(names) | set(found))
    return names


def no_voice(row: dict) -> str | None:
    """Why a cloning row (a "profiles" folder in its files) cannot speak at
    all: no voice of its own in its languages. Asked before any load, so a
    missing profiles folder never loads a heavy model only to fail."""
    if "profiles" not in (row.get("files") or {}) or row_voices(row):
        return None
    langs = ", ".join(row.get("languages") or ["en"])
    return (
        f"{row.get('label', row['id'])} has no voice in {langs}: add one (profiles.py)"
    )


def needed_files(files: dict[str, Path]) -> dict[str, Path]:
    """The files a model needs on disk (a profiles folder is voices, not a file)."""
    return {k: p for k, p in files.items() if k != "profiles"}


def model_present(row: dict) -> bool:
    """Every model file is on disk."""
    files = needed_files(model_files(row))
    return bool(files) and all(p.exists() for p in files.values())


def profile_names(reg: dict) -> set[str]:
    """Every voice profile a cloning row (a "profiles" folder) can see."""
    names: set[str] = set()
    for row in reg.get("models", []):
        if "profiles" in (row.get("files") or {}):
            names |= set(profiles.load(model_files(row)["profiles"]))
    return names


# ---------------------------------------------------------------- settings

DEFAULT_SETTINGS: dict[str, Any] = {
    "stt": {"model": None},
    "tts": {"model": None, "voice": None, "speed": 1.0},
    "apps": {},
    "anywhere": {
        "target": "auto",
        "speak_replies": True,
        "earcons": True,
        "notify": True,
    },
    "ptt": {"hold_s": 0.35, "silence_s": 1.2, "max_s": 30},
    "resources": {"threads": 4, "cpus": "", "idle_unload_s": 300, "device": "cpu"},
    "max_chars": 1500,
}
TARGETS = ("auto", "jan", "claude", "text")
_APP_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")


def settings_path() -> Path:
    env = os.environ.get("FORGE_VOICE_SETTINGS")
    return Path(env) if env else Path.home() / ".config" / "forge" / "voice.json"


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_settings() -> dict:
    try:
        saved = json.loads(settings_path().read_text())
    except (OSError, ValueError):
        saved = {}
    return _merge(DEFAULT_SETTINGS, saved if isinstance(saved, dict) else {})


def _num(v, lo, hi, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
        raise BadInput(f"{what} must be a number from {lo} to {hi}")
    return v


def _check_model(reg: dict, v, kind: str, what: str):
    if v is None:
        return None
    if not isinstance(v, str) or model_row(reg, v).get("kind") != kind:
        raise BadInput(f"{what} must be a {kind} model id")
    return v


def _check_tts(reg: dict, d, what: str) -> dict:
    if not isinstance(d, dict):
        raise BadInput(f"{what} must be an object")
    out = {}
    for k, v in d.items():
        if k == "model":
            out[k] = _check_model(reg, v, "tts", f"{what}.model")
        elif k == "voice":
            if v is not None and (not isinstance(v, str) or len(v) > 60):
                raise BadInput(f"{what}.voice must be a short name")
            out[k] = v
        elif k == "speed":
            out[k] = _num(v, 0.5, 2.0, f"{what}.speed")
        else:
            raise BadInput(f"unknown setting {what}.{k}")
    return out


def _check_stt(reg: dict, d, what: str) -> dict:
    if not isinstance(d, dict) or set(d) - {"model"}:
        raise BadInput(f"{what} takes only model")
    return {"model": _check_model(reg, d.get("model"), "stt", f"{what}.model")}


def validate_patch(patch: Any, reg: dict) -> dict:
    """A checked copy of a partial settings object; BadInput on anything odd."""
    if not isinstance(patch, dict):
        raise BadInput("settings must be an object")
    out: dict[str, Any] = {}
    for key, val in patch.items():
        if key == "stt":
            out[key] = _check_stt(reg, val, "stt")
        elif key == "tts":
            out[key] = _check_tts(reg, val, "tts")
        elif key == "apps":
            if not isinstance(val, dict):
                raise BadInput("apps must be an object")
            apps = {}
            for name, d in val.items():
                if not _APP_NAME.match(name) or not isinstance(d, dict):
                    raise BadInput(f"bad app entry: {name}")
                a: dict[str, Any] = {}
                for k, v in d.items():
                    if k == "tts":
                        a[k] = _check_tts(reg, v, f"apps.{name}.tts")
                    elif k == "stt":
                        a[k] = _check_stt(reg, v, f"apps.{name}.stt")
                    elif k == "speak_replies":
                        if not isinstance(v, bool):
                            raise BadInput("speak_replies must be true or false")
                        a[k] = v
                    else:
                        raise BadInput(f"unknown setting apps.{name}.{k}")
                apps[name] = a
            out[key] = apps
        elif key == "anywhere":
            if not isinstance(val, dict):
                raise BadInput("anywhere must be an object")
            a = {}
            for k, v in val.items():
                if k == "target":
                    if v not in TARGETS:
                        raise BadInput(f"target must be one of {', '.join(TARGETS)}")
                elif k in ("speak_replies", "earcons", "notify"):
                    if not isinstance(v, bool):
                        raise BadInput(f"anywhere.{k} must be true or false")
                else:
                    raise BadInput(f"unknown setting anywhere.{k}")
                a[k] = v
            out[key] = a
        elif key == "ptt":
            limits = {"hold_s": (0.1, 2.0), "silence_s": (0.3, 5.0), "max_s": (2, 120)}
            if not isinstance(val, dict) or set(val) - set(limits):
                raise BadInput("ptt takes hold_s, silence_s, max_s")
            out[key] = {
                k: _num(v, limits[k][0], limits[k][1], f"ptt.{k}")
                for k, v in val.items()
            }
        elif key == "resources":
            if not isinstance(val, dict):
                raise BadInput("resources must be an object")
            r: dict[str, Any] = {}
            for k, v in val.items():
                if k == "threads":
                    r[k] = int(_num(v, 1, 12, "resources.threads"))
                elif k == "idle_unload_s":
                    r[k] = _num(v, 10, 86400, "resources.idle_unload_s")
                elif k == "cpus":
                    if not isinstance(v, str) or not re.fullmatch(r"[0-9,\-]*", v):
                        raise BadInput("resources.cpus must look like 0-3")
                    r[k] = v
                elif k == "device":
                    if v not in ("cpu", "gpu"):
                        raise BadInput("resources.device must be cpu or gpu")
                    r[k] = v
                else:
                    raise BadInput(f"unknown setting resources.{k}")
            out[key] = r
        elif key == "max_chars":
            out[key] = int(_num(val, 50, 20000, "max_chars"))
        else:
            raise BadInput(f"unknown setting {key}")
    return out


def save_settings(patch: Any, reg: dict) -> dict:
    merged = _merge(load_settings(), validate_patch(patch, reg))
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged, indent=2) + "\n")
    tmp.replace(path)
    return merged


def voice_for(settings: dict, reg: dict, app: str | None, tts: str | None):
    """The voice for model `tts` in `app`. A voice belongs to its model: the
    app's voice when the app's model (or, without one, the global model) is
    `tts`, then the global voice when the global model is `tts`, then the
    model's default voice."""
    a = settings.get("apps", {}).get(app or "", {}) if app else {}
    at, gt = a.get("tts") or {}, settings.get("tts") or {}
    glob = gt.get("model") or reg["defaults"].get("tts")
    if at.get("voice") and (at.get("model") or glob) == tts:
        return at["voice"]
    if gt.get("voice") and glob == tts:
        return gt["voice"]
    try:
        return model_row(reg, tts).get("default_voice") if tts else None
    except BadInput:
        return None


def pick_voice(
    settings: dict, reg: dict, app: str | None, row: dict, asked: str | None
) -> str:
    """The voice `row` speaks with. A cloning row takes only its own voices:
    the asked one, else the app's (or global) voice for it, else its default,
    else its first, so a wrong name never turns silently into another voice.
    Any other row takes the asked name unless it is a cloned voice's."""
    own = voice_for(settings, reg, app, row["id"]) or ""
    if "profiles" not in (row.get("files") or {}):
        return asked if asked and asked not in profile_names(reg) else own
    names = row_voices(row)
    for v in (asked, own, row.get("default_voice")):
        if v and v in names:
            return v
    return names[0] if names else (asked or own)


def resolve(settings: dict, reg: dict, app: str | None) -> dict:
    """Pick for one app: the app value, then the global value, then the registry."""
    a = settings.get("apps", {}).get(app or "", {}) if app else {}
    at, gt = a.get("tts") or {}, settings.get("tts") or {}
    tts = at.get("model") or gt.get("model") or reg["defaults"].get("tts")
    voice = voice_for(settings, reg, app, tts)
    speed = at.get("speed") or gt.get("speed") or 1.0
    stt = (a.get("stt") or {}).get("model") or (settings.get("stt") or {}).get("model")
    speak = a.get("speak_replies")
    if speak is None:
        speak = (
            settings["anywhere"].get("speak_replies", True)
            if app in (None, "", "anywhere")
            else False
        )
    return {
        "stt": stt or reg["defaults"].get("stt"),
        "tts": tts,
        "voice": voice,
        "speed": speed,
        "speak_replies": bool(speak),
    }


def discover_apps(settings: dict, reg: dict) -> list[dict]:
    """'anywhere' plus every app whose forge_app.json has a `voice` field."""
    rows = [{"name": "anywhere", "label": "Anywhere (hotkey)", "voice": {}}]
    apps_dir = Path(os.environ.get("FORGE_APPS_DIR") or APPS_DIR)
    for mf in sorted(apps_dir.glob("*/forge_app.json")):
        try:
            m = json.loads(mf.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(m, dict) and m.get("voice"):
            name = m.get("name") or mf.parent.name
            rows.append(
                {"name": name, "label": m.get("label", name), "voice": m["voice"]}
            )
    for r in rows:
        r.update(resolve(settings, reg, r["name"]))
    return rows


# ---------------------------------------------------------------- audio


def decode(data: bytes) -> np.ndarray:
    """Any audio ffmpeg reads -> float32 mono 16 kHz."""
    if not data:
        raise BadInput("no audio")
    if len(data) > MAX_BYTES:
        raise BadInput("audio is over 20 MB")
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        "pipe:0",
        "-t",
        str(MAX_SECONDS + 1),
    ]
    cmd += ["-f", "f32le", "-ac", "1", "-ar", str(RATE), "pipe:1"]
    out = subprocess.run(cmd, input=data, capture_output=True, timeout=60)
    if out.returncode != 0:
        raise BadInput(
            f"could not read the audio: {out.stderr.decode()[-200:].strip()}"
        )
    audio = np.frombuffer(out.stdout, dtype="<f4").copy()
    if audio.size == 0:
        raise BadInput("no audio")
    if audio.size > MAX_SECONDS * RATE:
        raise BadInput("audio is over 120 s")
    return audio


# ---------------------------------------------------------------- shared text helpers


def _stand_in():
    """Minimal forge_voice stand-in used until shared/forge_voice.py exists."""
    import types

    m = types.SimpleNamespace()
    fillers = re.compile(r"\b(um+|uh+|erm|hmm)\b[,.]?\s*", re.I)

    def clean_heard(text: str) -> str:
        text = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text or "")
        return " ".join(fillers.sub("", text).split()).strip()

    def split_target(text: str, wake: dict | None = None):
        wake = load_registry().get("wake", {}) if wake is None else wake
        low = text.strip().lower()
        pairs = [(n.lower(), t) for t, ns in wake.items() for n in ns]
        for name, target in sorted(pairs, key=lambda p: -len(p[0])):
            m = re.match(rf"((hey|ok|okay) )?{re.escape(name)}\b[\s,.:!?]*", low)
            if m:
                return target, text.strip()[m.end() :]
        return "", text.strip()

    def is_control(text: str):
        t = re.sub(r"[^a-z ]", "", (text or "").lower()).strip()
        if t in ("stop", "quiet", "hush", "be quiet", "shut up", "stop talking"):
            return "stop"
        if t in ("say that again", "repeat", "repeat that", "again"):
            return "repeat"
        if t in ("cancel", "never mind", "nevermind", "forget it"):
            return "cancel"
        return None

    def speech_text(md: str) -> str:
        t = re.sub(r"```.*?```", " (code skipped) ", md or "", flags=re.S)
        t = re.sub(r"`([^`]*)`", r"\1", t)
        t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
        t = re.sub(r"https?://\S+", "a link", t)
        t = re.sub(r"[*_#>|~]+", " ", t)
        return " ".join(t.split())

    m.clean_heard, m.split_target = clean_heard, split_target
    m.is_control, m.speech_text = is_control, speech_text
    return m


_fv_cache: dict[str, Any] = {}


def fv():
    """shared/forge_voice.py if present (reloaded when it changes), else the stand-in."""
    path = SHARED_DIR / "forge_voice.py"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return _fv_cache.setdefault("stand_in", _stand_in())
    if _fv_cache.get("mtime") != mtime:
        import importlib.util

        spec = importlib.util.spec_from_file_location("forge_voice", path)
        if spec is None or spec.loader is None:
            return _fv_cache.setdefault("stand_in", _stand_in())
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:  # a half-written file must not break the service
            return _fv_cache.setdefault("stand_in", _stand_in())
        _fv_cache["mod"], _fv_cache["mtime"] = mod, mtime
    return _fv_cache["mod"]


# ---------------------------------------------------------------- models


HEAVY_HEADROOM_MB = 1500  # left free beside a heavy model's ram_mb
JAN_BUSY_TICKS = 10  # CPU ticks (1/100 s) in 0.5 s; a generating Jan uses far more
_jan_mod: dict[str, Any] = {}


def mem_available_mb(path: str = "/proc/meminfo") -> int:
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return 1 << 30  # unknown: do not block


def jan_ticks() -> dict[str, int]:
    """CPU ticks of each model Jan has loaded (shared/forge_jan.py), {} if none."""
    try:
        if "mod" not in _jan_mod:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "forge_jan", SHARED_DIR / "forge_jan.py"
            )
            assert spec is not None and spec.loader is not None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _jan_mod["mod"] = mod
        return dict(_jan_mod["mod"].cpu_ticks())
    except Exception:
        return {}


def jan_busy(sample_s: float = 0.5) -> bool:
    """Jan is answering someone now (its model's CPU time grows)."""
    before = jan_ticks()
    if not before:
        return False
    time.sleep(sample_s)
    after = jan_ticks()
    return any(after.get(m, t) - t > JAN_BUSY_TICKS for m, t in before.items())


class Models:
    """Load on first use, one lock per model, unload after idle (a row's own
    idle_unload_s when it is shorter than the global one)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._loaded: dict[str, Any] = {}
        self._used: dict[str, float] = {}
        self._kind: dict[str, str] = {}
        self._idle: dict[str, float] = {}
        self.loader: Callable[[dict, dict, int], Any] = engines.load

    def lock_for(self, model_id: str) -> threading.Lock:
        with self._lock:
            return self._locks.setdefault(model_id, threading.Lock())

    def use(self, row: dict, threads: int, fn: Callable[[Any], Any]):
        mid = row["id"]
        with self.lock_for(mid):
            eng = self._loaded.get(mid)
            if eng is None:
                files = model_files(row)
                need = needed_files(files)
                missing = [str(p) for p in need.values() if not p.exists()]
                if missing:
                    raise VoiceError(f"{row.get('label', mid)} is not downloaded")
                try:
                    eng = self.loader(row, files, threads)
                except Exception as e:
                    raise VoiceError(f"{row.get('label', mid)} failed to load: {e}")
                self._loaded[mid], self._kind[mid] = eng, row.get("kind", "")
                self._idle[mid] = float(row.get("idle_unload_s") or 0)
            self._used[mid] = time.monotonic()
            try:
                return fn(eng)
            finally:
                self._used[mid] = time.monotonic()

    def is_loaded(self, model_id: str) -> bool:
        return model_id in self._loaded

    def status(self) -> list[dict]:
        now = time.monotonic()
        return [
            {
                "id": m,
                "kind": self._kind.get(m, ""),
                "idle_s": round(now - self._used.get(m, now), 1),
            }
            for m in list(self._loaded)
        ]

    def _idle_past(self, mid: str, idle_s: float, now: float) -> bool:
        limit = min(idle_s, self._idle.get(mid) or idle_s)
        return now - self._used.get(mid, now) > limit

    def unload(
        self, model_id: str | None = None, idle_s: float | None = None
    ) -> list[str]:
        """Unload one model or all. With idle_s, only a model still idle that
        long once its lock is free: a long synth that just ended is fresh."""
        gone = []
        for mid in [model_id] if model_id else list(self._loaded):
            if mid not in self._loaded:
                continue
            with self.lock_for(mid):
                if idle_s is not None and not self._idle_past(
                    mid, idle_s, time.monotonic()
                ):
                    continue
                eng = self._loaded.pop(mid, None)
                if eng is not None:
                    try:
                        eng.close()
                    finally:
                        gone.append(mid)
        return gone

    def reap(self, idle_s: float) -> list[str]:
        """Unload models idle longer than idle_s (or their row's shorter
        idle_unload_s); STT stays loaded."""
        now = time.monotonic()
        old = [
            m
            for m in list(self._loaded)
            if self._kind.get(m) != "stt" and self._idle_past(m, idle_s, now)
        ]
        return [g for m in old for g in self.unload(m, idle_s)]


# ---------------------------------------------------------------- playback


class Player:
    """One playback queue on the laptop speakers (pw-play)."""

    def __init__(self, on_idle: Callable[[], None] | None = None):
        self.q: queue.Queue = queue.Queue()
        self.proc: subprocess.Popen | None = None
        self.on_idle = on_idle
        self.busy = False
        self._gen = 0
        self._lock = threading.Lock()  # a hush and a clip starting never interleave
        threading.Thread(target=self._run, daemon=True).start()

    def command(self) -> list[str]:
        return (os.environ.get("FORGE_VOICE_PLAYER") or "pw-play").split()

    def play(self, wav: bytes) -> int:
        with self._lock:
            self.busy = True
            self.q.put((self._gen, wav))
            return self.q.qsize()

    def hush(self) -> None:
        with self._lock:
            self._gen += 1
            while True:
                try:
                    self.q.get_nowait()
                except queue.Empty:
                    break
            p = self.proc
            if p is None:
                # Nothing is playing, so no clip end will clear the flag.
                self.busy = False
            elif p.poll() is None:
                p.kill()

    def _run(self) -> None:
        while True:
            gen, wav = self.q.get()
            with tempfile.NamedTemporaryFile(suffix=".wav", prefix="forge-voice-") as f:
                f.write(wav)
                f.flush()
                with self._lock:
                    if gen == self._gen:
                        try:
                            self.proc = subprocess.Popen(
                                self.command() + [f.name],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                        except OSError:
                            self.proc = None
                p = self.proc
                if p:
                    p.wait()
                    self.proc = None
            with self._lock:
                idle = self.q.empty()
                if idle:
                    self.busy = False
            if idle and self.on_idle:
                self.on_idle()


def play_file(path: str) -> None:
    """Fire-and-forget a short sound (earcon)."""
    try:
        subprocess.Popen(
            (os.environ.get("FORGE_VOICE_PLAYER") or "pw-play").split() + [path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


EARCONS = {
    "start": "kenney/interface-sounds/select_001.ogg",
    "stop": "kenney/interface-sounds/select_007.ogg",
    "error": "kenney/interface-sounds/error_001.ogg",
}


def earcon(name: str) -> None:
    p = SHARED_DIR / "sound_library" / EARCONS.get(name, "")
    if p.is_file():
        play_file(str(p))


# ---------------------------------------------------------------- mic capture


def capture(
    stop: threading.Event,
    use_silence: Callable[[], bool],
    silence_s: float,
    max_s: float,
    on_level: Callable[[float], None] | None = None,
    skip_s: float = 0.15,
) -> np.ndarray:
    """Record 16 kHz mono until `stop`, silence after speech (when use_silence()), or max_s.

    The gate counts by samples, so a FORGE_VOICE_CAPTURE wav runs as fast as it
    reads and still ends the same way the mic would.
    """
    fake = os.environ.get("FORGE_VOICE_CAPTURE")
    chunk = RATE // 10
    proc = None
    if fake:
        src = decode(Path(fake).read_bytes())
        chunks = (src[i : i + chunk] for i in range(0, src.size, chunk))
    else:
        cmd = ["pw-record", "--raw", "--rate", str(RATE), "--channels", "1"]
        proc = subprocess.Popen(
            cmd + ["--format", "s16", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        def mic():
            assert proc is not None and proc.stdout is not None
            while True:
                b = proc.stdout.read(chunk * 2)
                if not b:
                    return
                yield np.frombuffer(b, dtype="<i2").astype(np.float32) / 32768.0

        chunks = mic()
    got: list[np.ndarray] = []
    n = heard = quiet = 0
    floor = None
    try:
        for c in chunks:
            got.append(c)
            n += c.size
            rms = float(np.sqrt(np.mean(c * c))) if c.size else 0.0
            if on_level:
                on_level(rms)
            if n > skip_s * RATE:
                floor = rms if floor is None else min(rms, floor * 1.02 + 1e-5)
                loud = rms > max(0.015, (floor or 0) * 3)
                if loud:
                    heard, quiet = heard + c.size, 0
                else:
                    quiet += c.size
                if use_silence() and heard >= 0.2 * RATE and quiet >= silence_s * RATE:
                    break
            if stop.is_set() or n >= max_s * RATE:
                break
    finally:
        if proc:
            proc.kill()
            proc.wait()
    return np.concatenate(got) if got else np.zeros(0, dtype=np.float32)


# ---------------------------------------------------------------- push-to-talk state machine


class PTT:
    """Pure push-to-talk state machine. `event()` returns actions for the caller.

    States: idle -> listening -> transcribing -> thinking -> speaking -> idle.
    User events: down, up, tap, cancel, hush. Worker events: ended (capture
    stopped by itself), heard (text, may be empty), replied (speak: bool),
    spoken, failed. Actions: start, stop, discard, hush. A press (down or tap)
    while transcribing or thinking cancels the round, so the key is never dead
    while a slow answer is on its way.
    """

    def __init__(self, hold_s: float = 0.35):
        self.state = "idle"
        self.mode: str | None = None  # "pressed" while held, "tap" once let go early
        self.pressed_at = 0.0
        self.hold_s = hold_s

    @property
    def use_silence(self) -> bool:
        return self.mode == "tap"

    def _to(self, state: str, actions: list[str]) -> list[str]:
        self.state = state
        if state != "listening":
            self.mode = None
        return actions

    def event(self, name: str, now: float = 0.0, **kw) -> list[str]:
        s = self.state
        if name == "cancel":
            return self._to("idle", ["discard", "hush"])
        if name == "hush":
            return self._to("idle" if s == "speaking" else s, ["hush"])
        if name == "down":
            if s == "idle":
                self.mode, self.pressed_at = "pressed", now
                return self._to("listening", ["start"])
            if s == "speaking":
                return self._to("idle", ["hush"])
            if s in ("transcribing", "thinking"):
                return self._to("idle", ["discard", "hush"])
            if s == "listening" and self.mode == "tap":
                return self._to("transcribing", ["stop"])
            return []
        if name == "up":
            if s == "listening" and self.mode == "pressed":
                if now - self.pressed_at >= self.hold_s:
                    return self._to("transcribing", ["stop"])
                self.mode = "tap"
            return []
        if name == "tap":
            if s == "idle":
                self.mode = "tap"
                self.state = "listening"
                return ["start"]
            if s == "listening":
                return self._to("transcribing", ["stop"])
            if s == "speaking":
                return self._to("idle", ["hush"])
            if s in ("transcribing", "thinking"):
                return self._to("idle", ["discard", "hush"])
            return []
        if name == "ended":
            return self._to("transcribing", []) if s == "listening" else []
        if name == "heard":
            if s != "transcribing":
                return []
            return self._to("thinking" if kw.get("text") else "idle", [])
        if name == "replied":
            if s != "thinking":
                return []
            return self._to("speaking" if kw.get("speak") else "idle", [])
        if name == "spoken":
            return self._to("idle", []) if s == "speaking" else []
        if name == "failed":
            return self._to("idle", [])
        raise ValueError(f"unknown event {name}")


# ---------------------------------------------------------------- routing


def _url(env: str, default: str) -> str:
    return (os.environ.get(env) or default).rstrip("/")


def _http(method: str, url: str, body: dict | None = None, timeout: float = 30) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "X-Forge": "1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def ask_jan(text: str) -> dict:
    url = _url("FORGE_ACCHAN_URL", "http://127.0.0.1:8451") + "/api/voice/command"
    try:
        r = _http("POST", url, {"text": text, "use_model": True, "source": "voice"}, 95)
    except (urllib.error.URLError, OSError, ValueError):
        return {"handled_by": "error", "reply": "Acchan is not answering."}
    return {"handled_by": r.get("handled_by", "jan"), "reply": r.get("reply") or ""}


def ask_commands(text: str) -> dict | None:
    """Acchan's own commands only (fast path and phrases, no model), or None
    when none matched or Acchan is not running."""
    url = _url("FORGE_ACCHAN_URL", "http://127.0.0.1:8451") + "/api/voice/command"
    try:
        r = _http(
            "POST", url, {"text": text, "use_model": False, "source": "voice"}, 15
        )
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if r.get("handled_by") not in ("fast", "phrase"):
        return None
    return {"handled_by": r["handled_by"], "reply": r.get("reply") or ""}


def ask_claude(text: str, deadline_s: float = 300, wait: int = 25) -> dict:
    """Claude's answer: handled_by "error" (so Jan may answer instead) only
    when the Claude app never got the request. Once it may have taken it, a
    failure is reported, never handed to Jan as well (both would act)."""
    base = _url("FORGE_CLAUDE_URL", "http://127.0.0.1:8445")
    try:
        rid = _http("POST", base + "/api/voice/ask", {"text": text, "source": "voice"})[
            "id"
        ]
    except (TimeoutError, ConnectionResetError, http.client.HTTPException):
        # urlopen wraps send errors in URLError; these come after the request
        # went out, so Claude may be working on it
        return {
            "handled_by": "claude",
            "reply": "Claude may not have got that; check the Voice chat "
            "before you say it again.",
        }
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
        return {"handled_by": "error", "reply": "Claude is not answering."}
    end = time.monotonic() + deadline_s
    try:
        while time.monotonic() < end:
            q = urllib.parse.urlencode({"id": rid, "wait": wait})
            r = _http("GET", f"{base}/api/voice/reply?{q}", timeout=wait + 10)
            if r.get("done"):
                if r.get("error"):
                    return {
                        "handled_by": "claude",
                        "reply": f"Claude hit a problem: {r['error']}",
                    }
                return {"handled_by": "claude", "reply": r.get("text") or ""}
    except (OSError, ValueError, AttributeError, http.client.HTTPException):
        return {
            "handled_by": "claude",
            "reply": "Claude has it, but the answer did not come back; "
            "it will be in the Voice chat.",
        }
    return {
        "handled_by": "claude",
        "reply": "Claude is still working; the answer is in the Voice chat.",
    }


def short_reply(text: str) -> str:
    """At most three sentences of a reply for speaking."""
    try:
        return fv().speech_text(text, max_sentences=3)
    except TypeError:
        return fv().speech_text(text)


def route(text: str, target: str, default: str) -> tuple[str, str, bool]:
    """(target, text to send, named) for heard text; target is jan|claude|text.

    A hotkey target or a leading wake name ("Claude, ...", "Acchan ...") picks
    directly (named). Otherwise the default brain answers, 'auto' meaning
    Claude; answer() lets Acchan's own commands try un-named speech first.
    """
    who, rest = fv().split_target(text, load_registry().get("wake") or {})
    if target in ("jan", "claude", "text"):
        return target, (rest if who in ("jan", "claude") else text), True
    if who in ("jan", "claude"):
        return who, rest, True
    return (default if default in ("jan", "text") else "claude"), text, False


def answer(target: str, text: str, named: bool) -> dict:
    """{target, handled_by, reply} for routed speech (target jan or claude).

    Un-named speech for Claude goes to Acchan's commands first ("volume 40",
    "open firefox" need no model), then Claude; when the Claude app is not
    running, Jan answers instead. A name or hotkey target is never redirected.
    """
    if target == "jan":
        return {"target": "jan", **ask_jan(text)}
    if not named:
        done = ask_commands(text)
        if done is not None:
            return {"target": "jan", **done}
    ans = ask_claude(text)
    if ans["handled_by"] == "error" and not named:
        return {"target": "jan", **ask_jan(text)}
    return {"target": "claude", **ans}


# ---------------------------------------------------------------- the service


class Voice:
    """Ties PTT, capture, models, routing and playback together."""

    def __init__(self):
        self.models = Models()
        self.ptt = PTT()
        self.player = Player(on_idle=self._played)
        self.history: deque = deque(maxlen=50)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.session = 0
        self.target = "auto"
        self.last_reply = ""
        self.level = 0.0
        self.notify_id: str | None = None
        self.done = threading.Event()  # set when a PTT round returns to idle
        self.done.set()
        threading.Thread(target=self._reaper, daemon=True).start()

    # -- basics
    def settings(self) -> dict:
        return load_settings()

    def _reaper(self) -> None:
        while True:
            time.sleep(30)
            try:
                self.models.reap(float(self.settings()["resources"]["idle_unload_s"]))
            except Exception:
                pass

    def threads(self) -> int:
        return int(self.settings()["resources"].get("threads", 4))

    def transcribe(
        self, audio: np.ndarray, app: str | None = None, model: str | None = None
    ) -> dict:
        reg = load_registry()
        mid = model or resolve(self.settings(), reg, app)["stt"]
        if not mid:
            raise VoiceError("no speech-to-text model is set")
        row = model_row(reg, mid)
        if row.get("kind") != "stt":
            raise BadInput(f"{mid} is not a speech-to-text model")
        t = time.monotonic()
        try:
            text = self.models.use(row, self.threads(), lambda e: e.transcribe(audio))
        except VoiceError:
            raise
        except Exception as e:
            raise VoiceError(f"speech-to-text failed: {e}")
        return {
            "text": text.strip(),
            "model": mid,
            "ms": int((time.monotonic() - t) * 1000),
        }

    def synthesize(
        self, text: str, app=None, model=None, voice=None, speed=None
    ) -> dict:
        reg = load_registry()
        st = self.settings()
        pick = resolve(st, reg, app)
        mid = model or pick["tts"]
        if not mid:
            raise VoiceError("no text-to-speech model is set")
        row = model_row(reg, mid)
        if row.get("kind") != "tts":
            raise BadInput(f"{mid} is not a voice model")
        say = fv().speech_text(expressive.prepare(text or ""))
        say = say[: int(st.get("max_chars", 1500))].strip()
        if not re.search(r"\w", expressive.plain(say)):  # "[laugh]" alone too
            raise BadInput("nothing to say")
        v = pick_voice(st, reg, app, row, voice)
        sp = float(speed or pick["speed"] or 1.0)
        t = time.monotonic()
        fell_back = no_voice(row) or self.heavy_block(row)
        if fell_back and self._speaks_anyway(reg, row):
            fell_back = None
        if fell_back:
            row = self._fallback(reg, row, fell_back)
            v = pick_voice(st, reg, app, row, None)  # the asked one was not its
        try:
            audio, rate, v = self._synth(row, say, v, sp)
        except VoiceError as e:
            if not row.get("heavy"):
                raise
            self.models.unload(row["id"])  # a dead server starts afresh next time
            fell_back = str(e)
            row = self._fallback(reg, row, fell_back)
            v = pick_voice(st, reg, app, row, None)  # the asked one was not its
            audio, rate, v = self._synth(row, say, v, sp)
        return {
            "wav": engines.wav_bytes(audio, rate),
            "model": row["id"],
            "voice": v,
            "seconds": round(len(audio) / rate, 2),
            "ms": int((time.monotonic() - t) * 1000),
            "fell_back": fell_back,
        }

    def _synth(self, row: dict, say: str, v: str, sp: float):
        """(audio, rate, the voice that really spoke)."""
        if not row.get("expressive"):  # a plain voice never reads "[angry]" aloud
            say = expressive.plain(say)
            if not re.search(r"\w", say):
                raise BadInput("nothing to say")

        def run(eng):
            audio, rate = eng.synthesize(say, v, sp)
            return audio, rate, getattr(eng, "used_voice", None) or v

        try:
            return self.models.use(row, self.threads(), run)
        except VoiceError:
            raise
        except engines.InputError as e:  # the line, not the model: it stays loaded
            raise BadInput(str(e))
        except Exception as e:
            raise VoiceError(f"text-to-speech failed: {e or type(e).__name__}")

    def heavy_block(self, row: dict) -> str | None:
        """Why a heavy model (row "heavy": true) should not run now, or None:
        too little free memory to load it, or Jan busy on the shared iGPU."""
        if not row.get("heavy"):
            return None
        label = row.get("label", row["id"])
        need = int(row.get("ram_mb") or 0) + HEAVY_HEADROOM_MB
        if not self.models.is_loaded(row["id"]):
            try:  # a server a dead backend left would hold that memory for good
                engines.clear_stale(row, model_files(row))
            except Exception:  # best effort: never stops the speech
                pass
            if mem_available_mb() < need:
                return f"not enough free memory for {label} (it needs {need} MB)"
        if jan_busy():
            return f"Jan is busy, so {label} waits"
        return None

    def _fallback_row(self, reg: dict, row: dict) -> dict | None:
        """The registry's default voice model when it can stand in for `row`:
        another model that speaks its language (no "languages" is English)."""
        fb = reg["defaults"].get("tts")
        if not fb or fb == row["id"]:
            return None
        fb_row = model_row(reg, fb)
        want = set(row.get("languages") or ["en"])
        return fb_row if want & set(fb_row.get("languages") or ["en"]) else None

    def _fallback(self, reg: dict, row: dict, why: str) -> dict:
        """The stand-in for a heavy model that cannot speak now, else
        VoiceError with the reason and why the default voice cannot either."""
        fb_row = self._fallback_row(reg, row)
        if fb_row:
            return fb_row
        fb = reg["defaults"].get("tts")
        if not fb or fb == row["id"]:
            raise VoiceError(why)
        label = model_row(reg, fb).get("label", fb)
        want = ", ".join(sorted(set(row.get("languages") or ["en"])))
        raise VoiceError(f"{why}; {label} does not speak {want}")

    def _speaks_anyway(self, reg: dict, row: dict) -> bool:
        """A loaded heavy row (so only Jan holds it back) waits only while
        another voice can speak its language; otherwise it speaks, slowly,
        because a Japanese line said late beats none."""
        return (
            self.models.is_loaded(row["id"])
            and not no_voice(row)
            and self._fallback_row(reg, row) is None
        )

    def say(self, text: str, **kw) -> int:
        return self.say_report(text, **kw)["queued"]

    def say_report(self, text: str, **kw) -> dict:
        """Speak on the laptop: the queue place, and the model and voice that
        made the line (fell_back says why when it was not the one asked)."""
        r = self.synthesize(text, **kw)
        keep = ("model", "voice", "fell_back")
        return dict({k: r[k] for k in keep}, queued=self.player.play(r["wav"]))

    def hush(self) -> str:
        with self.lock:
            self.ptt.event("hush")
            self.player.hush()
            self._settle()
            return self.ptt.state

    def _played(self) -> None:
        with self.lock:
            self.ptt.event("spoken")
            self._settle()

    def _settle(self) -> None:
        if self.ptt.state == "idle":
            self.done.set()

    # -- push to talk
    def press(self, name: str, target: str = "auto") -> str:
        st = self.settings()
        with self.lock:
            if (
                name in ("down", "tap")
                and self.ptt.state == "idle"
                and self.player.busy
            ):
                # Something is being said outside a round (an app's /api/say):
                # the press stops it, and the mic stays shut so it is not heard.
                self.player.hush()
                return self.ptt.state
            self.ptt.hold_s = float(st["ptt"]["hold_s"])
            actions = self.ptt.event(name, time.monotonic())
            for a in actions:
                if a == "start":
                    self.target = target if target in TARGETS else "auto"
                    self._start(st)
                elif a == "stop":
                    self.stop_event.set()
                elif a == "discard":
                    self.session += 1
                    self.stop_event.set()
                elif a == "hush":
                    self.player.hush()
            self._settle()
            return self.ptt.state

    def _start(self, st: dict) -> None:
        self.session += 1
        self.done.clear()
        self.stop_event = threading.Event()
        if st["anywhere"].get("earcons"):
            earcon("start")
        threading.Thread(
            target=self._round, args=(self.session, self.stop_event, st), daemon=True
        ).start()

    def _round(self, session: int, stop: threading.Event, st: dict) -> None:
        def live() -> bool:
            return session == self.session

        def lvl(x: float) -> None:
            self.level = x

        t0 = time.monotonic()
        try:
            audio = capture(
                stop,
                lambda: self.ptt.use_silence,
                float(st["ptt"]["silence_s"]),
                float(st["ptt"]["max_s"]),
                on_level=lvl,
            )
            with self.lock:
                if not live():
                    return
                self.ptt.event("ended")
            if st["anywhere"].get("earcons"):
                earcon("stop")
            heard = (
                self.transcribe(audio, "anywhere")["text"]
                if audio.size > RATE // 5
                else ""
            )
            text = fv().clean_heard(heard)
            with self.lock:
                if not live():
                    return
                self.ptt.event("heard", text=text)
            if not text:
                return
            self._handle(text, st, t0, live)
        except Exception as e:  # any failure ends the round, spoken briefly
            with self.lock:
                if live():
                    self.ptt.event("failed")
            self.history.appendleft(self._row("", "error", "error", str(e), t0))
            self._notify(f"Voice failed: {e}", st)
        finally:
            with self.lock:
                if live():
                    self._settle()

    def _handle(self, text: str, st: dict, t0: float, live: Callable[[], bool]) -> None:
        f = fv()
        control = f.is_control(text)
        target, rest, named = route(
            text, self.target, st["anywhere"].get("target", "auto")
        )
        control = control or (f.is_control(rest) if target != "text" else None)
        if control:
            reply = self.last_reply if control == "repeat" else ""
            self.history.appendleft(self._row(text, "control", control, reply, t0))
            with self.lock:
                if not live():
                    return
                if control == "stop":
                    self.player.hush()
                self.ptt.event("replied", speak=bool(reply))
            if reply:
                self._speak(reply, live)
            return
        if target == "text":
            self.history.appendleft(self._row(text, "text", "text", "", t0))
            with self.lock:
                if live():
                    self.ptt.event("replied", speak=False)
            return
        self._notify(f"Heard: {text}", st)
        ans = answer(target, rest, named)
        reply = ans.get("reply") or ""
        self.history.appendleft(
            self._row(text, ans["target"], ans.get("handled_by", target), reply, t0)
        )
        if not live():
            return
        speak = (
            bool(reply) and resolve(st, load_registry(), "anywhere")["speak_replies"]
        )
        if reply:
            self.last_reply = reply
            self._notify(reply, st)
        with self.lock:
            if not live():
                return
            self.ptt.event("replied", speak=speak)
        if speak:
            self._speak(short_reply(reply), live)

    def _speak(self, text: str, live: Callable[[], bool]) -> None:
        """Speak a round's reply unless it was hushed or cancelled meanwhile."""
        try:
            wav = self.synthesize(text, app="anywhere")["wav"]
        except (VoiceError, BadInput):
            wav = None
        with self.lock:
            if not live():
                return
            if wav and self.ptt.state == "speaking":
                self.player.play(wav)
            else:
                self.ptt.event("spoken")
                self._settle()

    def _row(self, heard, target, handled_by, reply, t0) -> dict:
        return {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "heard": heard,
            "target": target,
            "handled_by": handled_by,
            "reply": reply,
            "ms": int((time.monotonic() - t0) * 1000),
        }

    def _notify(self, body: str, st: dict) -> None:
        if not st["anywhere"].get("notify"):
            return
        cmd = ["notify-send", "-a", "Forge Voice", "-p"]
        if self.notify_id:
            cmd += ["-r", self.notify_id]
        try:
            out = subprocess.run(
                cmd + ["Forge Voice", body[:300]],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.notify_id = out.stdout.strip() or self.notify_id
        except (OSError, subprocess.SubprocessError):
            pass

    def status(self) -> dict:
        mic = os.environ.get("FORGE_VOICE_CAPTURE")
        tool = "file" if mic else "pw-record"
        ok = bool(mic) or any(
            (Path(d) / "pw-record").exists()
            for d in os.environ.get("PATH", "").split(":")
        )
        return {
            "state": self.ptt.state,
            "loaded": self.models.status(),
            "mic": {"ok": ok, "tool": tool},
            "level": round(self.level, 4) if self.ptt.state == "listening" else 0,
            "version": 1,
        }


if __name__ == "__main__":  # pragma: no cover
    sys.exit("run web_app:app with uvicorn")
