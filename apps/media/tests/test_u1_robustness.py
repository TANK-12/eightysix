"""U1 sweep (2026-10-08): bad input to the API is a 4xx, never a 500 or a
job started with nonsense, and a hand-edited settings file cannot take the
routes down."""

import json
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import media_lib as lib  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(
        lib.load_settings, "__defaults__", (tmp_path / "settings.json",)
    )
    monkeypatch.setattr(
        lib.save_settings, "__defaults__", (tmp_path / "settings.json",)
    )
    from fastapi.testclient import TestClient

    import web_app

    return TestClient(web_app.app)


@pytest.mark.parametrize(
    "body",
    [
        {"volume": 10**9},
        {"volume": -1},
        {"folders": ["/tmp/a\x00b"]},
        {"folders": ["x" * 5000]},
        {"folders": [f"/f{i}" for i in range(501)]},
        {"download_folder": ""},
        {"download_folder": "   "},
        {"download_folder": "/tmp/a\x00b"},
    ],
)
def test_settings_refuse_bad_values(client, body):
    r = client.post("/api/settings", json=body)
    assert r.status_code == 422, r.text
    assert client.get("/api/library").status_code == 200


def test_settings_still_take_good_values(client, tmp_path):
    r = client.post(
        "/api/settings",
        json={"volume": 30, "folders": [str(tmp_path)], "download_folder": "~/x"},
    )
    assert r.status_code == 200
    assert r.json()["volume"] == 30


def test_file_route_with_a_nul_byte_is_a_404(client):
    assert client.get("/api/file", params={"path": "/tmp/a\x00b"}).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"text": "a", "limit": -5},
        {"text": "a", "limit": 0},
        {"text": "a", "limit": 501},
        {"text": "a" * 2001},
    ],
)
def test_list_refuses_bad_limits_and_huge_text(client, monkeypatch, body):
    monkeypatch.setattr(lib, "ytdlp", lambda: "/bin/false")
    assert client.post("/api/yt/list", json=body).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"urls": ["https://x"], "kind": "flac"},
        {"urls": ["https://x"] * 501},
        {"urls": ["https://x"], "folder": "/tmp/a\x00b"},
    ],
)
def test_download_refuses_bad_requests(client, monkeypatch, body):
    monkeypatch.setattr(lib, "ytdlp", lambda: "/bin/false")
    assert client.post("/api/yt/download", json=body).status_code == 422


def test_hand_edited_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"volume": "loud", "download_folder": 5, "advanced_mode": "yes"})
    )
    s = lib.load_settings(path)
    assert s["volume"] == 80
    assert s["download_folder"] == "~/Music/Forge"
    assert s["advanced_mode"] is True


def test_scan_skips_a_folder_with_a_nul_byte(tmp_path):
    (tmp_path / "a.mp3").write_bytes(b"x")
    files = lib.scan(["/tmp/bad\x00dir", str(tmp_path)])
    assert [f["name"] for f in files] == ["a"]


def test_page_loads_forge_idle_before_app_js():
    # app.js retries its start through ForgeIdle.poll
    html = (APP / "static" / "index.html").read_text()
    assert html.index("/shared/forge_idle.js") < html.index('src="app.js"')


def test_fifty_one_folders_still_save_and_errors_read_as_one_line(client, tmp_path):
    folders = [str(tmp_path / f"f{i}") for i in range(51)]
    assert client.post("/api/settings", json={"folders": folders}).status_code == 200
    r = client.post("/api/settings", json={"volume": "loud"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    assert r.json()["detail"].startswith("volume: ")
