"""The Conversations view's door to the Claude app (mc/claude_proxy.py): a
fake Claude app on a free port records what Mission forwards to it."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

H = {"X-Mission": "1"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


class FakeClaude(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, format, *args):  # quiet
        pass

    def _picture(self):
        # the Claude app's unguarded image route: .png is a picture, .gif
        # pretends to be one but answers a web page
        if "/conversations/gone/" in self.path:
            code, media, raw = 404, "application/json", b'{"detail": "No such image"}'
        elif self.path.endswith(".gif"):
            code, media, raw = 200, "text/html", b"<html>not a picture</html>"
        else:
            code, media, raw = 200, "image/png", PNG
        self.send_response(code)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _answer(self, method):
        if method == "GET" and "/files/" in self.path:
            FakeClaude.seen.append({"method": method, "path": self.path})
            return self._picture()
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else None
        FakeClaude.seen.append(
            {
                "method": method,
                "path": self.path,
                "forge": self.headers.get("X-Forge"),
                "body": body,
            }
        )
        if self.headers.get("X-Forge") != "1":
            code, out = 403, {"detail": "Send X-Forge: 1"}
        elif "/conversations/gone/" in self.path:
            code, out = 404, {"detail": "No such conversation"}
        else:
            code, out = 200, {"ok": True, "echo": self.path, "meta": {"model": "opus"}}
        raw = json.dumps(out).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._answer("GET")

    def do_POST(self):
        self._answer("POST")


@pytest.fixture
def fake(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeClaude)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("MISSION_PORT_CLAUDE", str(srv.server_address[1]))
    FakeClaude.seen = []
    yield FakeClaude.seen
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def client():
    import web_app

    return TestClient(web_app.app)


def test_options_and_events_are_forwarded_with_the_forge_header(fake, client):
    assert client.get("/api/claude/options").json()["echo"] == "/api/options"
    got = client.get(
        "/api/claude/conversations/d7d9db32b3d9/events",
        params={"after": 12, "wait": 99, "boot": "b00t"},
    )
    assert got.status_code == 200
    path = fake[-1]["path"]
    assert path.startswith("/api/conversations/d7d9db32b3d9/events?")
    assert "after=12" in path and "boot=b00t" in path
    assert "wait=25.0" in path  # held at the Claude app's own ceiling
    assert all(r["forge"] == "1" for r in fake)


@pytest.mark.parametrize(
    "action", ["send", "settings", "stop", "seen", "files", "paste-image"]
)
def test_every_allowed_action_reaches_the_claude_app(fake, client, action):
    body = {"text": "hi", "model": "opus"}
    got = client.post(
        f"/api/claude/conversations/abc123/{action}", json=body, headers=H
    )
    assert got.status_code == 200, got.text
    assert fake[-1]["method"] == "POST"
    assert fake[-1]["path"] == f"/api/conversations/abc123/{action}"
    assert fake[-1]["body"] == body


def test_posts_need_the_mission_header(fake, client):
    got = client.post("/api/claude/conversations/abc/send", json={"text": "x"})
    assert got.status_code == 403
    assert fake == []


@pytest.mark.parametrize(
    "url",
    [
        "/api/claude/conversations/abc/close",
        "/api/claude/conversations/abc/attach-page",
        "/api/claude/conversations/abc/..%2F..%2Fprojects",
        "/api/claude/conversations/a.b/send",
        "/api/claude/conversations/" + "a" * 65 + "/send",
    ],
)
def test_nothing_outside_the_allowlist_gets_through(fake, client, url):
    got = client.post(url, json={}, headers=H)
    assert got.status_code in (400, 404, 405)
    assert fake == []


def test_bad_ids_and_bodies_are_refused(fake, client):
    assert client.get("/api/claude/conversations/a.b/events").status_code == 400
    bad_boot = client.get("/api/claude/conversations/abc/events?boot=x/y")
    assert bad_boot.status_code == 400
    raw = client.post(
        "/api/claude/conversations/abc/send",
        content=b"[1,2]",
        headers={**H, "Content-Type": "application/json"},
    )
    assert raw.status_code == 400
    assert fake == []


def test_the_claude_apps_errors_come_back_as_they_are(fake, client):
    got = client.post("/api/claude/conversations/gone/send", json={}, headers=H)
    assert got.status_code == 404
    assert got.json()["detail"] == "No such conversation"


def test_claude_app_down_is_a_plain_503(monkeypatch, client):
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv("MISSION_PORT_CLAUDE", str(port))
    got = client.get("/api/claude/options")
    assert got.status_code == 503
    assert "not running" in got.json()["detail"]


@pytest.mark.parametrize(
    "name", ["run_controls.js", "run_controls.css", "enjoy_logic.js", "enjoy.css"]
)
def test_the_claude_apps_own_ui_files_are_served_unchanged(client, name):
    from mc import claude_proxy

    got = client.get(f"/claude-ui/{name}")
    assert got.status_code == 200
    with open(f"{claude_proxy.CLAUDE_STATIC}/{name}", "rb") as fh:
        assert got.content == fh.read()


@pytest.mark.parametrize(
    "name", ["enjoy.js", "../web_app.py", "index.html", "runner.py"]
)
def test_only_the_listed_ui_files_are_served(client, name):
    assert client.get(f"/claude-ui/{name}").status_code == 404


def test_open_can_stay_in_mission(monkeypatch, client):
    from mc import actions

    calls = []
    monkeypatch.setattr(actions, "manifest_port", lambda **k: 1)
    monkeypatch.setattr(
        actions,
        "http_json",
        lambda port, path, *a, **k: calls.append(path) or {"id": "c1"},
    )
    asked = []
    import forge_open  # pyright: ignore[reportMissingImports]

    monkeypatch.setattr(
        forge_open, "request_open", lambda app: asked.append(app) or "ok"
    )
    sid = "11111111-aaaa-bbbb-cccc-000000000005"
    got = client.post(
        f"/api/sessions/{sid}/open", json={"state": "ended", "show": False}, headers=H
    )
    assert got.json() == {"ok": True, "id": "c1", "shown": False}
    assert asked == []
    got = client.post(f"/api/sessions/{sid}/open", json={"state": "ended"}, headers=H)
    assert got.json()["shown"] is True and asked == ["claude"]


def test_an_attached_picture_comes_through_as_a_picture(fake, client):
    got = client.get("/api/claude/conversations/c1/files/shot%201.png")
    assert got.status_code == 200, got.text
    assert got.content == PNG
    assert got.headers["content-type"] == "image/png"
    assert fake[-1]["path"] == "/api/conversations/c1/files/shot%201.png"


@pytest.mark.parametrize(
    "name, code",
    [
        ("notes.txt", 400),
        pytest.param("x" * 201 + ".png", 400, id="long"),
        ("..%5Cx.png", 400),
    ],
)
def test_only_picture_names_are_asked_for(fake, client, name, code):
    got = client.get(f"/api/claude/conversations/c1/files/{name}")
    assert got.status_code == code
    assert not fake  # nothing reached the Claude app


def test_a_reply_that_is_not_a_picture_is_refused(fake, client):
    got = client.get("/api/claude/conversations/c1/files/fake.gif")
    assert got.status_code == 502
    assert b"<html>" not in got.content


def test_a_missing_picture_is_a_404(fake, client):
    assert client.get("/api/claude/conversations/gone/files/a.png").status_code == 404


def test_a_link_opens_through_the_claude_app(fake, client):
    url = "https://example.com/a?b=1"
    assert client.post("/api/claude/open-link", json={"url": url}).status_code == 403
    got = client.post("/api/claude/open-link", json={"url": url}, headers=H)
    assert got.status_code == 200, got.text
    assert fake[-1]["path"] == "/api/open-link"
    assert fake[-1]["body"] == {"url": url} and fake[-1]["forge"] == "1"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "",
        pytest.param("https://" + "a" * 5000, id="long"),
    ],
)
def test_only_web_addresses_are_opened(fake, client, url):
    got = client.post("/api/claude/open-link", json={"url": url}, headers=H)
    assert got.status_code == 400
    assert not fake


def test_stop_a_relay_task_goes_to_the_relay_page(fake, client, monkeypatch):
    from mc import actions

    port = actions.manifest_port(role="claude")  # the fake answers any route
    monkeypatch.setenv("MISSION_PORT_RELAY", str(port))
    assert client.post("/api/relay/tasks/109/stop").status_code == 403
    got = client.post("/api/relay/tasks/109/stop", headers=H)
    assert got.status_code == 200, got.text
    assert fake[-1]["method"] == "POST"
    assert fake[-1]["path"] == "/api/tasks/109/stop"
    assert client.post("/api/relay/tasks/0/stop", headers=H).status_code == 400
    assert client.post("/api/relay/tasks/x/stop", headers=H).status_code == 422


def test_stop_a_relay_task_when_the_relay_page_is_down(client, monkeypatch):
    monkeypatch.setenv("MISSION_PORT_RELAY", "9")  # nothing listens on 9
    got = client.post("/api/relay/tasks/109/stop", headers=H)
    assert got.status_code == 503 and "Relay" in got.json()["detail"]
