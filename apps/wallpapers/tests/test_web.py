"""The Wallpapers API: listing, favourites, previews and setting a wallpaper."""

import time

import pytest
from fastapi.testclient import TestClient

import forge_theme
import forge_wallpapers as fw
import web_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    folder = tmp_path / "Wallpapers"
    (folder / "anime").mkdir(parents=True)
    (folder / "sea.jpg").write_bytes(b"x")
    (folder / "anime" / "moon.png").write_bytes(b"y")
    (tmp_path / "secret.jpg").write_bytes(b"z")
    monkeypatch.setattr(forge_theme, "CONFIG", tmp_path / "config" / "settings.json")
    monkeypatch.setattr(forge_theme, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(forge_theme, "WALLPAPER_DIR", folder)
    monkeypatch.setattr(forge_theme, "DESKTOP_WALLPAPER", tmp_path / "desktop.txt")
    monkeypatch.setattr(forge_theme, "_magick", lambda: None)
    monkeypatch.setattr(web_app, "HUB_DIR", tmp_path / "hub")
    # No lifespan: TestClient without `with` does not start the index thread.
    return TestClient(web_app.app)


def test_the_collection_is_listed_with_sub_folders(client):
    body = client.get("/api/wallpapers").json()
    names = [w["name"] for w in body["wallpapers"]]
    assert names == ["anime/moon.png", "sea.jpg"]
    first = body["wallpapers"][0]
    assert first["favourite"] is False and first["duplicate_of"] is None
    assert body["index"]["stale"] == 2


def test_reindexing_fills_in_the_index(client, monkeypatch):
    monkeypatch.setattr(
        fw, "probe", lambda source: {"width": 8, "height": 4, "hash": "0" * 64}
    )
    assert client.post("/api/reindex").json()["started"] is True
    deadline = time.time() + 5
    while web_app.index_state["running"] and time.time() < deadline:
        time.sleep(0.02)
    body = client.get("/api/wallpapers").json()
    assert body["index"]["stale"] == 0 and body["index"]["done"] == 2
    # Both are the same 8x4 picture: one is shown, one stands aside.
    marked = [w["duplicate_of"] for w in body["wallpapers"]]
    assert marked.count(None) == 1


def test_a_favourite_is_kept_and_only_for_a_real_wallpaper(client):
    r = client.post("/api/favourite", json={"name": "anime/moon.png", "on": True})
    assert r.json()["favourites"] == ["anime/moon.png"]
    listed = {
        w["name"]: w["favourite"]
        for w in client.get("/api/wallpapers").json()["wallpapers"]
    }
    assert listed == {"anime/moon.png": True, "sea.jpg": False}
    assert (
        client.post("/api/favourite", json={"name": "../secret.jpg"}).status_code == 404
    )


def test_pictures_are_only_served_from_the_collection(client):
    assert client.get("/api/thumb", params={"name": "sea.jpg"}).status_code == 200
    assert (
        client.get("/api/preview", params={"name": "anime/moon.png"}).status_code == 200
    )
    assert client.get("/api/thumb", params={"name": "../secret.jpg"}).status_code == 404
    assert client.get("/api/preview", params={"name": "missing.jpg"}).status_code == 404


def test_setting_forge_saves_it_and_hands_back_the_theme(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        fw, "set_desktop", lambda source: pytest.fail("desktop not asked")
    )
    body = client.post(
        "/api/apply", json={"name": "anime/moon.png", "forge": True}
    ).json()
    assert body["forge"]["ok"] and body["desktop"] is None
    assert body["theme"]["wallpaper_name"] == "moon.png"
    assert forge_theme.load()["wallpaper"] == "anime/moon.png"
    assert "moon" in (tmp_path / "hub" / "theme.js").read_text()
    assert client.get("/api/wallpapers").json()["forge"] == "anime/moon.png"


def test_setting_the_desktop_leaves_forge_alone_when_forge_has_its_own(
    client, monkeypatch
):
    forge_theme.save({"wallpaper": "sea.jpg"})
    asked = []
    monkeypatch.setattr(
        fw, "set_desktop", lambda source: (asked.append(source.name), (True, "set"))[1]
    )
    body = client.post(
        "/api/apply", json={"name": "anime/moon.png", "desktop": True}
    ).json()
    assert asked == ["moon.png"] and body["desktop"] == {"ok": True, "message": "set"}
    assert body["theme"] is None and forge_theme.load()["wallpaper"] == "sea.jpg"


def test_both_at_once_and_a_desktop_failure_is_reported(client, monkeypatch):
    monkeypatch.setattr(fw, "set_desktop", lambda source: (False, "no tool"))
    body = client.post(
        "/api/apply", json={"name": "sea.jpg", "desktop": True, "forge": True}
    ).json()
    assert body["desktop"] == {"ok": False, "message": "no tool"}
    assert body["forge"]["ok"] and body["theme"]["wallpaper_name"] == "sea.jpg"


def test_apply_needs_a_target_and_a_real_name(client):
    assert client.post("/api/apply", json={"name": "sea.jpg"}).status_code == 400
    assert (
        client.post(
            "/api/apply", json={"name": "../secret.jpg", "forge": True}
        ).status_code
        == 404
    )


def test_the_page_and_the_shared_kit_are_served(client):
    assert "Wallpapers" in client.get("/").text
    assert client.get("/shared/forge_chrome.js").status_code == 200


def test_particles_on_the_desktop_switch_saves_and_reaches_theme_js(client, tmp_path):
    # B38: the GNOME extension watches settings.json, desktop/particles.py
    # watches hub/theme.js, so the switch must write both
    assert client.get("/api/desktop-particles").json() == {"on": False}
    body = client.post("/api/desktop-particles", json={"on": True}).json()
    assert body["on"] is True and body["theme"]["desktop_particles"] is True
    assert forge_theme.load()["desktop_particles"] is True
    assert '"desktop_particles": true' in (tmp_path / "hub" / "theme.js").read_text()
    assert client.get("/api/desktop-particles").json() == {"on": True}
    assert (
        client.post("/api/desktop-particles", json={"on": False}).json()["on"] is False
    )


def test_a_wallpaper_gets_its_own_particles(client, tmp_path, monkeypatch):
    monkeypatch.setattr(forge_theme, "AMBIENCE_FILE", tmp_path / "ambience.json")
    body = client.get("/api/particles").json()
    assert (
        "glitter" in body["kinds"]
        and "off" in body["kinds"]
        and "auto" not in body["kinds"]
    )
    assert body["picks"] == {}
    r = client.post(
        "/api/particles", json={"name": "anime/moon.png", "kind": "lanterns"}
    )
    assert r.status_code == 200 and r.json()["picks"] == {"moon.png": "lanterns"}
    assert r.json()["theme"] is None  # not Forge's wallpaper
    client.post("/api/apply", json={"name": "anime/moon.png", "forge": True})
    r = client.post("/api/particles", json={"name": "anime/moon.png", "kind": "off"})
    assert r.json()["theme"]["wallpaper_particles"] == "off"
    r = client.post("/api/particles", json={"name": "anime/moon.png", "kind": ""})
    assert r.json()["theme"]["wallpaper_particles"] == ""
    assert (
        client.post(
            "/api/particles", json={"name": "sea.jpg", "kind": "lava"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/particles", json={"name": "nope.jpg", "kind": "snow"}
        ).status_code
        == 404
    )
