"""The HTTP surface, run against a temporary data folder.

The backend is small, but it owns the two things a bad request could break
for good: the settings file and the save slots.
"""

import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(APP, "..", "..", "shared"))

from emberfield import config  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "EmberfieldData"
    monkeypatch.setattr(config, "DATA_ROOT", str(root))
    monkeypatch.setattr(config, "SAVES_DIR", str(root / "saves"))
    monkeypatch.setattr(config, "VOICE_CACHE", str(root / "voice_cache"))
    monkeypatch.setattr(config, "SETTINGS_PATH", str(root / "settings.json"))
    sys.modules.pop("web_app", None)
    web_app = importlib.import_module("web_app")
    yield TestClient(web_app.app)
    sys.modules.pop("web_app", None)


def test_a_wrong_type_in_settings_is_refused_and_the_game_still_boots(client):
    bad = client.post("/api/settings", json={"values": {"heavy_cores": "abc"}})
    assert bad.status_code == 422
    assert "heavy_cores" in bad.json()["detail"]
    assert client.get("/api/capabilities").status_code == 200
    assert client.get("/api/settings").json()["heavy_cores"] == 6


def test_settings_numbers_are_clamped_and_switches_must_be_switches(client):
    r = client.post(
        "/api/settings",
        json={"values": {"heavy_cores": 0, "day_seconds": 1, "volume": 900}},
    )
    assert r.status_code == 200
    got = r.json()
    assert (got["heavy_cores"], got["day_seconds"], got["volume"]) == (1, 60, 100)
    assert (
        client.post("/api/settings", json={"values": {"zoom": 1e300}}).json()["zoom"]
        == 5
    )
    assert (
        client.post("/api/settings", json={"values": {"shadows": 1}}).status_code == 422
    )
    assert (
        client.post("/api/settings", json={"values": {"zoom": True}}).status_code == 422
    )
    nested = client.post("/api/settings", json={"values": {"new_dial": {"a": 1}}})
    assert nested.status_code == 422
    huge = client.post("/api/settings", json={"values": {"big": "x" * 200000}})
    assert huge.status_code == 422
    assert "big" not in client.get("/api/settings").json()


def test_a_refused_patch_changes_nothing(client):
    before = client.get("/api/settings").json()
    r = client.post("/api/settings", json={"values": {"volume": 10, "llm_mode": ["x"]}})
    assert r.status_code == 422
    assert client.get("/api/settings").json() == before


def test_a_poisoned_settings_file_heals_on_load(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text('{"heavy_cores": "abc", "volume": 40, "zoom": null}')
    monkeypatch.setattr(config, "SETTINGS_PATH", str(path))
    data = config.load_settings()
    assert data["heavy_cores"] == 6
    assert data["volume"] == 40
    assert data["zoom"] == 3


def test_the_settings_the_page_sends_are_accepted(client):
    values = {
        "llm_mode": "off",
        "voice_mode": "off",
        "palette": "emberfield-summer",
        "zoom": 4,
        "shadows": False,
        "volume": 55,
        "day_seconds": 600,
        "heavy_cores": 4,
    }
    r = client.post("/api/settings", json={"values": values})
    assert r.status_code == 200
    assert {k: r.json()[k] for k in values} == values


def test_save_slots_round_trip_and_stay_inside_the_saves_folder(client):
    payload = {"name": "Ëmber 🔥", "day": 3, "world": {"seed": 7}}
    assert client.post("/api/saves/../../evil", json=payload).status_code in (
        200,
        404,
        405,
    )
    assert client.post("/api/saves/valley-7", json=payload).json()["saved"]
    assert client.get("/api/saves/valley-7").json()["name"] == "Ëmber 🔥"
    for name in os.listdir(config.SAVES_DIR):
        assert name.endswith(".json")
    assert not os.path.exists(os.path.join(config.DATA_ROOT, "..", "evil.json"))
    assert client.get("/api/saves/missing").status_code == 404
    assert client.post("/api/saves/x", json=[1, 2]).status_code == 422


def test_files_are_revalidated_rather_than_kept_by_guesswork(client):
    for path in ("/", "/ui.js", "/api/settings"):
        assert client.get(path).headers["cache-control"] == "no-cache"
