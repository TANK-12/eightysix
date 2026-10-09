"""engines/breeze_cpp.py against a stand-in server (tests/fake_breeze_server.py)."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from conftest import tone_wav
from engines import InputError

FAKE = Path(__file__).with_name("fake_breeze_server.py")
REF_TEXT = "The harbour lights came on one by one."


@pytest.fixture
def breeze(env, tmp_path, monkeypatch):
    """A row, its files and a log of what the server was asked."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("FAKE_BREEZE_LOG", str(tmp_path / "fake.log"))
    d = tmp_path / "models" / "voice" / "tts" / "breeze"
    d.mkdir(parents=True)
    (d / "m.gguf").write_bytes(b"gguf")
    tone_wav(d / "ref.wav")
    server = tmp_path / "breeze-server"  # argv[1] is this path, as for a script
    code = FAKE.read_text().split("\n", 1)[1]
    server.write_text(f"#!{sys.executable}\n{code}")
    server.chmod(0o755)
    row = {
        "id": "breeze-test",
        "kind": "tts",
        "engine": "breeze_cpp",
        "ref_text": REF_TEXT,
        "default_voice": "harbour",
        "load_timeout_s": 20,
    }
    files = {"model": d / "m.gguf", "ref": d / "ref.wav", "server": server}
    return row, files, tmp_path / "fake.log"


def asked(log: Path) -> list[dict]:
    return [json.loads(x) for x in log.read_text().splitlines()]


def test_load_saves_the_voice_speaks_and_stops(breeze):
    from engines import breeze_cpp

    row, files, log = breeze
    eng = breeze_cpp.Engine(row, files, 3)
    try:
        assert eng.voices() == ["harbour"]  # cached voices are not listed
        assert (files["model"].parent / "voices" / "harbour.breeze").exists()
        audio, rate = eng.synthesize("one two three", "harbour", 1.4)
        assert rate == 24000 and audio.dtype == np.float32
        assert len(audio) == 3 * 2400 and 0.2 < np.abs(audio).max() < 0.3
        proc = eng.proc
        assert proc is not None
        assert eng.pidfile.name == f"breeze-test@{os.getpid()}.pid"
        assert eng.pidfile.read_text().split() == [str(proc.pid), str(os.getpid())]
        start = asked(log)[0]
        assert start["omp"] == "3"
        argv = start["argv"]
        assert argv[argv.index("--ws-port") + 1] == "-1"
        assert argv[argv.index("--host") + 1] == "127.0.0.1"
        assert "--cpu" not in argv
        assert asked(log)[1] == {"saved": "harbour", "ref_text": REF_TEXT}
    finally:
        eng.close()
    assert proc.poll() is not None and not eng.pidfile.exists()
    eng.close()  # twice is fine


def test_saved_voice_is_not_saved_again_and_cpu_row(breeze):
    from engines import breeze_cpp

    row, files, log = breeze
    vd = files["model"].parent / "voices"
    vd.mkdir()
    (vd / "harbour.breeze").write_bytes(b"BRZV")
    eng = breeze_cpp.Engine(dict(row, device="cpu"), files, 2)
    eng.close()
    lines = asked(log)
    assert "--cpu" in lines[0]["argv"] and len(lines) == 1


def test_unknown_voice_uses_the_default_and_busy_is_retried(breeze, monkeypatch):
    from engines import breeze_cpp

    row, files, log = breeze
    monkeypatch.setenv("FAKE_BREEZE_MODE", "busy:2")
    eng = breeze_cpp.Engine(row, files, 1)
    try:
        audio, _ = eng.synthesize("hello there", "af_heart", 1.0)
    finally:
        eng.close()
    assert len(audio) == 2 * 2400
    voices = [x["speech"]["voice_id"] for x in asked(log) if "speech" in x]
    assert voices == ["af_heart", "af_heart", "af_heart", "harbour"]


