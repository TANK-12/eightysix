import json

import pytest
from fastapi.testclient import TestClient

import art
import web_app


@pytest.fixture
def client(tree, monkeypatch):
    monkeypatch.setenv("CREWROOM_CLAUDE_DIR", str(tree["claude"]))
    monkeypatch.setenv("CREWROOM_PROC_DIR", str(tree["proc"]))
    monkeypatch.setenv("FORGE_ART_DIR", str(tree["tmp"] / "art"))
    seed = tree["tmp"] / "seed"
    (seed / "packs" / "crewroom" / "rooms").mkdir(parents=True)
    (seed / "palettes").mkdir()
    (seed / "packs" / "crewroom" / "rooms" / "office.json").write_text(
        json.dumps({"id": "office", "label": "Office", "order": 1})
    )
    (seed / "palettes" / "crewroom.json").write_text(
        json.dumps({"id": "crewroom", "colors": {"a": "#000000"}})
    )
    (seed / "packs" / "crewroom-props.json").write_text(
        json.dumps({"id": "crewroom-props", "sprites": {}})
    )
    monkeypatch.setattr(art, "SEED_DIR", str(seed))
    with TestClient(web_app.app) as c:
        yield c


def test_room_endpoint_merges_sources_without_paths(client):
    data = client.get("/api/room").json()
    assert data["errors"] == {}
    assert data["sessions"][0]["name"] == "forge-builder"
    assert "transcript" not in data["sessions"][0]
    assert data["helpers"][0]["type"] == "crew-worker"
    assert data["crews"][0]["name"] == "forge"
    assert data["jan"]["models"][0]["short"] == "Qwen3.5 9B"


def test_rooms_are_seeded_and_listed(client, tree):
    rooms = client.get("/api/rooms").json()["rooms"]
    assert rooms == [{"id": "office", "label": "Office", "order": 1}]
    assert client.get("/api/rooms/office").json()["label"] == "Office"
    assert client.get("/api/rooms/nope").status_code == 404
    lib = client.get("/api/art/library").json()
    assert set(lib["palettes"]) == {"crewroom"}
    assert set(lib["packs"]) == {"crewroom-props"}


def test_seeding_never_overwrites_edits(tree, monkeypatch):
    monkeypatch.setenv("FORGE_ART_DIR", str(tree["tmp"] / "art2"))
    seed = tree["tmp"] / "seed2"
    (seed / "palettes").mkdir(parents=True)
    (seed / "palettes" / "crewroom.json").write_text('{"id": "crewroom"}')
    assert art.ensure_seeded(str(seed)) == ["palettes/crewroom.json"]
    target = tree["tmp"] / "art2" / "palettes" / "crewroom.json"
    target.write_text('{"id": "crewroom", "edited": true}')
    assert art.ensure_seeded(str(seed)) == []
    assert json.loads(target.read_text())["edited"] is True
