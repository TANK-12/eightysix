"""The Settings API: save, reset, wallpapers - and the theme.js it leaves behind."""

import pytest
from fastapi.testclient import TestClient

import forge_theme
import web_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    folder = tmp_path / "Wallpapers"
    folder.mkdir()
    (folder / "sea.jpg").write_bytes(b"x")
    monkeypatch.setattr(forge_theme, "CONFIG", tmp_path / "settings.json")
    monkeypatch.setattr(forge_theme, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(forge_theme, "WALLPAPER_DIR", folder)
    monkeypatch.setattr(forge_theme, "DESKTOP_WALLPAPER", tmp_path / "none.txt")
    monkeypatch.setattr(forge_theme, "_magick", lambda: None)
    monkeypatch.setattr(web_app, "HUB_DIR", tmp_path / "hub")
    return TestClient(web_app.app)


def test_saving_returns_the_theme_and_writes_it_for_the_next_launch(client, tmp_path):
    r = client.post("/api/settings", json={"gaps": 20, "wallpaper": "sea.jpg"})
    assert r.status_code == 200
    assert r.json()["settings"]["gaps"] == 20
    assert r.json()["theme"]["wallpaper_name"] == "sea.jpg"
    assert '"gaps": 20' in (tmp_path / "hub" / "theme.js").read_text()


def test_reset_puts_every_default_back(client):
    client.post("/api/settings", json={"radius": 3, "animations": False})
    settings = client.post("/api/settings/reset").json()["settings"]
    assert settings["radius"] == forge_theme.SETTINGS["radius"]["default"]
    assert settings["animations"] is True


def test_the_wallpaper_folder_is_listed(client):
    names = [w["name"] for w in client.get("/api/wallpapers").json()["wallpapers"]]
    assert names == ["sea.jpg"]


def test_a_thumbnail_is_only_served_for_a_real_wallpaper(client):
    assert client.get("/api/wallpapers/sea.jpg/thumb").status_code == 200
    assert (
        client.get("/api/wallpapers/..%2F..%2Fsettings.json/thumb").status_code == 404
    )
    assert client.get("/api/wallpapers/missing.jpg/thumb").status_code == 404


def test_favourites_from_the_wallpapers_app_are_listed_if_they_exist(
    client, tmp_path, monkeypatch
):
    import forge_wallpapers

    monkeypatch.setattr(forge_theme, "CONFIG", tmp_path / "config" / "settings.json")
    forge_wallpapers.set_favourite("sea.jpg", True)
    forge_wallpapers.set_favourite("gone.jpg", True)
    assert client.get("/api/favourites").json() == {"favourites": ["sea.jpg"]}


def test_a_wallpaper_in_a_sub_folder_has_a_thumbnail(client, tmp_path):
    (tmp_path / "Wallpapers" / "anime").mkdir()
    (tmp_path / "Wallpapers" / "anime" / "moon.png").write_bytes(b"x")
    assert client.get("/api/wallpapers/anime/moon.png/thumb").status_code == 200


def test_the_page_and_the_shared_kit_are_served(client):
    assert "Settings" in client.get("/").text
    assert client.get("/shared/forge_chrome.js").status_code == 200
