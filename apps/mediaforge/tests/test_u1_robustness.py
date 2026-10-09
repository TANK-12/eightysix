"""U1 sweep (2026-10-08): bad input is a 4xx, never a 500; the Duplicate
Slayer page route serves only the pages of a pending review; settings keep
their types. Nothing here writes the real settings file."""

import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import web_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(web_app.state, "settings", dict(web_app.state.settings))
    monkeypatch.setattr(web_app.state, "save_settings", lambda: None)
    return TestClient(web_app.app)


def test_dedupe_thumbnail_refuses_files_outside_a_review(client, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("password")
    r = client.get("/api/dedupe/thumbnail", params={"path": str(secret)})
    assert r.status_code == 404
    assert (
        client.get("/api/dedupe/thumbnail", params={"path": "/etc/passwd"}).status_code
        == 404
    )


def test_dedupe_thumbnail_serves_a_page_of_a_pending_review(
    client, tmp_path, monkeypatch
):
    page = tmp_path / "p0001_0.png"
    page.write_bytes(b"\x89PNG fake")
    job = web_app.Job("dedupe-scan")
    job.result = {"needs_review": True, "groups": [[str(page), str(page)]]}
    monkeypatch.setitem(web_app.state.jobs, job.id, job)
    # A Storage duplicates job keeps a list as its result: it must not
    # break the lookup (it made every page image a 500).
    other = web_app.Job("storage-duplicates")
    other.result = [{"size": 1, "paths": ["/etc/passwd"]}]
    monkeypatch.setitem(web_app.state.jobs, other.id, other)
    r = client.get("/api/dedupe/thumbnail", params={"path": str(page)})
    assert r.status_code == 200 and r.content == b"\x89PNG fake"
    assert (
        client.get("/api/dedupe/thumbnail", params={"path": "/etc/passwd"}).status_code
        == 404
    )
    r = client.post(f"/api/dedupe/{other.id}/finish", json={"keep_from_groups": []})
    assert r.status_code == 404


@pytest.mark.parametrize(
    "values",
    [
        {"advanced_mode": "x"},
        {"jan_base": 5},
        {"crf": "high"},
        {"crf": True},
        {"jan_base": "x" * 5000},
        {"whatever": {"nested": 1}},
        {"whatever": [1, 2]},
    ],
)
def test_settings_keep_their_types(client, values):
    before = dict(web_app.state.settings)
    r = client.post("/api/settings", json={"values": values})
    assert r.status_code == 422, r.text
    assert web_app.state.settings == before


def test_settings_still_save_what_the_page_sends(client):
    r = client.post(
        "/api/settings",
        json={"values": {"jan_base": "http://127.0.0.1:9/v1", "advanced_mode": False}},
    )
    assert r.status_code == 200
    assert r.json()["advanced_mode"] is False


def test_storage_search_refuses_infinite_sizes(client):
    r = client.get("/api/storage/search", params={"min_mb": "-1e999"})
    assert r.status_code == 422


def test_manga_download_refuses_a_chapter_without_a_link(client):
    r = client.post(
        "/api/manga/download", json={"chapters": [["a"]], "out_dir": "/tmp/nowhere"}
    )
    assert r.status_code == 422


def test_page_loads_forge_idle_and_has_no_shouting():
    html = (APP / "static" / "index.html").read_text()
    assert "/shared/forge_idle.js" in html
    for loud in ("MEDIA<span>FORGE", "OFFLINE", "KILL<"):
        assert loud not in html


def test_a_saved_value_of_the_wrong_type_falls_back_to_its_default(
    monkeypatch, tmp_path
):
    # jan_base 5 in settings.json used to stop the app from starting
    from mediaforge import config

    path = tmp_path / "settings.json"
    path.write_text('{"jan_base": 5, "crf": 18, "advanced_mode": "x", "extra": [1]}')
    monkeypatch.setattr(config, "SETTINGS_PATH", path)
    s = config.load_settings()
    assert s["jan_base"] == config.DEFAULTS["jan_base"]
    assert s["advanced_mode"] is config.DEFAULTS["advanced_mode"]
    assert s["crf"] == 18
    assert "extra" not in s


def test_probe_of_a_missing_file_is_a_404_not_fake_tracks(client):
    r = client.get("/api/subtitles/probe", params={"path": "/nope/missing.mkv"})
    assert r.status_code == 404


def test_probe_of_a_file_that_is_not_media_is_a_400(client, tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("not a video")
    r = client.get("/api/subtitles/probe", params={"path": str(f)})
    assert r.status_code == 400


def test_validation_errors_read_as_one_line(client):
    r = client.get("/api/storage/search", params={"min_mb": "lots"})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("min_mb: ")
