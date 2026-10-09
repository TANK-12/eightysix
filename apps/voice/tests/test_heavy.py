"""A heavy voice (row "heavy": true) speaks only when there is room for it;
otherwise the registry's default voice speaks and says why (X-Voice-Fell-Back).
Also: a voice belongs to its model, and a row's own idle_unload_s."""

import json
import re
import threading
import time

import pytest

from conftest import FakeEngine


def add_row(env, **row):
    """A fake-engine TTS row (its file made) added to the test registry."""
    path = env / "reg.json"
    reg = json.loads(path.read_text())
    rel = f"voice/tts/{row['id']}/m.gguf"
    (env / "models" / rel).parent.mkdir(parents=True, exist_ok=True)
    (env / "models" / rel).write_bytes(b"x")
    reg["models"].append(
        {"kind": "tts", "engine": "fake", "label": row["id"], "files": {"model": rel}}
        | row
    )
    path.write_text(json.dumps(reg))
    return reg


@pytest.fixture
def big(env, monkeypatch):
    import service

    add_row(
        env,
        id="big-tts",
        heavy=True,
        ram_mb=3000,
        idle_unload_s=60,
        voices=["deep"],
        default_voice="deep",
    )
    monkeypatch.setattr(service, "mem_available_mb", lambda: 16000)
    monkeypatch.setattr(service, "jan_busy", lambda: False)
    return service


def spoke(r):
    return (
        r.headers["x-voice-model"],
        r.headers["x-voice-voice"],
        FakeEngine.calls[-1][2],
    )


def test_heavy_speaks_when_there_is_room(client, big):
    r = client.post("/api/tts", json={"text": "hi", "model": "big-tts"})
    assert r.status_code == 200
    assert spoke(r) == ("big-tts", "deep", "deep")
    assert "x-voice-fell-back" not in r.headers


def test_short_memory_falls_back_to_the_default(client, big, monkeypatch):
    monkeypatch.setattr(big, "mem_available_mb", lambda: 4400)  # needs 3000 + 1500
    r = client.post(
        "/api/tts", json={"text": "hi", "model": "big-tts", "voice": "deep"}
    )
    assert r.status_code == 200
    assert spoke(r) == ("fake-tts", "a", "a")  # the default's voice, not "deep"
    assert "free memory" in r.headers["x-voice-fell-back"]
    assert "4500 MB" in r.headers["x-voice-fell-back"]


def test_a_loaded_heavy_model_skips_the_memory_check(client, big, monkeypatch):
    client.post("/api/tts", json={"text": "hi", "model": "big-tts"})
    monkeypatch.setattr(big, "mem_available_mb", lambda: 100)
    r = client.post("/api/tts", json={"text": "hi", "model": "big-tts"})
    assert spoke(r)[0] == "big-tts"


def test_jan_busy_falls_back(client, big, monkeypatch):
    monkeypatch.setattr(big, "jan_busy", lambda: True)
    r = client.post("/api/tts", json={"text": "hi", "model": "big-tts"})
    assert spoke(r)[0] == "fake-tts" and "Jan is busy" in r.headers["x-voice-fell-back"]


def test_a_failing_heavy_model_falls_back_and_unloads(client, big):
    import web_app

    class Broken(FakeEngine):
        def synthesize(self, text, voice, speed):
            if self.row["id"] == "big-tts":
                raise RuntimeError("server died")
            return super().synthesize(text, voice, speed)

    web_app.voice.models.loader = Broken
    r = client.post("/api/tts", json={"text": "hi", "model": "big-tts"})
    assert r.status_code == 200 and spoke(r)[0] == "fake-tts"
    assert "server died" in r.headers["x-voice-fell-back"]
    assert not web_app.voice.models.is_loaded("big-tts")

    def no_load(row, files, threads):
        if row["id"] == "big-tts":
            raise RuntimeError("no Vulkan")
        return FakeEngine(row, files, threads)

    web_app.voice.models.loader = no_load
    r = client.post("/api/say", json={"text": "hi", "model": "big-tts"})
    assert r.status_code == 200 and FakeEngine.calls[-1][2] == "a"


def test_a_heavy_default_that_cannot_run_is_an_error(client, big, env, monkeypatch):
    reg = json.loads((env / "reg.json").read_text())
    reg["defaults"]["tts"] = "big-tts"
    (env / "reg.json").write_text(json.dumps(reg))
    monkeypatch.setattr(big, "mem_available_mb", lambda: 100)
    r = client.post("/api/tts", json={"text": "hi"})
    assert r.status_code == 503 and "free memory" in r.json()["detail"]


def test_heavy_voice_per_app(client, big):
    s = {
        "tts": {"voice": "b"},
        "apps": {"claude": {"tts": {"model": "big-tts"}}},
    }
    assert client.post("/api/settings", json=s).status_code == 200
    r = client.post("/api/tts", json={"text": "hi", "app": "claude"})
    assert spoke(r) == ("big-tts", "deep", "deep")  # not the global voice "b"
    r = client.post("/api/tts", json={"text": "hi", "app": "mission"})
    assert spoke(r) == ("fake-tts", "b", "b")


