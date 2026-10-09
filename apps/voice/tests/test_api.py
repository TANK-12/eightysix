import io
import json
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import service
from conftest import FakeEngine, tone_wav


# ---- guard
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/registry"),
        ("get", "/api/settings"),
        ("get", "/api/apps"),
        ("get", "/api/history"),
        ("post", "/api/hush"),
        ("post", "/api/unload"),
        ("post", "/api/ptt/tap"),
        ("post", "/api/stt"),
        ("post", "/api/tts"),
        ("post", "/api/say"),
        ("post", "/api/settings"),
    ],
)
def test_guard_needs_header_and_host(client, method, path):
    no_hdr = getattr(client, method)(path, headers={"X-Forge": ""})
    assert no_hdr.status_code == 403
    bad_host = getattr(client, method)(path, headers={"Host": "evil.example:8467"})
    assert bad_host.status_code == 403


def test_open_routes(client):
    r = client.get("/api/status", headers={"X-Forge": ""})
    assert r.status_code == 200 and r.json()["state"] == "idle"
    assert "text" not in json.dumps(r.json())
    assert client.get("/", headers={"X-Forge": ""}).status_code == 200


def test_localhost_host_ok(client):
    assert (
        client.get("/api/settings", headers={"Host": "localhost:8467"}).status_code
        == 200
    )


@pytest.mark.parametrize(
    "origin,ok",
    [
        ("http://127.0.0.1:8445", True),
        ("http://localhost:5000", True),
        ("https://evil.example", False),
        ("http://127.0.0.1.evil.example", False),
        ("http://localhost.evil:80", False),
    ],
)
def test_cors(client, origin, ok):
    r = client.options(
        "/api/tts",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-forge,content-type",
        },
    )
    assert (r.headers.get("access-control-allow-origin") == origin) is ok


# ---- settings
def test_settings_merge_and_resolve(client):
    r = client.post(
        "/api/settings",
        json={
            "tts": {"speed": 1.2},
            "apps": {"claude": {"tts": {"voice": "b"}, "speak_replies": True}},
        },
    )
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["tts"]["speed"] == 1.2 and s["ptt"]["hold_s"] == 0.35
    r = client.post(
        "/api/settings", json={"apps": {"claude": {"stt": {"model": "fake-stt"}}}}
    )
    s = r.json()
    assert s["apps"]["claude"]["tts"]["voice"] == "b"  # partial merge kept it
    reg = service.load_registry()
    p = service.resolve(s, reg, "claude")
    assert p == {
        "stt": "fake-stt",
        "tts": "fake-tts",
        "voice": "b",
        "speed": 1.2,
        "speak_replies": True,
    }
    q = service.resolve(s, reg, "other")
    assert q["voice"] == "a" and q["speak_replies"] is False
    assert service.resolve(s, reg, "anywhere")["speak_replies"] is True


@pytest.mark.parametrize(
    "bad",
    [
        [],
        {"nope": 1},
        {"tts": {"speed": 9}},
        {"tts": {"model": "fake-stt"}},
        {"stt": {"model": "missing"}},
        {"ptt": {"hold_s": "x"}},
        {"anywhere": {"target": "bob"}},
        {"apps": {"Bad Name": {}}},
        {"apps": {"x": {"speak_replies": "yes"}}},
        {"resources": {"cpus": "1; rm"}},
        {"max_chars": True},
    ],
)
def test_settings_rejects(client, bad):
    assert client.post("/api/settings", json=bad).status_code == 400


def test_apps_discovered(client, tmp_path, monkeypatch):
    for name, voice in (("alpha", {"speaks": True}), ("beta", None)):
        d = tmp_path / "apps" / name
        d.mkdir(parents=True)
        m: dict = {"name": name, "label": name.title()}
        if voice:
            m["voice"] = voice
        (d / "forge_app.json").write_text(json.dumps(m))
    monkeypatch.setenv("FORGE_APPS_DIR", str(tmp_path / "apps"))
    names = [a["name"] for a in client.get("/api/apps").json()["apps"]]
    assert names == ["anywhere", "alpha"]


# ---- tts / stt
def test_tts_returns_wav(client):
    r = client.post("/api/tts", json={"text": "**Hello** `world`", "speed": 1.1})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert (
        r.headers["x-voice-model"] == "fake-tts"
        and r.headers["x-voice-seconds"] == "1.0"
    )
    with wave.open(io.BytesIO(r.content)) as w:
        assert w.getframerate() == 24000
    kind, text, voice, speed = FakeEngine.calls[-1]
    assert "*" not in text and "`" not in text and voice == "a" and speed == 1.1


