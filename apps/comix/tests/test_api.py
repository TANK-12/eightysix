"""API robustness (U1 sweep, 2026-10-08): bad input answers 4xx, never 500."""

import os
import zipfile

import pytest

os.environ.setdefault("COMIX_NO_WORKER", "1")


@pytest.fixture
def client(isolated, monkeypatch):
    from fastapi.testclient import TestClient

    import web_app
    from comix.store import Store

    store = Store(isolated / "api.db")
    monkeypatch.setattr(web_app, "store", store)
    rows = [
        {"number": 1.0, "group": "Asura", "url": "https://comix.to/c/1"},
        {"number": 2.0, "group": "Asura", "url": "https://comix.to/c/2"},
    ]
    sid = store.save_series(
        "https://comix.to/title/x", "X", "comix_to", rows, "all", []
    )
    return TestClient(web_app.app), store, sid


@pytest.mark.parametrize(
    "values",
    [
        {"pause_seconds": "abc"},
        {"pause_seconds": None},
        {"page_passes": [1]},
        {"chapter_attempts": "1e999"},
    ],
)
def test_settings_refuse_a_number_that_is_not_one(client, values):
    c, _, _ = client
    r = c.post("/api/settings", json={"values": values})
    assert r.status_code == 400
    assert "must be a number" in r.json()["detail"]


def test_settings_take_a_number_sent_as_text_and_clamp_it(client):
    c, _, _ = client
    r = c.post("/api/settings", json={"values": {"pause_seconds": "7.6"}})
    assert r.status_code == 200 and r.json()["pause_seconds"] == 7
    r = c.post("/api/settings", json={"values": {"pause_seconds": 10**9}})
    assert r.json()["pause_seconds"] == 120


def test_unknown_series_and_chapter_are_404(client):
    c, _, _ = client
    assert c.post("/api/series/999/choice", json={"mode": "all"}).status_code == 404
    assert c.post("/api/chapters/999/want", json={"wanted": True}).status_code == 404
    assert c.get("/api/series/999").status_code == 404


def test_wrong_types_are_422(client):
    c, _, sid = client
    assert c.post(f"/api/series/{sid}/choice", json={"mode": 5}).status_code == 422
    assert c.post("/api/queue/pause", json={"paused": "maybe"}).status_code == 422
    assert c.get("/api/read/abc").status_code == 422


def test_a_broken_cbz_is_404_not_500(client, isolated):
    c, store, sid = client
    cid = store.chapters(sid)[0]["id"]
    bad = isolated / "bad.cbz"
    bad.write_bytes(b"not a zip at all")
    store.finish(cid, str(bad))
    assert c.get(f"/api/read/{cid}").status_code == 404
    assert c.get(f"/api/read/{cid}/1").status_code == 404


def test_reader_pages_and_out_of_range(client, isolated):
    c, store, sid = client
    cid = store.chapters(sid)[0]["id"]
    good = isolated / "good.cbz"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("001.png", b"\x89PNG fake")
    store.finish(cid, str(good))
    assert c.get(f"/api/read/{cid}").json()["pages"] == 1
    assert c.get(f"/api/read/{cid}/1").status_code == 200
    assert c.get(f"/api/read/{cid}/0").status_code == 404
    assert c.get(f"/api/read/{cid}/99999999").status_code == 404


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/series/99999999999999999999999", None),
        ("post", "/api/series/99999999999999999999999/choice", {"mode": "all"}),
        ("post", "/api/chapters/99999999999999999999999/want", {"wanted": True}),
        ("get", "/api/read/99999999999999999999999", None),
    ],
)
def test_an_id_past_sqlite_range_is_404(client, method, path, body):
    c, _, _ = client
    r = c.get(path) if method == "get" else c.post(path, json=body)
    assert r.status_code == 404


@pytest.mark.parametrize(
    "values",
    [
        {"download_dir": "/tmp/a\0b"},
        {"download_dir": {"a": 1}},
        {"library_url": "https://comix.to/" + "x" * 200_000},
    ],
)
def test_settings_refuse_junk_text(client, values):
    c, _, _ = client
    before = c.get("/api/settings").json()
    r = c.post("/api/settings", json={"values": values})
    assert r.status_code == 400
    after = c.get("/api/settings").json()
    assert after == before


def test_settings_still_take_a_normal_folder(client, isolated):
    c, _, _ = client
    r = c.post("/api/settings", json={"values": {"download_dir": f"  {isolated}/dl  "}})
    assert r.status_code == 200
    assert r.json()["download_dir"] == f"{isolated}/dl"