def test_a_server_that_dies_says_why(breeze, monkeypatch):
    from engines import breeze_cpp

    row, files, _ = breeze
    monkeypatch.setenv("FAKE_BREEZE_MODE", "die")
    with pytest.raises(RuntimeError, match="failed to load model"):
        breeze_cpp.Engine(row, files, 1)
    assert not list(breeze_cpp.state_dir().glob("breeze-test*.pid"))


def test_missing_ref_text_fails_and_stops_the_server(breeze):
    from engines import breeze_cpp

    row, files, log = breeze
    with pytest.raises(RuntimeError, match="ref_text"):
        breeze_cpp.Engine(dict(row, ref_text=""), files, 1)
    assert not Path(f"/proc/{asked(log)[0]['pid']}").exists()
    assert not list(breeze_cpp.state_dir().glob("breeze-test*.pid"))


def test_a_server_left_by_a_crash_is_stopped(breeze):
    from engines import breeze_cpp

    row, files, _ = breeze
    old = breeze_cpp.Engine(row, files, 1)
    old_proc = old.proc
    assert old_proc is not None
    new = breeze_cpp.Engine(row, files, 1)  # the backend restarted after a crash
    try:
        assert old_proc.wait(timeout=5) is not None
        assert new.proc is not None
        assert new.pidfile.read_text().split()[0] == str(new.proc.pid)
        old.close()  # the old engine must not take the new server's pid file
        assert new.pidfile.exists()
    finally:
        new.close()


def test_stop_stale_leaves_other_programs_alone(tmp_path):
    from engines import breeze_cpp

    old, new = tmp_path / "x.pid", tmp_path / "x@1.pid"
    old.write_text(f"{os.getpid()}\n")  # this pytest process, not a breeze-server
    new.write_text(f"{os.getpid()} 1\n")
    breeze_cpp.stop_stale(tmp_path, "x", tmp_path / "breeze-server")
    assert not old.exists() and not new.exists()  # the files go, the process stays


def test_multipart_body():
    from engines import breeze_cpp

    p = Path(__file__)
    body, ctype = breeze_cpp.multipart({"name": "v1"}, {"ref_audio": p})
    b = ctype.split("boundary=")[1].encode()
    assert body.startswith(b"--" + b) and body.endswith(b"--" + b + b"--\r\n")
    assert b'name="name"\r\n\r\nv1\r\n' in body
    assert b'filename="test_breeze_engine.py"' in body and p.read_bytes() in body


def test_a_live_backend_keeps_its_server(breeze, tmp_path):
    """A second backend (a scratch run on the same cache) leaves alone a
    server another live backend owns; once that backend dies, its orphaned
    server is stopped."""
    from engines import breeze_cpp

    row = breeze[0]
    sd = breeze_cpp.state_dir()
    sd.mkdir(parents=True, exist_ok=True)
    srv = tmp_path / "sleeper"  # stands in for breeze-server (argv[1] is its path)
    srv.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
    srv.chmod(0o755)
    code = (
        "import os, subprocess, time\n"
        f"p = subprocess.Popen([{str(srv)!r}])\n"
        f"f = {str(sd)!r} + '/{row['id']}@' + str(os.getpid()) + '.pid'\n"
        "open(f + '.tmp', 'w').write(f'{p.pid} {os.getpid()}')\n"
        "os.rename(f + '.tmp', f)\n"
        "time.sleep(60)\n"
    )
    backend = subprocess.Popen([sys.executable, "-c", code])
    pf = sd / f"{row['id']}@{backend.pid}.pid"
    end = time.monotonic() + 10
    while not pf.exists() and time.monotonic() < end:
        time.sleep(0.05)
    server = int(pf.read_text().split()[0])
    try:
        breeze_cpp.stop_stale(sd, row["id"], srv)  # what a scratch load does
        breeze_cpp.clear_stale(row, {"server": srv})
        assert Path(f"/proc/{server}").exists() and pf.exists()
        backend.kill()  # the live backend crashes; its server is orphaned
        backend.wait()
        breeze_cpp.clear_stale(row, {"server": srv})
        assert not Path(f"/proc/{server}").exists() and not pf.exists()
    finally:
        backend.kill()
        backend.wait()
        try:
            os.kill(server, 9)
        except OSError:
            pass


