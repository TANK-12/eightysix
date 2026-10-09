#!/usr/bin/env python3
"""A stand-in audiocpp_server for tests: --config <json>, the same routes, a tone.

FAKE_AC_MODE: "die" exits at start, "empty" sends a wav with no samples, "json"
answers with base64 wav in JSON. FAKE_AC_LOG: a file the config, the working
folder and every request are appended to as JSON lines.
"""

import base64
import io
import json
import math
import os
import struct
import sys
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

args = sys.argv[1:]
CFG = json.load(open(args[args.index("--config") + 1]))
MODE = os.environ.get("FAKE_AC_MODE", "")
LOG = os.environ.get("FAKE_AC_LOG", "")
IDS = {m["id"]: m for m in CFG["models"]}


def log(entry):
    if LOG:
        with open(LOG, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


if MODE == "die":
    print("error: failed to load model", flush=True)
    sys.exit(1)
log({"config": CFG, "cwd": os.getcwd(), "pid": os.getpid()})


def tone(n):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(
            b"".join(struct.pack("<h", int(8000 * math.sin(i / 10))) for i in range(n))
        )
    return buf.getvalue()


class H(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.send(200, b'{"status":"ok"}')
        self.send(404, b"{}")

    def audio(self, n):
        wav = tone(0 if MODE == "empty" else n)
        if MODE == "json":
            body = {"audio": "data:audio/wav;base64," + base64.b64encode(wav).decode()}
            return self.send(200, json.dumps(body).encode())
        self.send(200, wav, "audio/wav")

    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        log({"path": self.path, "body": d})
        if d.get("model") not in IDS:
            return self.send(400, b'{"error":"unknown model"}')
        if self.path == "/v1/audio/speech":
            ref = d.get("voice_ref") or {}
            if ref and not os.path.exists(ref.get("path", "")):
                return self.send(400, b'{"error":"voice_ref not found"}')
            return self.audio(2400 * max(1, len(d["input"].split())))
        if self.path == "/v1/tasks/run":
            if not os.path.exists(d["request"].get("audio", "")):
                return self.send(400, b'{"error":"audio not found"}')
            return self.audio(4800)
        self.send(404, b"{}")


ThreadingHTTPServer(("127.0.0.1", CFG["port"]), H).serve_forever()