def test_a_voice_belongs_to_its_model(env, big):
    reg = big.load_registry()
    s = {"tts": {"voice": "b"}, "apps": {"claude": {"tts": {"model": "big-tts"}}}}
    assert big.voice_for(s, reg, "claude", "big-tts") == "deep"
    assert big.voice_for(s, reg, "claude", "fake-tts") == "b"
    assert big.voice_for(s, reg, "other", "fake-tts") == "b"
    s = {"apps": {"x": {"tts": {"voice": "b"}}}}  # an app voice for the global model
    assert big.voice_for(s, reg, "x", "fake-tts") == "b"
    assert big.voice_for(s, reg, "x", "big-tts") == "deep"
    s = {"tts": {"model": "big-tts", "voice": "deep"}, "apps": {}}
    assert big.voice_for(s, reg, "x", "fake-tts") == "a"
    assert big.voice_for(s, reg, None, "nope") is None


def test_a_row_idle_time_shorter_than_the_global_one(client, big):
    import web_app

    client.post("/api/tts", json={"text": "hi", "model": "big-tts"})
    client.post("/api/tts", json={"text": "hi"})
    m = web_app.voice.models
    for mid in ("big-tts", "fake-tts"):
        m._used[mid] = time.monotonic() - 100
    assert m.reap(300) == ["big-tts"]  # its row says 60 s
    assert m.reap(50) == ["fake-tts"]


def test_jan_busy_reads_jan_cpu_time(monkeypatch):
    import service

    def ticks(*seq):
        it = iter(seq)
        monkeypatch.setattr(service, "jan_ticks", lambda: next(it))

    ticks({"qwen": 100}, {"qwen": 160})
    assert service.jan_busy(0) is True
    ticks({"qwen": 100}, {"qwen": 103})
    assert service.jan_busy(0) is False
    ticks({})
    assert service.jan_busy(0) is False


def test_mem_available(tmp_path):
    import service

    f = tmp_path / "meminfo"
    f.write_text("MemTotal: 32000000 kB\nMemAvailable:    2048000 kB\n")
    assert service.mem_available_mb(str(f)) == 2000
    assert service.mem_available_mb(str(tmp_path / "none")) > 10**6


def test_a_many_line_load_error_still_falls_back(client, big):
    """A server that dies at load prints several log lines; the reason still
    goes out as one header line (a newline in it dropped the connection)."""
    import web_app

    def no_load(row, files, threads):
        if row["id"] == "big-tts":
            raise RuntimeError(
                "breeze-server stopped: ggml_vulkan: device lost\n"
                "error: failed to load model\r\n\x1b[0m" + "x" * 300
            )
        return FakeEngine(row, files, threads)

    web_app.voice.models.loader = no_load
    r = client.post("/api/tts", json={"text": "hi", "model": "big-tts"})
    assert r.status_code == 200 and spoke(r)[0] == "fake-tts"
    why = r.headers["x-voice-fell-back"]
    assert "device lost error: failed to load model" in why
    assert not re.search(r"[\x00-\x1f\x7f]", why) and len(why) <= 200


def test_header_text():
    import web_app

    assert web_app.header_text("a\nb\t c\x00 d\u00e9") == "a b c d?"
    assert web_app.header_text("x" * 300) == "x" * 200


def test_the_reaper_never_unloads_a_model_that_just_finished(big, monkeypatch):
    """A synth longer than the idle time: the reaper waits for it, then finds
    the model fresh, so the next request does not reload it."""
    m = big.Models()
    loads = []

    class Slow:
        def close(self):
            loads.append("closed")

    m.loader = lambda row, files, threads: (loads.append("loaded"), Slow())[1]
    monkeypatch.setattr(big, "model_files", lambda row: {})
    row = {"id": "heavy", "kind": "tts", "idle_unload_s": 0.5}
    a = threading.Thread(target=m.use, args=(row, 1, lambda e: time.sleep(1.0)))
    a.start()
    time.sleep(0.7)  # 0.7 s since it started: past its idle time, still busy
    assert m.reap(300) == []
    a.join()
    m.use(row, 1, lambda e: None)
    assert m.is_loaded("heavy") and loads == ["loaded"]
    m._used["heavy"] = time.monotonic() - 10
    assert m.reap(300) == ["heavy"] and loads == ["loaded", "closed"]


def test_a_server_left_behind_is_cleared_before_the_memory_check(
    client, big, monkeypatch
):
    """An orphaned server holding the memory is stopped first, so the heavy
    voice can load instead of falling back for good."""
    import engines

    freed = []
    monkeypatch.setattr(big, "mem_available_mb", lambda: 16000 if freed else 100)
    monkeypatch.setattr(engines, "clear_stale", lambda row, f: freed.append(row["id"]))
    r = client.post("/api/tts", json={"text": "hi", "model": "big-tts"})
    assert r.status_code == 200 and spoke(r)[0] == "big-tts"
    assert freed == ["big-tts"] and "x-voice-fell-back" not in r.headers

    def boom(row, f):
        raise OSError("no /proc")

    monkeypatch.setattr(engines, "clear_stale", boom)  # never stops the speech
    client.post("/api/unload", json={})
    r = client.post("/api/tts", json={"text": "hi", "model": "big-tts"})
    assert r.status_code == 200 and spoke(r)[0] == "big-tts"
