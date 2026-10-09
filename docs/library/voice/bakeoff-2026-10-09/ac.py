"""Scratch helpers for the Relay 120 bake-off: one audiocpp_server, JSON calls."""
import json, os, socket, subprocess, time, urllib.request, urllib.error, wave, base64
M = "/home/ejb/Forge/models/voice"
SRC = M + "/bin/audio.cpp-src"
BIN = SRC + "/build/linux-vulkan-release/bin/audiocpp_server"
AUK = {"auk.variant": "flash", "auk.model_gguf": "auk-flash-q8_0.gguf", "auk.qwen_gguf": "qwen2.5-omni-3b-q8_0.gguf"}
MODELS = [
    {"id": "auk", "family": "auk", "path": M + "/tts/auk", "task": "tts", "mode": "offline", "session_options": AUK},
    {"id": "auk-edit", "family": "auk", "path": M + "/tts/auk", "task": "gen", "mode": "offline", "session_options": AUK},
    {"id": "irodori", "family": "irodori_tts", "path": M + "/tts/irodori-v4.1-anime/irodori-tts-v4.1-anime-q8_0.gguf", "task": "tts", "mode": "offline"},
    {"id": "irodori-clon", "family": "irodori_tts", "path": M + "/tts/irodori-v4.1-anime/irodori-tts-v4.1-anime-q8_0.gguf", "task": "clon", "mode": "offline"},
    {"id": "irodori-vdes", "family": "irodori_tts", "path": M + "/tts/irodori-v4.1-anime/irodori-tts-v4.1-anime-q8_0.gguf", "task": "vdes", "mode": "offline"},
    {"id": "omnivoice", "family": "omnivoice", "path": M + "/tts/omnivoice/omnivoice-q8_0.gguf", "task": "tts", "mode": "offline"},
    {"id": "sensevoice", "family": "sense_asr", "path": M + "/stt/sensevoice-small/sensevoice-small-q8-audiocpp-v1.gguf", "task": "asr", "mode": "offline"},
]

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

class Server:
    def __init__(self, backend="vulkan", threads=6, max_loaded=2, log="/tmp/v120/bake/server.log"):
        self.port = free_port()
        cfg = {"host": "127.0.0.1", "port": self.port, "backend": backend, "device": 0, "threads": threads,
               "lazy_load": True, "max_loaded_models": max_loaded, "models": MODELS}
        self.cfg = f"/tmp/v120/bake/server-{backend}.json"
        json.dump(cfg, open(self.cfg, "w"), indent=1)
        self.log = open(log, "ab")
        self.p = subprocess.Popen([BIN, "--config", self.cfg, "--no-ui"], stdout=self.log, stderr=subprocess.STDOUT,
                                  cwd=SRC)
        self.url = f"http://127.0.0.1:{self.port}"
        for _ in range(240):
            if self.p.poll() is not None: raise RuntimeError("server died")
            try:
                urllib.request.urlopen(self.url + "/health", timeout=2).read(); return
            except OSError: time.sleep(0.5)
        raise RuntimeError("no health")
    def post(self, path, body, timeout=900):
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        t = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data, ctype = r.read(), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            return None, time.monotonic() - t, f"HTTP {e.code}: {e.read()[:400]!r}"
        return (data, ctype), time.monotonic() - t, None
    def unload_all(self):
        try: self.post("/v1/tasks/unload_all_models", {})
        except Exception: pass
    def close(self):
        self.p.terminate()
        try: self.p.wait(10)
        except subprocess.TimeoutExpired: self.p.kill(); self.p.wait()

def wav_seconds(path):
    with wave.open(path) as w: return w.getnframes() / w.getframerate()

def save_audio(resp, path):
    data, ctype = resp
    if "json" in ctype:
        d = json.loads(data)
        b64 = d.get("audio") or d.get("data") or d.get("audio_base64") or ""
        data = base64.b64decode(b64.split(",")[-1])
    open(path, "wb").write(data)
    return wav_seconds(path)
