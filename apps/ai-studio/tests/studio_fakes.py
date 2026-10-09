"""Shared fakes for the catalog / parts / API tests: a local file server with
Range support, a scratch models folder, and fake sd-servers. No real model is
ever downloaded and no GPU work runs."""

import http.server
import sys
import threading
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import model_manager  # noqa: E402  # pyright: ignore[reportMissingImports]


class FakeServers:
    """Stands in for model_manager.servers: records calls, starts nothing."""

    def __init__(self):
        self.calls = []
        self.active_id = None
        self.has_cpu = False

    def stop(self):
        self.calls.append("stop")
        self.active_id = None

    def alive(self):
        return self.active_id is not None

    def switch_to(self, model_id):
        self.calls.append(("switch", model_id))
        model_manager.set_active_id(model_id)
        self.active_id = model_id


class FileServer:
    """Serves byte blobs by path on 127.0.0.1 (a free port), honouring Range
    unless ignore_range. ``gate`` (an Event) pauses every response after its
    first chunk until set, so a test can cancel mid-download."""

    def __init__(self):
        self.files = {}
        self.requests = []  # (path, Range header or None)
        self.ignore_range = False
        self.gate = None
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                outer.requests.append((self.path, self.headers.get("Range")))
                data = outer.files.get(self.path)
                if data is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                start = 0
                rng = self.headers.get("Range")
                if rng and not outer.ignore_range:
                    start = int(rng.split("=", 1)[1].split("-", 1)[0])
                    self.send_response(206)
                    self.send_header(
                        "Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}"
                    )
                else:
                    self.send_response(200)
                body = data[start:]
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body[:1024])
                    self.wfile.flush()
                    if outer.gate is not None:
                        outer.gate.wait(10)
                    self.wfile.write(body[1024:])
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def close(self):
        if self.gate is not None:
            self.gate.set()
        self.httpd.shutdown()
        self.httpd.server_close()


def make_part(server, role, filename, size, fill=b"x"):
    """Register a blob of `size` bytes on the server and return its part."""
    path = f"/{filename}"
    server.files[path] = (fill * size)[:size]
    return {
        "role": role,
        "url": server.url(path),
        "filename": filename,
        "size_bytes": size,
    }


def entry(mid, parts, kind="image", **extra):
    return {
        "id": mid,
        "kind": kind,
        "label": mid.title(),
        "blurb": f"{mid} blurb",
        "tier": "compact",
        "engine": {"image": "sd", "video": "sd-video"}.get(kind, "world:fake"),
        "engine_build": "current",
        "parts": parts,
        "settings": {"steps": 4, "cfg_scale": 1.0, "sampler": "euler"},
        **extra,
    }


@pytest.fixture
def server():
    s = FileServer()
    yield s
    s.close()


@pytest.fixture
def studio(tmp_path, monkeypatch):
    """A scratch models folder wired into model_manager; returns a namespace
    with the folders, the fake servers and a `use(catalog)` helper."""
    models = tmp_path / "models"

    ns = types.SimpleNamespace()
    ns.root = tmp_path
    ns.parts = models / "parts"
    ns.legacy = models / "sd" / "catalog"
    ns.lora = models / "sd" / "lora"
    ns.fake = FakeServers()
    ns.free = [10**15]
    monkeypatch.setattr(model_manager, "PARTS_DIR", ns.parts)
    monkeypatch.setattr(model_manager, "DOWNLOAD_DIR", ns.legacy)
    monkeypatch.setattr(model_manager, "LORA_DIR", ns.lora)
    monkeypatch.setattr(model_manager, "STATE_PATH", models / "active_model.json")
    monkeypatch.setattr(model_manager, "servers", ns.fake)
    monkeypatch.setattr(model_manager, "free_bytes", lambda: ns.free[0])
    monkeypatch.setattr(model_manager, "_jobs", {})
    monkeypatch.setattr(model_manager, "_file_locks", {})
    monkeypatch.setattr(model_manager, "EXTRA_MODELS", [])

    def use(catalog, default=None):
        monkeypatch.setattr(model_manager, "CATALOG", {e["id"]: e for e in catalog})
        monkeypatch.setattr(model_manager, "DEFAULT_MODEL_ID", default)

    ns.use = use
    return ns


def put(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def wait_download(model_id, timeout=10):
    with model_manager._jobs_lock:
        job = model_manager._jobs.get(model_id)
    if job and job.thread:
        job.thread.join(timeout)
    return model_manager.download_state(model_id)
