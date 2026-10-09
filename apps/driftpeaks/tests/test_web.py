"""The Drift Peaks API: shapes through the shared store, levels, save, sounds."""

import json

import pytest
from fastapi.testclient import TestClient

import web_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_CONTENT_DIR", str(tmp_path / "store"))
    monkeypatch.setattr(web_app, "SAVE_DIR", tmp_path / "save")
    return TestClient(web_app.app)


def test_every_shipped_shape_is_valid():
    names = sorted(p.stem for p in web_app.SHIPPED_SHAPES.glob("*.json"))
    assert set(web_app.shipped_shapes()) == set(names)
    assert {"rider", "rock", "pole", "coin", "goat"} <= set(names)


def test_shapes_are_seeded_into_the_shared_store(client, tmp_path):
    body = client.get("/api/shapes").json()
    assert body["problems"] == []
    assert "rider" in body["shapes"] and body["shapes"]["rider"]["id"] == "rider"
    stored = tmp_path / "store" / "shapes" / "driftpeaks-rider.json"
    assert stored.is_file()


def test_an_edit_is_kept_and_revert_restores_the_original(client, tmp_path):
    client.get("/api/shapes")
    rock = client.get("/api/shapes").json()["shapes"]["rock"]
    rock["parts"][0]["role"] = "gold"
    assert client.put("/api/shapes/rock", json=rock).status_code == 200
    assert (
        client.get("/api/shapes").json()["shapes"]["rock"]["parts"][0]["role"] == "gold"
    )
    # a reseed never overwrites the user's copy
    web_app.seed_store()
    assert (
        client.get("/api/shapes").json()["shapes"]["rock"]["parts"][0]["role"] == "gold"
    )
    assert client.delete("/api/shapes/rock").json()["reverted"] is True
    assert (
        client.get("/api/shapes").json()["shapes"]["rock"]["parts"][0]["role"] == "rock"
    )


@pytest.mark.parametrize(
    "shape",
    [
        {"label": "x", "parts": []},
        {"label": "x", "parts": [{"role": "snow", "points": [[0, 0], [1, 1]]}]},
        {
            "label": "x",
            "parts": [{"role": "snow", "points": [[0, 0], [1, 1], [9e9, 0]]}],
        },
        {"label": "x", "parts": [{"role": "1bad", "points": [[0, 0], [1, 1], [2, 0]]}]},
        {"label": "", "parts": [{"role": "snow", "points": [[0, 0], [1, 1], [2, 0]]}]},
    ],
)
def test_bad_shapes_are_refused(client, shape):
    assert client.put("/api/shapes/rock", json=shape).status_code == 422


def test_a_broken_store_file_falls_back_to_the_original(client, tmp_path):
    client.get("/api/shapes")
    (tmp_path / "store" / "shapes" / "driftpeaks-pine.json").write_text("{nope")
    body = client.get("/api/shapes").json()
    assert body["shapes"]["pine"]["label"] == "Pine"
    assert any("driftpeaks-pine" in p for p in body["problems"])


def test_reverting_a_store_only_shape_removes_it(client, tmp_path):
    client.get("/api/shapes")
    rock = client.get("/api/shapes").json()["shapes"]["rock"]
    rock["id"] = "boulder"
    assert client.put("/api/shapes/boulder", json=rock).status_code == 200
    stored = tmp_path / "store" / "shapes" / "driftpeaks-boulder.json"
    assert stored.is_file()
    assert client.delete("/api/shapes/boulder").json()["reverted"] is False
    assert not stored.exists()
    assert client.delete("/api/shapes/boulder").status_code == 404
    assert client.delete("/api/shapes/nosuchshape").status_code == 404


def test_bad_shape_id_is_refused(client):
    assert client.put("/api/shapes/Bad_Id", json={"label": "x"}).status_code == 400
    assert client.delete("/api/shapes/Bad_Id").status_code == 400


def test_levels_have_three_goals_each(client):
    levels = client.get("/api/levels").json()["levels"]
    assert len(levels) >= 10
    assert all(len(level["goals"]) == 3 for level in levels)


def test_save_round_trip_and_size_limit(client, tmp_path):
    assert client.get("/api/save").json() == {}
    data = {"best": {"score": 1200}, "coins": 40, "level": 2}
    assert client.put("/api/save", json=data).status_code == 200
    assert client.get("/api/save").json() == data
    assert json.loads((tmp_path / "save" / "save.json").read_text()) == data
    huge = {"junk": "x" * 300_000}
    assert client.put("/api/save", json=huge).status_code == 413


def test_sounds_are_seeded_and_valid(client):
    sounds = client.get("/api/sounds").json()["sounds"]
    events = {s["event"] for s in sounds}
    assert {"jump", "flip", "crash", "coin"} <= events


def test_index_and_shared_kit_are_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/shared/forge_sound.js").status_code == 200


@pytest.fixture
def music(tmp_path, monkeypatch):
    folder = tmp_path / "music"
    folder.mkdir()
    (folder / "B track.mp3").write_bytes(b"ID3fake-b")
    (folder / "A track.mp3").write_bytes(b"ID3fake-a")
    (folder / "notes.txt").write_text("not music")
    monkeypatch.setattr(web_app, "MUSIC_DIR", folder)
    return TestClient(web_app.app)


def test_the_music_list_holds_only_audio_in_name_order(music):
    tracks = music.get("/api/music").json()["tracks"]
    assert [t["name"] for t in tracks] == ["A track", "B track"]
    assert tracks[0]["url"] == "music/A%20track.mp3"


def test_a_listed_track_is_served(music):
    r = music.get("/music/A track.mp3")
    assert r.status_code == 200 and r.content == b"ID3fake-a"
    assert r.headers["content-type"] == "audio/mpeg"


@pytest.mark.parametrize("name", ["notes.txt", "..%2Fsecret.mp3", "missing.mp3"])
def test_anything_else_under_music_is_refused(music, name):
    assert music.get(f"/music/{name}").status_code == 404


def test_no_music_folder_means_an_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "MUSIC_DIR", tmp_path / "nowhere")
    assert TestClient(web_app.app).get("/api/music").json() == {"tracks": []}
