"""The Cosmos API: discovery of modes and bodies, the star catalog, scenarios."""

import gzip
import json

import pytest
from fastapi.testclient import TestClient

import build_star_catalog as bsc
import web_app


@pytest.fixture
def paths(tmp_path, monkeypatch):
    an3 = tmp_path / "an3"
    cache = tmp_path / "cache"
    monkeypatch.setattr(web_app, "CATALOG_SOURCES", [("an3", an3), ("cache", cache)])
    monkeypatch.setattr(web_app, "SCENARIO_DIR", tmp_path / "scenarios")
    return {"an3": an3, "cache": cache, "scenarios": tmp_path / "scenarios"}


@pytest.fixture
def client(paths):
    return TestClient(web_app.app)


def build_tiny_catalog(folder, tmp_path, n=2):
    src = tmp_path / f"tiny-{folder.name}.csv.gz"
    with gzip.open(src, "wt") as fh:
        fh.write("id,proper,dist,mag,absmag,ci,x,y,z,con\n")
        for i in range(1, n + 1):
            fh.write(f"{i},Star {i},{i},{i},{i},0.5,{i},0,0,Ori\n")
    bsc.build(src, folder)


# --- discovery ----------------------------------------------------------------


def test_modes_are_discovered_from_folders(client, tmp_path, monkeypatch):
    modes = tmp_path / "modes"
    for mid, order in (("zeta", 5), ("alpha", 50)):
        (modes / mid).mkdir(parents=True)
        (modes / mid / "mode.json").write_text(
            json.dumps({"name": mid, "order": order})
        )
    (modes / "half-built").mkdir()  # no mode.json: not a mode yet
    (modes / "broken").mkdir()
    (modes / "broken" / "mode.json").write_text("{not json")
    monkeypatch.setattr(web_app, "MODES_DIR", modes)

    got = client.get("/api/modes").json()["modes"]
    assert [m["id"] for m in got] == ["zeta", "alpha"]
    assert got[0]["entry"] == "mode.js"


def test_the_shipped_modes_include_the_map_and_the_sandbox(client):
    ids = [m["id"] for m in client.get("/api/modes").json()["modes"]]
    assert {"map", "sandbox"} <= set(ids)


def test_bodies_form_one_tree_rooted_at_the_sun(client):
    bodies = client.get("/api/bodies").json()["bodies"]
    by_id = {b["id"]: b for b in bodies}
    assert bodies[0]["id"] == "sun"
    assert {"earth", "moon", "jupiter", "titan", "pluto", "eris"} <= set(by_id)
    for b in bodies[1:]:
        assert b["parent"] in by_id, b["id"]
        assert b["elements"]["model"] in {"standish", "kepler"}
        if b["elements"].get("frame") == "parent_equator":
            assert "pole" in by_id[b["parent"]], b["id"]
    orders = [b["order"] for b in bodies]
    assert orders == sorted(orders)


# --- the star catalog -----------------------------------------------------------


def test_no_catalog_is_reported_plainly(client):
    status = client.get("/api/catalog").json()
    assert status["available"] is False and status["source"] is None
    assert "CC BY-SA" in status["credit"]
    assert client.get("/api/stars").status_code == 404
    assert client.get("/api/star-names").status_code == 404


def test_the_cache_copy_is_used_when_the_drive_is_out(client, paths, tmp_path):
    build_tiny_catalog(paths["cache"], tmp_path, n=3)
    status = client.get("/api/catalog").json()
    assert status["available"] is True
    assert status["source"] == "cache" and status["count"] == 3
    stars = client.get("/api/stars")
    assert stars.status_code == 200 and stars.content[:4] == b"CSTR"
    assert len(client.get("/api/star-names").json()["stars"]) == 3


def test_the_drive_wins_when_both_are_there(client, paths, tmp_path):
    build_tiny_catalog(paths["cache"], tmp_path, n=3)
    build_tiny_catalog(paths["an3"], tmp_path, n=5)
    status = client.get("/api/catalog").json()
    assert status["source"] == "an3" and status["count"] == 5


# --- scenarios ------------------------------------------------------------------


def scenario(**overrides):
    base = {
        "name": "My Test World",
        "G": 1,
        "softening": 0.1,
        "bodies": [{"name": "Sun", "kind": "star", "m": 100, "r": 5, "x": 0, "y": 0}],
        "particles": [[1, 2, 3, 4, 0]],
    }
    return base | overrides


def test_a_saved_scenario_is_listed_and_can_be_loaded(client, paths):
    saved = client.post("/api/scenarios", json=scenario()).json()
    assert saved["id"] == "my-test-world"
    rows = client.get("/api/scenarios").json()["scenarios"]
    assert [r["id"] for r in rows] == ["my-test-world"]
    assert (
        rows[0]["saved"] is True
        and rows[0]["bodies"] == 1
        and rows[0]["particles"] == 1
    )
    full = client.get("/api/scenarios/my-test-world").json()
    assert full["bodies"][0]["name"] == "Sun"


def test_saving_never_overwrites_an_existing_scenario(client, paths):
    paths["scenarios"].mkdir(parents=True)
    original = {"name": "My Test World", "description": "hand made"}
    (paths["scenarios"] / "my-test-world.json").write_text(json.dumps(original))
    assert (
        client.post("/api/scenarios", json=scenario()).json()["id"] == "my-test-world-2"
    )
    assert (
        client.post("/api/scenarios", json=scenario()).json()["id"] == "my-test-world-3"
    )
    kept = json.loads((paths["scenarios"] / "my-test-world.json").read_text())
    assert kept == original


def test_presets_list_before_saved_worlds_in_their_own_order(client, paths):
    paths["scenarios"].mkdir(parents=True)
    for sid, order in (("late", 20), ("early", 10)):
        (paths["scenarios"] / f"{sid}.json").write_text(
            json.dumps({"name": sid, "order": order})
        )
    client.post("/api/scenarios", json=scenario(name="Aardvark"))
    ids = [r["id"] for r in client.get("/api/scenarios").json()["scenarios"]]
    assert ids == ["early", "late", "aardvark"]


@pytest.mark.parametrize(
    "bad",
    [
        {"name": ""},
        {"bodies": [{"m": -5, "r": 1}]},
        {"bodies": [{"m": "heavy", "r": 1}]},
        {"bodies": [{"m": 1, "r": 1, "kind": "dragon"}]},
        {"particles": [[1, 2, 3]]},
        {"softening": -1},
    ],
)
def test_broken_scenarios_are_refused_with_a_reason(client, paths, bad):
    res = client.post("/api/scenarios", json=scenario(**bad))
    assert res.status_code == 400 and res.json()["error"]
    assert not paths["scenarios"].exists() or not list(paths["scenarios"].iterdir())


def test_scenario_ids_cannot_escape_the_folder(client, paths):
    assert client.get("/api/scenarios/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/api/scenarios/Not-Valid").status_code == 404
