"""shared/forge_music.py and the music parts of forge_theme: the hub's
background music folder, "add from a YouTube link", and the system-audio
levels the visualiser draws. Fakes stand in for cava and yt-dlp, so nothing
here touches the network or the sound card.

HOW TO RUN
    apps/media/.venv/bin/python -m pytest -q tests/test_forge_music.py
    (stdlib only; any python with pytest works)
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

import forge_music  # noqa: E402
import forge_theme  # noqa: E402
import forge_ytdlp  # noqa: E402


def collect():
    events: list[dict] = []
    lock = threading.Lock()

    def push(e):
        with lock:
            events.append(e)

    return events, push


def wait_for(fn, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.02)
    return False


# --------------------------------------------------------------------------
# the music folder


def test_tracks_take_audio_and_video_one_level_down(tmp_path):
    (tmp_path / "Forge").mkdir()
    (tmp_path / "lofi playlist 각자의.mp4").write_bytes(b"v")
    (tmp_path / "Forge" / "song [abc].mp3").write_bytes(b"a")
    (tmp_path / "cover.jpg").write_bytes(b"i")
    names = [t["name"] for t in forge_theme.music_tracks(str(tmp_path))]
    assert names == ["lofi playlist 각자의", "song [abc]"]
    url = forge_theme.music_tracks(str(tmp_path))[0]["url"]
    assert url.startswith("file://") and " " not in url


def test_music_note_says_why_there_is_nothing(tmp_path):
    assert "does not exist" in forge_theme.music_note(str(tmp_path / "nope"))
    assert "No music in" in forge_theme.music_note(str(tmp_path))
    (tmp_path / "a.ogg").write_bytes(b"a")
    assert forge_theme.music_note(str(tmp_path)) == ""
    assert "No music folder" in forge_theme.music_note("")


def test_theme_carries_the_note(tmp_path):
    settings = forge_theme.load(tmp_path / "missing.json")
    settings.update(music=True, music_folder=str(tmp_path / "nope"))
    data = forge_theme.theme(settings)
    assert data["music_tracks"] == [] and "does not exist" in data["music_note"]


# --------------------------------------------------------------------------
# add from a YouTube link

FAKE_YTDLP = """#!/usr/bin/env python3
import sys
args = sys.argv[1:]
url = args[-1]
if "bad" in url:
    print("ERROR: [youtube] bad: Video unavailable"); sys.exit(1)
out = args[args.index("-o") + 1]
path = out.replace("%(title).150s", "Chill mix").replace("%(id)s", "xyz").replace("%(ext)s", "webm")
print("[download] Destination: " + path, flush=True)
for p in ("5.0", "60.0", "100.0"):
    print(f"[download]  {p}% of 3.00MiB", flush=True)
mp3 = path[:-4] + "mp3"
print("[ExtractAudio] Destination: " + mp3)
open(mp3, "wb").write(b"ID3")
"""


def fake_ytdlp(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "yt-dlp"
    exe.write_text(FAKE_YTDLP)
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")


def test_add_saves_the_audio_and_hands_back_tracks(tmp_path, monkeypatch):
    fake_ytdlp(tmp_path, monkeypatch)
    folder = tmp_path / "Music"
    events, push = collect()
    forge_music.add("https://www.youtube.com/watch?v=xyz", push, folder=folder)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "add-progress" and kinds[-1] == "add-done", kinds
    assert any(e.get("frac") == 1.0 for e in events)
    done = events[-1]
    assert (folder / "Chill mix [xyz].mp3").exists()
    assert done["file"] == (folder / "Chill mix [xyz].mp3").as_uri()
    assert [t["name"] for t in done["tracks"]] == ["Chill mix [xyz]"]
    assert done["note"] == ""


def test_add_reports_failure_and_refuses_non_links(tmp_path, monkeypatch):
    fake_ytdlp(tmp_path, monkeypatch)
    events, push = collect()
    forge_music.add("https://www.youtube.com/watch?v=bad", push, folder=tmp_path / "M")
    assert events[-1] == {
        "type": "add-error",
        "error": "ERROR: [youtube] bad: Video unavailable",
    }
    events.clear()
    forge_music.add("--exec rm", push, folder=tmp_path / "M")
    assert events == [
        {"type": "add-error", "error": "paste a YouTube link (https://...)"}
    ]


def test_destination_of_follows_the_final_file():
    assert (
        forge_ytdlp.destination_of("[ExtractAudio] Destination: /m/a.mp3") == "/m/a.mp3"
    )
    assert (
        forge_ytdlp.destination_of("[download] /m/a.mp3 has already been downloaded")
        == "/m/a.mp3"
    )
    assert forge_ytdlp.destination_of("[download]  50.0% of 3MiB") is None


# --------------------------------------------------------------------------
# system audio levels

FAKE_CAVA = """#!/usr/bin/env python3
import sys, time
bars = int([l for l in open(sys.argv[2]) if l.startswith("bars")][0].split("=")[1])
frames = [";".join(["0"] * bars) + ";"] * 3 + ["500;" * bars, "1000;" * bars, "12;3"]
for f in frames:
    print(f, flush=True); time.sleep(0.01)
