"""Real shells over the WebSocket: auth, I/O, resize, replay, exit, close."""

from __future__ import annotations

import json
import signal
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import web_app  # noqa: E402

H = {"X-Forge": "1"}
ORIGIN = {"origin": "http://testserver"}


@pytest.fixture(autouse=True)
def deadline():
    """A shell that never answers must fail the test, not hang the run."""

    def boom(*_):
        raise TimeoutError("terminal test took too long")

    old = signal.signal(signal.SIGALRM, boom)
    signal.alarm(20)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)


@pytest.fixture
def client():
    with TestClient(web_app.app) as c:
        yield c


def new(c, **body) -> str:
    r = c.post("/api/terms", json=body, headers=H)
    assert r.status_code == 200
    return r.json()["id"]


def ws_url(tid: str, token: str | None = None) -> str:
    return f"/ws/{tid}?t={token or web_app.TOKEN}"


def read_until(ws, needle: str, limit: int = 400) -> str:
    seen = ""
    for _ in range(limit):
        msg = ws.receive()
        if msg.get("bytes"):
            seen += msg["bytes"].decode(errors="replace")
        elif msg.get("text"):
            seen += msg["text"]
        if needle in seen:
            return seen
    raise AssertionError(f"never saw {needle!r} in {seen[-500:]!r}")


def send(ws, text: str) -> None:
    ws.send_text(json.dumps({"t": "in", "d": text}))


def test_api_needs_header(client):
    assert client.get("/api/terms").status_code == 403
    assert client.post("/api/terms", json={}).status_code == 403
    assert client.get("/api/session", headers=H).json()["token"] == web_app.TOKEN


@pytest.mark.parametrize(
    "headers,token",
    [({}, None), ({"origin": "http://evil.example"}, None), (ORIGIN, "wrong")],
)
def test_ws_refuses_without_origin_and_token(client, headers, token):
    tid = new(client)
    assert close_code(client, ws_url(tid, token), headers) == 4403
    client.delete(f"/api/terms/{tid}", headers=H)


def close_code(client, url: str, headers: dict = ORIGIN) -> int:
    """The code a refused socket closes with, refused before or after accept."""
    try:
        with client.websocket_connect(url, headers=headers) as ws:
            msg = ws.receive()
    except WebSocketDisconnect as e:
        return e.code
    assert msg["type"] == "websocket.close", msg
    return msg["code"]


def test_ws_tells_its_own_page_why_it_closed(client):
    """Codes the page acts on: 4403 fetch a new token, 4404 the shell is gone.
    Non-ASCII in the token is refused, not a crash."""
    tid = new(client)
    assert close_code(client, ws_url("nope0000")) == 4404
    assert close_code(client, ws_url(tid, "stale")) == 4403
    assert close_code(client, ws_url(tid, "t%C3%A9st")) == 4403
    assert close_code(client, ws_url("nope0000", "stale")) == 4403
    client.delete(f"/api/terms/{tid}", headers=H)


def test_malformed_messages_are_ignored(client):
    tid = new(client)
    with client.websocket_connect(ws_url(tid), headers=ORIGIN) as ws:
        for bad in [
            "not json",
            "[1]",
            "5",
            "null",
            '{"t": "resize", "cols": "abc", "rows": 5}',
            '{"t": "resize", "cols": 1e400}',
            '{"t": "resize", "cols": null}',
            '{"t": "in", "d": {"x": 1}}',
            '{"t": "in", "d": "\\ud800"}',
        ]:
            ws.send_text(bad)
        ws.send_bytes(b"\x00binary")
        # Ctrl-U drops the "?" the lone surrogate typed
        send(ws, "\x15echo still-$((2*21))\n")
        read_until(ws, "still-42")
    client.delete(f"/api/terms/{tid}", headers=H)