@pytest.mark.parametrize(
    "body",
    [
        {"text": ""},
        {"text": "  ** "},
        {},
        {"text": "x", "speed": 5},
        {"text": "x", "model": "fake-stt"},
        {"text": "x", "model": "nope"},
    ],
)
def test_tts_400(client, body):
    assert client.post("/api/tts", json=body).status_code == 400


def test_tts_503_missing_files_and_engine_error(client):
    r = client.post("/api/tts", json={"text": "hi", "model": "gone-tts"})
    assert r.status_code == 503 and "not downloaded" in r.json()["detail"]

    def boom(*a):
        raise RuntimeError("bad onnx")

    import web_app

    web_app.voice.models.loader = boom
    r = client.post("/api/tts", json={"text": "hi"})
    assert r.status_code == 503 and "bad onnx" in r.json()["detail"]


def test_stt(client, tmp_path):
    wav = tone_wav(tmp_path / "a.wav", 1.0).read_bytes()
    r = client.post("/api/stt?app=claude", content=wav)
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "hello there" and r.json()["model"] == "fake-stt"
    assert FakeEngine.calls[-1] == ("stt", 16000)


def test_stt_refuses_a_voice_model(client, tmp_path):
    wav = tone_wav(tmp_path / "a.wav", 1.0).read_bytes()
    r = client.post("/api/stt?model=fake-tts", content=wav)
    assert r.status_code == 400 and "not a speech-to-text model" in r.text
    assert not any(call[0] == "stt" for call in FakeEngine.calls[-1:])


def test_stt_400(client, tmp_path):
    assert client.post("/api/stt", content=b"").status_code == 400
    assert client.post("/api/stt", content=b"not audio at all").status_code == 400
    long = tone_wav(tmp_path / "l.wav", 125.0).read_bytes()
    assert client.post("/api/stt", content=long).status_code == 400
    assert (
        client.post("/api/stt", content=b"0" * (20 * 1024 * 1024 + 1)).status_code
        == 400
    )


def test_say_and_hush(client):
    r = client.post("/api/say", json={"text": "hi"})
    assert r.status_code == 200 and r.json()["ok"]
    assert client.post("/api/hush").json()["ok"]


def test_unload(client):
    client.post("/api/tts", json={"text": "hi"})
    assert [m["id"] for m in client.get("/api/status").json()["loaded"]] == ["fake-tts"]
    assert client.post("/api/unload").json()["unloaded"] == ["fake-tts"]


def test_reap_keeps_stt(client, tmp_path):
    import web_app

    client.post("/api/tts", json={"text": "hi"})
    client.post("/api/stt", content=tone_wav(tmp_path / "a.wav").read_bytes())
    assert web_app.voice.models.reap(-1) == ["fake-tts"]
    assert [m["id"] for m in web_app.voice.models.status()] == ["fake-stt"]


# ---- routing with fake Acchan / Claude
class Fake(BaseHTTPRequestHandler):
    seen: list = []
    replies = 0
    fault = ""  # drop_ask | ask_404 | drop_reply

    def log_message(self, format, *args):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.seen.append((self.path, body, self.headers.get("X-Forge")))
        if self.path == "/api/voice/command":
            if "volume" in body["text"].lower():
                said = {"handled_by": "fast", "reply": "Volume set to 40."}
            elif body.get("use_model") is False:  # no command matched
                said = {"handled_by": "none", "reply": ""}
            else:
                said = {"handled_by": "jan", "reply": "Jan here."}
            return self._send(200, {**said, "calls": [], "ms": 3})
        if self.path == "/api/voice/ask":
            if Fake.fault == "drop_ask":  # taken, then the connection drops
                self.close_connection = True
                return None
            if Fake.fault == "ask_404":  # a Claude app without the voice routes
                return self._send(404, {})
            return self._send(200, {"id": "v1"})
        self._send(404, {})

    def do_GET(self):
        Fake.seen.append((self.path, None, self.headers.get("X-Forge")))
        if Fake.fault == "drop_reply":
            self.close_connection = True
            return None
        Fake.replies += 1
        done = Fake.replies >= 2
        self._send(
            200,
            {"done": done, "text": "It is **sunny**." if done else "", "error": None},
        )