time.sleep(30)
"""


def fake_cava(tmp_path):
    exe = tmp_path / "cava"
    exe.write_text(FAKE_CAVA)
    exe.chmod(0o755)
    return str(exe)


def test_parse_frame():
    assert forge_music.parse_frame("0;500;1000;\n", 3) == [0.0, 0.5, 1.0]
    assert forge_music.parse_frame("0;500;", 3) is None  # torn line
    assert forge_music.parse_frame("a;b;c;", 3) is None
    assert "bars = 24" in forge_music.cava_config(24, 30)


def test_the_pulse_asks_cava_for_fast_levels():
    # Alt+V felt late: cava's own noise reduction (77) held every level back
    # for several frames before the hub ever saw the beat. The visualiser
    # lagged the same way (task 56), so it runs on a light 30 now.
    assert "noise_reduction = 30" in forge_music.cava_config(32, 30)
    fast = forge_music.cava_config(32, 60, fast=True)
    assert "noise_reduction = 15" in fast and "framerate = 60" in fast


def test_a_new_shape_restarts_cava_and_the_same_shape_does_not(tmp_path):
    levels = forge_music.SystemLevels(exe=fake_cava(tmp_path))
    events, push = collect()
    assert levels.start(push, bars=4)
    first = levels.proc
    assert levels.start(push, bars=4) and levels.proc is first
    assert levels.start(push, bars=4, fps=60, fast=True)
    assert levels.proc is not first and levels.shape == (4, 60, True)
    assert "noise_reduction = 15" in Path(levels.conf).read_text()
    levels.stop()
    assert wait_for(lambda: not levels.running())
    assert not any(e["type"] == "levels-off" for e in events), events


def test_levels_stream_skip_repeated_silence_and_stop(tmp_path):
    levels = forge_music.SystemLevels(exe=fake_cava(tmp_path))
    events, push = collect()
    assert levels.start(push, bars=4)
    assert wait_for(lambda: len(events) >= 3)
    assert levels.running()
    v = [e["v"] for e in events if e["type"] == "levels"]
    assert v[:3] == [[0.0] * 4, [0.5] * 4, [1.0] * 4]  # three silent frames sent once
    conf = levels.conf
    levels.stop()
    assert wait_for(lambda: not levels.running())
    assert conf and not os.path.exists(conf)


def test_a_stop_we_asked_for_is_never_reported_as_cava_stopping(tmp_path):
    # The hub stops the levels whenever it opens an app or hides. cava's end
    # used to race stop(), come back as "cava stopped", and switch the
    # visualiser to the Forge music only for good: QBZ was ignored after that.
    levels = forge_music.SystemLevels(exe=fake_cava(tmp_path))
    for _ in range(20):
        events, push = collect()
        assert levels.start(push, bars=4)
        assert wait_for(lambda: len(events) >= 1)
        levels.stop()
        assert wait_for(lambda: not levels.running())
        time.sleep(0.05)
        assert not any(e["type"] == "levels-off" for e in events), events


def test_a_cava_that_ignores_term_is_killed_and_reaped(tmp_path):
    # Task 71: a "[cava] <defunct>" child of forge.py. A cava that does not
    # end on TERM was killed but never waited for.
    exe = tmp_path / "cava"
    exe.write_text(
        "#!/usr/bin/env python3\n"
        "import signal, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "while True:\n"
        "    print('0;0;0;0;', flush=True); time.sleep(0.01)\n"
    )
    exe.chmod(0o755)
    levels = forge_music.SystemLevels(exe=str(exe))
    events, push = collect()
    assert levels.start(push, bars=4)
    proc = levels.proc
    assert proc is not None
    assert wait_for(lambda: len(events) >= 1)
    levels.stop()
    assert proc.returncode is not None  # reaped: no zombie left behind
    assert not Path(f"/proc/{proc.pid}").exists()


def test_levels_stop_when_the_page_goes_quiet(tmp_path, monkeypatch):
    levels = forge_music.SystemLevels(exe=fake_cava(tmp_path))
    monkeypatch.setattr(levels, "KEEPALIVE_S", 0.0)
    events, push = collect()
    levels.start(push, bars=4)
    assert wait_for(lambda: not levels.running(), timeout=5)
    assert not any(e["type"] == "levels-off" for e in events)


def test_no_cava_says_so():
    levels = forge_music.SystemLevels(exe=None)
    levels.exe = None
    events, push = collect()
    assert not levels.start(push)
    assert events == [{"type": "levels-off", "reason": "cava is not installed"}]


def test_handle_routes_requests(tmp_path, monkeypatch):
    events, push = collect()
    folder = tmp_path / "Music"
    folder.mkdir()
    (folder / "x.mp3").write_bytes(b"a")
    monkeypatch.setattr(forge_music, "music_folder", lambda: folder)
    forge_music.handle({"op": "tracks"}, push)
    assert events[-1]["type"] == "tracks" and events[-1]["tracks"][0]["name"] == "x"
    started = []
    monkeypatch.setattr(
        forge_music.LEVELS,
        "start",
        lambda p, bars, fps=30, fast=False: started.append(bars),
    )
    monkeypatch.setattr(forge_music.LEVELS, "stop", lambda: started.append("stop"))
    forge_music.handle({"op": "levels", "on": True, "bars": 999}, push)
    forge_music.handle({"op": "levels", "on": False}, push)
    assert started == [128, "stop"]


# --------------------------------------------------------------------------
# the music folder over http, so the visualiser can read the page's own music


def fetch(url, headers=None):
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), b""


def test_server_serves_music_with_ranges_and_cors(tmp_path):
    import urllib.parse

    folder = tmp_path / "Music"
    (folder / "sub").mkdir(parents=True)
    song = folder / "sub" / "a song.mp3"
    song.write_bytes(bytes(range(200)))
    server = forge_music.MusicServer(lambda: folder)
    try:
        base = server.start()
        url = base + urllib.parse.quote(song.as_uri(), safe="")
        code, head, body = fetch(url)
        assert code == 200 and body == bytes(range(200))
        assert head["Access-Control-Allow-Origin"] == "*"
        assert head["Content-Type"] == "audio/mpeg"
        code, head, body = fetch(url, {"Range": "bytes=10-19"})
        assert code == 206 and body == bytes(range(10, 20))
        assert head["Content-Range"] == "bytes 10-19/200"
        code, _, body = fetch(url, {"Range": "bytes=190-"})
        assert code == 206 and body == bytes(range(190, 200))
        assert base == server.start()  # one server, started once
    finally:
        server.stop()


def test_server_refuses_files_outside_the_music_folder(tmp_path):
    import urllib.parse

    folder = tmp_path / "Music"
    folder.mkdir()
    secret = tmp_path / "secret.mp3"
    secret.write_bytes(b"no")
    notes = folder / "notes.txt"
    notes.write_text("no")
    server = forge_music.MusicServer(lambda: folder)
    try:
        base = server.start()
        for p in (secret, notes, folder / ".." / "secret.mp3", folder / "gone.mp3"):
            code, _, body = fetch(base + urllib.parse.quote(p.as_uri(), safe=""))
            assert code == 404 and body == b""
        assert fetch(base + "nonsense")[0] == 404
    finally:
        server.stop()


def test_handle_serve_hands_back_the_base(monkeypatch):
    events, push = collect()
    monkeypatch.setattr(forge_music.SERVER, "start", lambda: "http://x/t?u=")
    forge_music.handle({"op": "serve"}, push)
    assert events == [{"type": "serve", "base": "http://x/t?u="}]


def test_handle_folder_hands_back_the_full_path_and_makes_it(tmp_path, monkeypatch):
    events, push = collect()
    folder = tmp_path / "not yet" / "Music"
    monkeypatch.setattr(forge_music, "music_folder", lambda: folder)
    forge_music.handle({"op": "folder"}, push)
    assert events == [{"type": "folder", "path": str(folder)}]
    assert folder.is_dir()


def _stream(index, app, value, mute=False):
    vol = {"value": value, "value_percent": f"{round(value / 655.36)}%"}
    return {
        "index": index,
        "mute": mute,
        "volume": {"front-left": dict(vol), "front-right": dict(vol)},
        "properties": {"application.name": app},
    }


def test_make_audible_lifts_only_forge_streams_that_are_silent():
    """#257: WirePlumber saved 0% for "Forge", so every new Forge stream
    started silent (measured live 2026-09-28)."""
    streams = [
        _stream(177, "Forge", 0),
        _stream(178, "Forge", 30000),  # the user's own level stays
        _stream(179, "Forge", 65536, mute=True),
        _stream(267, "Blender", 0),  # not ours
    ]
    calls = []

    def run(argv, **_kw):
        calls.append(argv)
        out = json.dumps(streams) if argv[:3] == ["pactl", "-f", "json"] else ""
        return subprocess.CompletedProcess(argv, 0, out, "")

    assert forge_music.make_audible("Forge", run=run) == [177, 179]
    assert ["pactl", "set-sink-input-volume", "177", "100%"] in calls
    assert ["pactl", "set-sink-input-mute", "179", "0"] in calls
    assert not any("178" in a or "267" in a for a in calls)
    assert not any(
        a[:2] == ["pactl", "set-sink-input-volume"] and a[2] == "179" for a in calls
    )


def test_make_audible_survives_no_pactl():
    def run(argv, **_kw):
        raise FileNotFoundError("pactl")

    assert forge_music.make_audible("Forge", run=run) == []
