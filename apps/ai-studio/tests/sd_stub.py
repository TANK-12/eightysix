"""A fake sd-server for tests: answers the A1111-style routes AI Studio uses
(/sdapi/v1/samplers, /sdapi/v1/txt2img, /sdapi/v1/img2img) on CPU in
milliseconds, so the whole image and video pipeline can run for real
without a model or the GPU.

- txt2img returns a solid colour picked from the seed.
- img2img returns the init image resized to the asked size, nudged a little
  toward the seed's colour (like a light "heal"), so motion warps carry
  through to the output frames.
Every request body is kept in `stub.requests` for the test to inspect.
"""

import base64
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

PORTS = range(9011, 9031)  # crew scratch ports


def bind(handler, port=None):
    """A server on `port`, or on the first free crew scratch port. (The
    server sets SO_REUSEADDR, so ports a finished stub left in TIME_WAIT are
    reused rather than skipped.)"""
    for p in [port] if port else PORTS:
        try:
            return ThreadingHTTPServer(("127.0.0.1", p), handler)
        except OSError:
            continue
    raise RuntimeError("no free scratch port in 9011-9030")


def seed_colour(seed):
    seed = int(seed) if seed is not None else 0
    return (40 + seed * 53 % 200, 40 + seed * 97 % 200, 40 + seed * 31 % 200)


def png_b64(img):
    out = io.BytesIO()
    img.save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode()


class SdStub:
    def __init__(self, port=None, delay=0.0):
        self.port = 0
        self.url = ""
        self.delay = delay
        self.fail_with = None  # an HTTP status to answer every POST with
        self.requests = []  # (path, body)
        self._lock = threading.Lock()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):  # noqa: A002 (base class name)
                pass

            def _send(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/sdapi/v1/samplers":
                    self._send(200, [{"name": "euler"}, {"name": "lcm"}])
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with stub._lock:
                    stub.requests.append((self.path, body))
                if stub.delay:
                    threading.Event().wait(stub.delay)
                if stub.fail_with:
                    self._send(stub.fail_with, {"error": "stub told to fail"})
                    return
                w, h = int(body["width"]), int(body["height"])
                colour = seed_colour(body.get("seed"))
                if self.path == "/sdapi/v1/txt2img":
                    img = Image.new("RGB", (w, h), colour)
                elif self.path == "/sdapi/v1/img2img":
                    raw = base64.b64decode(body["init_images"][0])
                    src = Image.open(io.BytesIO(raw)).convert("RGB").resize((w, h))
                    img = Image.blend(src, Image.new("RGB", (w, h), colour), 0.1)
                else:
                    self._send(404, {"error": "not found"})
                    return
                self._send(200, {"images": [png_b64(img)], "info": "{}"})

        self.server = bind(Handler, port)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.server.server_close()

    def bodies(self, path_end):
        with self._lock:
            return [b for p, b in self.requests if p.endswith(path_end)]