@pytest.fixture
def fake_server(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}"
    Fake.seen, Fake.replies = [], 0
    monkeypatch.setenv("FORGE_ACCHAN_URL", url)
    monkeypatch.setenv("FORGE_CLAUDE_URL", url)
    yield url
    srv.shutdown()


def test_ask_jan_and_claude(fake_server):
    assert service.ask_jan("volume 40") == {
        "handled_by": "fast",
        "reply": "Volume set to 40.",
    }
    assert Fake.seen[0] == (
        "/api/voice/command",
        {"text": "volume 40", "use_model": True, "source": "voice"},
        "1",
    )
    r = service.ask_claude("weather?", wait=1)
    assert r == {"handled_by": "claude", "reply": "It is **sunny**."}
    assert Fake.seen[1][:2] == (
        "/api/voice/ask",
        {"text": "weather?", "source": "voice"},
    )
    assert Fake.seen[2][0].startswith("/api/voice/reply?id=v1&wait=1")


def test_down_services_spoken_message():
    assert service.ask_jan("x")["reply"] == "Acchan is not answering."
    assert service.ask_claude("x")["reply"] == "Claude is not answering."


@pytest.mark.parametrize(
    "text,target,want",
    [
        ("Claude, what's up", "auto", ("claude", "what's up", True)),
        ("tetsu check the build", "auto", ("claude", "check the build", True)),
        ("Acchan volume 40", "auto", ("jan", "volume 40", True)),
        ("volume 40", "auto", ("claude", "volume 40", False)),
        ("Claude hi", "jan", ("jan", "hi", True)),
        ("hello", "text", ("text", "hello", True)),
    ],
)
def test_route(text, target, want):
    assert service.route(text, target, "auto") == want


@pytest.mark.parametrize(
    "default,want",
    [("jan", "jan"), ("text", "text"), ("claude", "claude"), ("x", "claude")],
)
def test_route_default_brain(default, want):
    assert service.route("what is new", "auto", default) == (want, "what is new", False)


def test_unnamed_command_is_done_by_acchan_without_a_model(fake_server):
    assert service.answer("claude", "volume 40", False) == {
        "target": "jan",
        "handled_by": "fast",
        "reply": "Volume set to 40.",
    }
    assert Fake.seen == [
        (
            "/api/voice/command",
            {"text": "volume 40", "use_model": False, "source": "voice"},
            "1",
        )
    ]


def test_unnamed_question_goes_to_claude_after_the_commands(fake_server):
    r = service.answer("claude", "what is new", False)
    assert r == {
        "target": "claude",
        "handled_by": "claude",
        "reply": "It is **sunny**.",
    }
    assert Fake.seen[0][1]["use_model"] is False
    assert [x[0].split("?")[0] for x in Fake.seen[1:]] == [
        "/api/voice/ask",
        "/api/voice/reply",
        "/api/voice/reply",
    ]


def test_claude_down_jan_answers_unnamed_speech(fake_server, monkeypatch):
    monkeypatch.setenv("FORGE_CLAUDE_URL", "http://127.0.0.1:9")
    r = service.answer("claude", "what is new", False)
    assert r == {"target": "jan", "handled_by": "jan", "reply": "Jan here."}
    assert [x[1]["use_model"] for x in Fake.seen] == [False, True]


@pytest.mark.parametrize(
    "fault, target, said",
    [
        ("drop_ask", "claude", "may not have got"),
        ("drop_reply", "claude", "did not come back"),
        ("ask_404", "jan", "Jan here."),
    ],
)
def test_jan_never_runs_what_claude_may_have_taken(
    fake_server, monkeypatch, fault, target, said
):
    """Jan answers un-named speech only when Claude never got it; once the
    request may be with Claude, a lost reply is reported instead (both would
    have acted on "email the report to Bob")."""
    monkeypatch.setattr(Fake, "fault", fault)
    r = service.answer("claude", "email the report to Bob", False)
    assert r["target"] == target and said in r["reply"]
    jan = [x for x in Fake.seen if x[0] == "/api/voice/command" and x[1]["use_model"]]
    assert len(jan) == (1 if target == "jan" else 0)