def test_second_page_takes_the_shell_with_a_code(client):
    """The first page is told 4409, so it waits for a key instead of taking
    the shell straight back (two windows used to swap it every 1.5 s)."""
    tid = new(client)
    with client.websocket_connect(ws_url(tid), headers=ORIGIN) as first:
        send(first, "echo one\n")
        read_until(first, "one")
        with client.websocket_connect(ws_url(tid), headers=ORIGIN) as second:
            read_until(second, "one")
            with pytest.raises(WebSocketDisconnect) as e:
                for _ in range(400):
                    first.receive_bytes()
            assert e.value.code == 4409
    client.delete(f"/api/terms/{tid}", headers=H)


def test_shell_runs_commands_and_resizes(client, tmp_path):
    tid = new(client, cwd=str(tmp_path), cols=80, rows=24)
    with client.websocket_connect(ws_url(tid), headers=ORIGIN) as ws:
        send(ws, "echo hi-$((6*7)); pwd\n")
        out = read_until(ws, "hi-42")
        out += read_until(ws, str(tmp_path))
        ws.send_text(json.dumps({"t": "resize", "cols": 123, "rows": 45}))
        send(ws, "stty size\n")
        read_until(ws, "45 123")
        send(ws, 'echo "venv=[$VIRTUAL_ENV]" term=$TERM\n')
        read_until(ws, "venv=[] term=xterm-256color")
    info = {t["id"]: t for t in client.get("/api/terms", headers=H).json()}[tid]
    assert info["alive"] and info["cwd"] == str(tmp_path)
    client.delete(f"/api/terms/{tid}", headers=H)


def test_scrollback_replays_on_reattach(client):
    tid = new(client)
    with client.websocket_connect(ws_url(tid), headers=ORIGIN) as ws:
        send(ws, "echo marker-$((1+1))\n")
        read_until(ws, "marker-2")
    with client.websocket_connect(ws_url(tid), headers=ORIGIN) as ws:
        read_until(ws, "marker-2")  # arrives without typing anything
    client.delete(f"/api/terms/{tid}", headers=H)


def test_exit_reports_and_is_dropped(client):
    tid = new(client)
    with client.websocket_connect(ws_url(tid), headers=ORIGIN) as ws:
        send(ws, "exit 3\n")
        read_until(ws, '"t": "exit"')
    client.get("/api/terms", headers=H)  # lists it once as exited, then drops it
    ids = [t["id"] for t in client.get("/api/terms", headers=H).json()]
    assert tid not in ids


def test_close_hangs_up_the_shell(client):
    tid = new(client)
    term = web_app.terms.get(tid)
    assert term is not None
    with client.websocket_connect(ws_url(tid), headers=ORIGIN) as ws:
        send(ws, "echo ready\n")
        read_until(ws, "ready")
        assert client.delete(f"/api/terms/{tid}", headers=H).status_code == 200
        read_until(ws, '"t": "exit"')
    assert not term.alive
    assert client.delete(f"/api/terms/{tid}", headers=H).status_code == 404


def test_foreground_program_is_named(client):
    tid = new(client)
    with client.websocket_connect(ws_url(tid), headers=ORIGIN) as ws:
        send(ws, "sleep 5\n")
        info: dict = {}
        for _ in range(50):
            info = {t["id"]: t for t in client.get("/api/terms", headers=H).json()}[tid]
            if info["program"] == "sleep":
                break
            time.sleep(0.1)
        assert info["program"] == "sleep"
    client.delete(f"/api/terms/{tid}", headers=H)


def test_static_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "Terminal" in r.text
    assert client.get("/vendor/xterm.js").status_code == 200


def test_logs_never_show_the_socket_token():
    import logging

    rec = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        __file__,
        1,
        '%s - "WebSocket %s" [accepted]',
        ("127.0.0.1:1", "/ws/ab12?t=SECRETsecret-_42"),
        None,
    )
    for name in ("uvicorn.error", "uvicorn.access"):
        assert any(
            isinstance(f, web_app.HideToken) for f in logging.getLogger(name).filters
        )
    assert web_app.HideToken().filter(rec) is True
    assert "SECRET" not in rec.getMessage() and "/ws/ab12?t=…" in rec.getMessage()
