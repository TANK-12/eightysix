#!/usr/bin/env python3
"""A stand-in breeze-server for tests: the same routes and flags, a tone for speech.

FAKE_BREEZE_MODE: "die" exits at start, "busy:N" answers 409 to the first N
speech requests. FAKE_BREEZE_LOG: a file each speech request and the argv are
appended to as JSON lines.
"""

import json
import math
import os
import re
import struct
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

args = sys.argv[1:]


def flag(name, default):
    return args[args.index(name) + 1] if name in args else default


PORT = int(flag("--port", "8080"))
VOICES = Path(flag("--voices-dir", "voices"))
MODE = os.environ.get("FAKE_BREEZE_MODE", "")
LOG = os.environ.get("FAKE_BREEZE_LOG", "")
busy = [int(MODE.split(":")[1]) if MODE.startswith("busy:") else 0]


def log(entry):
    if LOG:
        with open(LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")


if MODE == "die":
    print("error: failed to load model", flush=True)
    sys.exit(1)
log({"argv": sys.argv, "omp": os.environ.get("OMP_NUM_THREADS"), "pid": os.getpid()})


class H(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send(self, code, body, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.send(200, b'{"status":"ok","sample_rate":24000,"ws_port":0}')
        if self.path == "/v1/voices":
            vs = [{"id": p.stem, "saved": True} for p in VOICES.glob("*.breeze")]
            return self.send(
                200, json.dumps(vs + [{"id": "cached1", "saved": False}]).encode()
            )
        self.send(404, b"{}")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/v1/voices":
            name = re.search(rb'name="name"\r\n\r\n(.*?)\r\n', body)
            text = re.search(rb'name="ref_text"\r\n\r\n(.*?)\r\n', body)
            if not (name and text and b'name="ref_audio"' in body):
                return self.send(400, b'{"error":"ref_audio and ref_text needed"}')
            (VOICES / (name.group(1).decode() + ".breeze")).write_bytes(b"BRZV")
            log({"saved": name.group(1).decode(), "ref_text": text.group(1).decode()})
            return self.send(200, json.dumps({"id": name.group(1).decode()}).encode())
        if self.path == "/v1/audio/speech":
            f = {k: v[0] for k, v in parse_qs(body.decode()).items()}
            log({"speech": f})
            if busy[0] > 0:
                busy[0] -= 1
                return self.send(409, b'{"error":"busy"}')
            if not (VOICES / (f.get("voice_id", "") + ".breeze")).exists():
                return self.send(404, b'{"error":"unknown voice_id"}')
            n = 2400 * len(f["text"].split())
            pcm = b"".join(
                struct.pack("<h", int(8000 * math.sin(i / 10))) for i in range(n)
            )
            return self.send(200, pcm, "audio/pcm", {"X-Sample-Rate": "24000"})
        self.send(404, b"{}")


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
