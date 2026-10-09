"""The orbit puzzle API: level discovery, saved progress, sound recipes."""

import json

import pytest
from fastapi.testclient import TestClient

import web_app


@pytest.fixture
def paths(tmp_path, monkeypatch):
    levels = tmp_path / "levels"
    progress = tmp_path / "cosmos" / "puzzle-progress.json"
    content = tmp_path / "content"
    monkeypatch.setattr(web_app, "LEVEL_DIR", levels)
    monkeypatch.setattr(web_app, "PROGRESS_FILE", progress)
    monkeypatch.setenv("FORGE_CONTENT_DIR", str(content))
    return {"levels": levels, "progress": progress, "content": content}


@pytest.fixture
def client(paths):
    return TestClient(web_app.app)


def write_level(folder, lid, **fields):
    folder.mkdir(parents=True, exist_ok=True)
    data = {"name": lid, "goal": {"type": "reach", "target": "x"}} | fields
    (folder / f"{lid}.json").write_text(json.dumps(data))


# --- levels ---------------------------------------------------------------------


def test_levels_are_discovered_in_their_own_order(client, paths):
    write_level(paths["levels"], "late", order=20)
    write_level(paths["levels"], "early", order=10, caption="Aim ahead.")
    write_level(paths["levels"], "wander", order=99, goal={"type": "explore"})
    got = client.get("/api/levels").json()
    assert [r["id"] for r in got["levels"]] == ["early", "late", "wander"]
    assert got["levels"][0]["caption"] == "Aim ahead."
    assert got["levels"][2]["goal"] == "explore"
    assert got["folder"] == str(paths["levels"])


def test_broken_or_unknown_level_files_hide_themselves(client, paths):
    write_level(paths["levels"], "good")
    (paths["levels"] / "broken.json").write_text("{nope")
    write_level(paths["levels"], "odd-goal", goal={"type": "teleport"})
    write_level(paths["levels"], "Bad_Name")
    ids = [r["id"] for r in client.get("/api/levels").json()["levels"]]
    assert ids == ["good"]


def test_no_level_folder_is_an_empty_list(client):
    assert client.get("/api/levels").json()["levels"] == []


def test_a_level_loads_with_its_id_and_ids_cannot_escape(client, paths):
    write_level(paths["levels"], "first-light", bodies=[{"id": "x"}])
    got = client.get("/api/levels/first-light").json()
    assert got["id"] == "first-light" and got["bodies"] == [{"id": "x"}]
    assert client.get("/api/levels/missing").status_code == 404
    assert client.get("/api/levels/..%2F..%2Fetc%2Fpasswd").status_code == 404


# --- progress -------------------------------------------------------------------


def post(client, **result):
    return client.post("/api/puzzles/progress", json=result)


def test_progress_starts_empty(client):
    assert client.get("/api/puzzles/progress").json() == {
        "version": 1,
        "levels": {},
        "endless": {"best_difficulty": 0},
        "explore": {},
    }


def test_galaxy_discoveries_are_kept_and_merged(client, paths):
    post(client, explore="galaxy", found=["ember", "vega"], farthest=120.5, time=30)
    post(
        client,
        explore="galaxy",
        found=["vega", "core"],
        farthest=80,
        time=90,
        ended=True,
    )
    row = client.get("/api/puzzles/progress").json()["explore"]["galaxy"]
    assert row == {
        "found": ["core", "ember", "vega"],
        "farthest": 120.5,
        "longest_flight": 90,
        "probes": 1,
    }
    assert json.loads(paths["progress"].read_text())["explore"]["galaxy"] == row


@pytest.mark.parametrize(
    "bad",
    [
        {"explore": "../x", "found": []},
        {"explore": "galaxy", "found": "ember"},
        {"explore": "galaxy", "found": ["Not An Id"]},
        {"explore": "galaxy", "found": [], "farthest": -1},
    ],
)
def test_malformed_discoveries_are_refused(client, paths, bad):
    res = client.post("/api/puzzles/progress", json=bad)
    assert res.status_code == 400 and res.json()["error"]
    assert not paths["progress"].exists()