def test_acchan_down_claude_still_answers(fake_server, monkeypatch):
    monkeypatch.setenv("FORGE_ACCHAN_URL", "http://127.0.0.1:9")
    r = service.answer("claude", "volume 40", False)
    assert r["target"] == "claude" and r["reply"] == "It is **sunny**."


def test_a_name_is_never_redirected(fake_server, monkeypatch):
    r = service.answer("claude", "volume 40", True)
    assert r["target"] == "claude" and Fake.seen[0][0] == "/api/voice/ask"
    Fake.seen.clear()
    monkeypatch.setenv("FORGE_CLAUDE_URL", "http://127.0.0.1:9")
    r = service.answer("claude", "what is new", True)
    assert r == {
        "target": "claude",
        "handled_by": "error",
        "reply": "Claude is not answering.",
    }
    assert Fake.seen == []
    assert service.answer("jan", "what is new", True)["reply"] == "Jan here."
    assert Fake.seen[-1][1]["use_model"] is True


def test_player_hush_never_leaves_busy_stuck(tmp_path, monkeypatch):
    """A hush that empties the queue before the clip started clears busy, and
    one that cuts a clip off lets the player go idle."""
    player = service.Player()
    player.busy = True  # an item was queued and drained before it started
    player.hush()
    assert player.busy is False
    slow = tmp_path / "slow-player"
    slow.write_text("#!/bin/sh\nsleep 5\n")
    slow.chmod(0o755)
    monkeypatch.setenv("FORGE_VOICE_PLAYER", str(slow))
    idle = threading.Event()
    player = service.Player(on_idle=idle.set)
    player.play(b"one")
    player.play(b"two")
    end = time.monotonic() + 5
    while player.proc is None and time.monotonic() < end:
        time.sleep(0.02)
    assert player.proc is not None and player.busy
    player.hush()
    assert idle.wait(3) and player.busy is False and player.q.empty()


def test_press_while_a_line_is_said_only_hushes(client, monkeypatch):
    """A tap or hold while an app's /api/say line plays (no round running)
    stops the line and keeps the mic shut."""
    import web_app

    hushed = []
    monkeypatch.setattr(web_app.voice.player, "busy", True)
    monkeypatch.setattr(web_app.voice.player, "hush", lambda: hushed.append(1))
    before = web_app.voice.session
    assert client.post("/api/ptt/tap").json()["state"] == "idle"
    assert client.post("/api/ptt/down").json()["state"] == "idle"
    assert client.post("/api/ptt/up").json()["state"] == "idle"
    assert hushed == [1, 1] and web_app.voice.session == before


# ---- end to end tap through FORGE_VOICE_CAPTURE
def _settings_quiet(client):
    client.post(
        "/api/settings",
        json={
            "anywhere": {"earcons": False, "notify": False},
            "ptt": {"silence_s": 0.5},
        },
    )


def test_tap_end_to_end(client, fake_server, tmp_path, monkeypatch):
    import web_app

    _settings_quiet(client)
    monkeypatch.setenv(
        "FORGE_VOICE_CAPTURE", str(tone_wav(tmp_path / "c.wav", 3.0, (0.3, 1.0)))
    )
    FakeEngine.heard = "Acchan, volume 40."
    assert client.post("/api/ptt/tap").json()["state"] == "listening"
    assert web_app.voice.done.wait(10)
    h = client.get("/api/history").json()["history"]
    assert h[0]["heard"] == "Acchan, volume 40." and h[0]["target"] == "jan"
    assert h[0]["handled_by"] == "fast" and h[0]["reply"] == "Volume set to 40."
    assert Fake.seen[0][1]["text"] == "volume 40."
    stt = [c for c in FakeEngine.calls if c[0] == "stt"][0]
    assert (
        1.4 * 16000 <= stt[1] <= 2.0 * 16000
    )  # stopped by the silence gate, not the 3 s file end
    assert [c for c in FakeEngine.calls if c[0] == "tts"][0][1] == "Volume set to 40."
    assert client.get("/api/status").json()["state"] == "idle"


def test_tap_unnamed_command_end_to_end(client, fake_server, tmp_path, monkeypatch):
    import web_app

    _settings_quiet(client)
    monkeypatch.setenv("FORGE_VOICE_CAPTURE", str(tone_wav(tmp_path / "c.wav", 2.0)))
    FakeEngine.heard = "Volume 40, please."
    client.post("/api/ptt/tap")
    assert web_app.voice.done.wait(10)
    row = client.get("/api/history").json()["history"][0]
    assert (row["target"], row["handled_by"]) == ("jan", "fast")
    assert Fake.seen[0][1] == {
        "text": "Volume 40, please.",
        "use_model": False,
        "source": "voice",
    }


