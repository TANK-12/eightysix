"""media_lib: settings, the library scan, the file guard, yt-dlp command
lines and its output. No network; yt-dlp is never run here."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import media_lib as lib  # noqa: E402


@pytest.fixture
def home(tmp_path):
    music = tmp_path / "Music"
    (music / "Album").mkdir(parents=True)
    (music / "one.mp3").write_bytes(b"x" * 10)
    (music / "Album" / "two.flac").write_bytes(b"y" * 20)
    (music / "Album" / "cover.jpg").write_bytes(b"z")
    (music / ".hidden").mkdir()
    (music / ".hidden" / "secret.mp3").write_bytes(b"s")
    videos = tmp_path / "Videos"
    videos.mkdir()
    (videos / "clip.mp4").write_bytes(b"v" * 30)
    return tmp_path


def test_settings_round_trip_and_bounds(tmp_path):
    path = tmp_path / "settings.json"
    assert lib.load_settings(path)["volume"] == 80
    saved = lib.save_settings({"volume": 140, "folders": ["~/A", " "], "junk": 1}, path)
    assert saved["volume"] == 100
    assert saved["folders"] == ["~/A"]
    assert "junk" not in json.loads(path.read_text())


def test_scan_finds_media_skips_hidden_and_others(home):
    rows = lib.scan([str(home / "Music"), str(home / "Videos")])
    names = sorted(r["name"] for r in rows)
    assert names == ["clip", "one", "two"]
    by_name = {r["name"]: r for r in rows}
    assert by_name["two"]["folder"] == "Album"
    assert by_name["two"]["kind"] == "audio"
    assert by_name["clip"]["kind"] == "video"
    assert by_name["one"]["size"] == 10


def test_scan_ignores_missing_folders_and_respects_limit(home):
    assert lib.scan([str(home / "nope")]) == []
    assert len(lib.scan([str(home / "Music")], limit=1)) == 1


def test_inside_only_serves_library_files(home):
    folders = [str(home / "Music")]
    assert lib.inside(str(home / "Music" / "one.mp3"), folders) is not None
    assert lib.inside(str(home / "Videos" / "clip.mp4"), folders) is None
    assert lib.inside(str(home / "Music" / "../Videos/clip.mp4"), folders) is None
    assert lib.inside(str(home / "Music"), folders) is None  # a folder, not a file


def test_list_target_search_channel_and_link():
    assert lib.list_target("Tokyo Echo Sounds") == "ytsearch60:Tokyo Echo Sounds"
    assert (
        lib.list_target("https://www.youtube.com/@tokyoechosounds")
        == "https://www.youtube.com/@tokyoechosounds/videos"
    )
    assert (
        lib.list_target("https://www.youtube.com/channel/UCabc/")
        == "https://www.youtube.com/channel/UCabc/videos"
    )
    url = "https://www.youtube.com/watch?v=abc"
    assert lib.list_target(url) == url
    with pytest.raises(ValueError):
        lib.list_target("   ")


def test_parse_listing_search_and_single_video():
    raw = json.dumps(
        {
            "title": "Tokyo Echo Sounds",
            "entries": [
                {
                    "id": "a1",
                    "title": "Song A",
                    "url": "a1",
                    "duration": 61,
                    "uploader": "TES",
                    "channel_url": "https://www.youtube.com/channel/UC1",
                },
                {
                    "id": "b2",
                    "title": "Song B",
                    "webpage_url": "https://www.youtube.com/watch?v=b2",
                    "duration": None,
                },
                "junk",
            ],
        }
    )
    out = lib.parse_listing(raw)
    assert out["title"] == "Tokyo Echo Sounds"
    assert [e["url"] for e in out["entries"]] == [
        "https://www.youtube.com/watch?v=a1",
        "https://www.youtube.com/watch?v=b2",
    ]
    assert out["entries"][0]["duration"] == 61 and out["entries"][1]["duration"] == 0
    single = lib.parse_listing(
        json.dumps({"id": "z9", "title": "One", "webpage_url": "https://youtu.be/z9"})
    )
    assert single["entries"][0]["id"] == "z9"
    assert lib.parse_listing("")["entries"] == []


def test_download_commands(tmp_path):
    audio = lib.download_command(["https://x/1"], tmp_path, "audio")
    assert "-x" in audio and "mp3" in audio and audio[-1] == "https://x/1"
    assert "--no-overwrites" in audio and "--no-playlist" in audio
    video = lib.download_command(["https://x/1", "https://x/2"], tmp_path, "video")
    assert "--merge-output-format" in video and video[-2:] == [
        "https://x/1",
        "https://x/2",
    ]
    assert "-x" not in video


def test_progress_lines():
    assert lib.progress_of(
        "[download]  45.2% of 3.00MiB at 1.00MiB/s"
    ) == pytest.approx(0.452)
    assert lib.progress_of("[ExtractAudio] Destination: x.mp3") is None


def test_list_remote_uses_runner_and_reports_failure():
    calls = []

    def ok(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"title": "T", "entries": []}), stderr=""
        )

    out = lib.list_remote("Tokyo Echo Sounds", run=ok, limit=5)
    assert (
        out["target"] == "ytsearch5:Tokyo Echo Sounds" and calls[0][-1] == out["target"]
    )

    def bad(cmd):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="ERROR: nope\n")

    with pytest.raises(RuntimeError, match="nope"):
        lib.list_remote("x", run=bad)