def test_progress_and_levels_are_never_cached(client, paths):
    write_level(paths["levels"], "wander", goal={"type": "explore"})
    for url in ("/api/puzzles/progress", "/api/levels", "/api/levels/wander"):
        assert client.get(url).headers["cache-control"] == "no-store", url


def test_an_explore_level_says_how_many_stars_it_holds(client, paths):
    write_level(
        paths["levels"],
        "wander",
        goal={"type": "explore"},
        bodies=[
            {"id": "a", "kind": "star"},
            {"id": "b", "kind": "blackhole"},
            {"id": "c", "kind": "planet"},
        ],
    )
    assert client.get("/api/levels").json()["levels"][0]["discoverable"] == 2


def test_progress_keeps_the_best_of_every_flight(client, paths):
    post(client, level="slingshot", won=False, stars=0, cost=9, time=40)
    row = client.get("/api/puzzles/progress").json()["levels"]["slingshot"]
    assert row == {"plays": 1, "stars": 0}

    post(client, level="slingshot", won=True, stars=3, cost=5.5, time=30)
    post(client, level="slingshot", won=True, stars=1, cost=7.0, time=20)
    row = json.loads(paths["progress"].read_text())["levels"]["slingshot"]
    assert row == {
        "plays": 3,
        "wins": 2,
        "stars": 3,
        "best_cost": 5.5,
        "best_time": 20,
    }


def test_endless_keeps_the_highest_difficulty(client):
    post(client, endless_difficulty=4)
    post(client, endless_difficulty=2)
    assert client.get("/api/puzzles/progress").json()["endless"] == {
        "best_difficulty": 4
    }


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"level": "../x", "won": True, "stars": 1},
        {"level": "a", "won": True, "stars": 4},
        {"level": "a", "won": True, "stars": "3"},
        {"level": "a", "won": True, "stars": True},
        {"level": "a", "stars": 1},
        {"level": "a", "won": True, "stars": 1, "cost": -1},
        {"level": "a", "won": True, "stars": 1, "time": "soon"},
        {"endless_difficulty": 0},
    ],
)
def test_malformed_results_are_refused_and_nothing_is_written(client, paths, bad):
    res = client.post("/api/puzzles/progress", json=bad)
    assert res.status_code == 400 and res.json()["error"]
    assert not paths["progress"].exists()


def test_an_unreadable_progress_file_is_kept_aside_not_overwritten(client, paths):
    paths["progress"].parent.mkdir(parents=True)
    paths["progress"].write_text("{half a file")
    post(client, level="a", won=True, stars=2, cost=1, time=1)
    kept = paths["progress"].with_name("puzzle-progress.json.broken")
    assert kept.read_text() == "{half a file"
    assert json.loads(paths["progress"].read_text())["levels"]["a"]["stars"] == 2


# --- sounds ---------------------------------------------------------------------


def test_only_cosmos_sounds_are_served_and_broken_ones_are_named(client, paths):
    folder = paths["content"] / "sounds"
    folder.mkdir(parents=True)
    (folder / "cosmos-launch.json").write_text(
        json.dumps({"label": "Launch", "event": "launch", "freq": 180})
    )
    (folder / "emberfield-hit.json").write_text(
        json.dumps({"label": "Hit", "event": "hit"})
    )
    (folder / "cosmos-broken.json").write_text(json.dumps({"label": "No event"}))
    got = client.get("/api/sounds").json()
    assert [s["id"] for s in got["sounds"]] == ["cosmos-launch"]
    assert got["sounds"][0]["freq"] == 180 and got["sounds"][0]["wave"] == "triangle"
    assert any("cosmos-broken" in p for p in got["problems"])