def test_cancel_discards(client, fake_server, tmp_path, monkeypatch):
    import web_app

    _settings_quiet(client)
    monkeypatch.setenv("FORGE_VOICE_CAPTURE", str(tone_wav(tmp_path / "c.wav", 3.0)))
    client.post("/api/ptt/down")
    assert client.post("/api/ptt/cancel").json()["state"] == "idle"
    web_app.voice.done.wait(5)
    assert not Fake.seen and client.get("/api/history").json()["history"] == []


def test_control_stop_and_repeat(client, fake_server, tmp_path, monkeypatch):
    import web_app

    _settings_quiet(client)
    monkeypatch.setenv("FORGE_VOICE_CAPTURE", str(tone_wav(tmp_path / "c.wav", 2.0)))
    web_app.voice.last_reply = "Old answer."
    FakeEngine.heard = "say that again"
    client.post("/api/ptt/tap")
    assert web_app.voice.done.wait(10)
    row = client.get("/api/history").json()["history"][0]
    assert row["target"] == "control" and row["handled_by"] == "repeat"
    assert ("tts", "Old answer.", "a", 1.0) in FakeEngine.calls
    assert not Fake.seen


def test_ptt_bad_target(client):
    assert client.post("/api/ptt/tap?target=bob").status_code == 400
    assert client.post("/api/ptt/jump").status_code == 404


def test_stand_in_matches_shared_contract(monkeypatch, tmp_path):
    """The local stand-in and shared/forge_voice.py route the same way."""
    real = service.fv()
    stand = service._stand_in()
    wake = service.load_registry()["wake"]
    for text in ("Claude, hi there", "hey acchan volume 40", "volume 40", "tetsu"):
        assert stand.split_target(text, wake) == real.split_target(text, wake), text
    for text in ("stop", "say that again", "cancel", "open firefox"):
        assert stand.is_control(text) == real.is_control(text), text


def test_tap_while_reply_is_made_hushes_it(client, fake_server, tmp_path, monkeypatch):
    """A tap during synthesis wins: the reply is not played afterwards."""
    import web_app

    _settings_quiet(client)
    monkeypatch.setenv("FORGE_VOICE_CAPTURE", str(tone_wav(tmp_path / "c.wav", 2.0)))
    played = []
    made = threading.Event()
    monkeypatch.setattr(web_app.voice.player, "play", lambda wav: played.append(wav))
    real = web_app.voice.synthesize

    def slow(*a, **kw):
        web_app.voice.press("tap")  # the user taps while the reply is being made
        try:
            return real(*a, **kw)
        finally:
            made.set()

    monkeypatch.setattr(web_app.voice, "synthesize", slow)
    FakeEngine.heard = "jan volume 40"
    client.post("/api/ptt/tap")
    assert made.wait(10)
    time.sleep(0.2)  # let the round take the lock after synthesis
    assert played == [] and client.get("/api/status").json()["state"] == "idle"


def test_tap_while_thinking_cancels_the_round(
    client, fake_server, tmp_path, monkeypatch
):
    """A tap while the answer is on its way ends the round at once; the late
    answer is not spoken and the next tap starts a fresh round."""
    import web_app

    _settings_quiet(client)
    monkeypatch.setenv("FORGE_VOICE_CAPTURE", str(tone_wav(tmp_path / "c.wav", 2.0)))
    asked, release = threading.Event(), threading.Event()

    def slow_jan(text):
        asked.set()
        release.wait(10)
        return {"reply": "Late answer.", "handled_by": "agent"}

    monkeypatch.setattr(service, "ask_jan", slow_jan)
    FakeEngine.heard = "jan what is new"
    client.post("/api/ptt/tap")
    assert asked.wait(10)
    assert client.get("/api/status").json()["state"] == "thinking"
    assert client.post("/api/ptt/tap").json()["state"] == "idle"
    assert web_app.voice.done.is_set()
    release.set()
    time.sleep(0.3)  # let the old round see its answer
    assert not [c for c in FakeEngine.calls if c[0] == "tts"]
    assert client.get("/api/status").json()["state"] == "idle"