def test_clear_stale_leaves_this_backends_own_server(breeze):
    """Before a memory check the backend's own server stays (a load may be
    under way); a new load in the same backend replaces it."""
    from engines import breeze_cpp

    row, files, _ = breeze
    eng = breeze_cpp.Engine(row, files, 1)
    try:
        assert eng.proc is not None
        breeze_cpp.clear_stale(row, files)
        assert eng.proc.poll() is None and eng.pidfile.exists()
    finally:
        eng.close()


def make_profile(home: Path, pid: str, language: str, text: str) -> Path:
    d = home / pid
    d.mkdir(parents=True)
    tone_wav(d / "calm.wav")
    clips = {"calm": {"wav": "calm.wav", "text": text}}
    (d / "profile.json").write_text(json.dumps({"language": language, "clips": clips}))
    return d


def test_a_profile_is_saved_once_from_its_calm_clip(breeze, tmp_path):
    import expressive
    from engines import breeze_cpp

    row, files, log = breeze
    home = tmp_path / "profiles"
    lena = make_profile(home, "lena", "en", "Handler One to all units.")
    make_profile(home, "shin-ja", "ja", "こちらアンダーテイカー。")
    make_profile(home, "mute", "en", "")
    row = dict(row, languages=["en"], expressive="breeze")
    eng = breeze_cpp.Engine(row, dict(files, profiles=home), 2)
    try:
        assert eng.voices() == ["harbour", "lena", "mute"]
        eng.synthesize("[angry] Fall back now.", "lena", 1.0)
        eng.synthesize("Fall back now.", "lena", 1.0)
        saves = [e for e in asked(log) if "saved" in e]
        speech = [e["speech"] for e in asked(log) if "speech" in e]
        assert len(saves) == 2  # harbour at load, then lena once
        name = saves[1]["saved"]
        assert name.startswith("p-lena-") and len(name) == len("p-lena-") + 10
        assert saves[1]["ref_text"] == "Handler One to all units."
        assert [s["voice_id"] for s in speech] == [name, name]
        angry = expressive.style("breeze")["instructions"]["angry"]
        assert speech[0]["instruction"] == angry
        assert "instruction" not in speech[1]
        assert eng.voices() == ["harbour", "lena", "mute"]  # the copy is hidden

        tone_wav(lena / "calm.wav", seconds=1.5)  # a new calm clip, a new voice
        eng.synthesize("Fall back now.", "lena", 1.0)
        new = [e for e in asked(log) if "saved" in e][-1]["saved"]
        assert new.startswith("p-lena-") and new != name
        assert asked(log)[-1]["speech"]["voice_id"] == new

        eng.synthesize("Hello.", "shin-ja", 1.0)  # not a Breeze language
        assert asked(log)[-1]["speech"]["voice_id"] == "harbour"
        assert len([e for e in asked(log) if "saved" in e]) == 3
        with pytest.raises(InputError, match="no words"):
            eng.synthesize("Hello.", "mute", 1.0)
    finally:
        eng.close()


def test_a_second_engine_finds_the_saved_copy(breeze, tmp_path):
    from engines import breeze_cpp

    row, files, log = breeze
    home = tmp_path / "profiles"
    make_profile(home, "lena", "en", "Handler One to all units.")
    files = dict(files, profiles=home)
    for _ in range(2):
        eng = breeze_cpp.Engine(dict(row, languages=["en"]), files, 2)
        try:
            eng.synthesize("Fall back now.", "lena", 1.0)
        finally:
            eng.close()
    saved = [e["saved"] for e in asked(log) if "saved" in e]
    assert len(saved) == 2 and saved[0] == "harbour" and saved[1].startswith("p-lena-")
