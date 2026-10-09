"""U1 sweep (2026-10-08): bad input to the sweep route is a 400 that starts
nothing, a URL slug never becomes a path outside the data folder, and Foresight
reads the same library folder Dossier was pointed at."""

import json
import time

import pytest
from fastapi.testclient import TestClient

import dossier_link
import store
import web_app


def _idle() -> dict:
    return {"running": False, "done": 0, "total": 0, "log": [], "last": ""}


@pytest.fixture
def runs(monkeypatch):
    started = []
    monkeypatch.setattr(web_app, "_sweep_state", _idle())
    monkeypatch.setattr(web_app, "_run_sweep", lambda *args: started.append(args))
    return started


@pytest.mark.parametrize(
    "body",
    [
        {"limit": "abc"},
        {"days": "x"},
        {"limit": [3]},
        {"sources": 5},
        {"sources": "pageviews"},
        {"subjects": "abc"},
        {"subjects": [5]},
        {"subjects": [{"name": "no slug"}]},
        {"subjects": [{"slug": "../../etc"}]},
        {"subjects": [{"slug": ".."}]},
    ],
)
def test_bad_sweep_input_is_a_400_and_starts_nothing(runs, body):
    response = TestClient(web_app.app, raise_server_exceptions=False).post(
        "/api/sweep", json=body
    )
    assert response.status_code == 400, response.text
    assert web_app._sweep_state["running"] is False
    time.sleep(0.05)
    assert runs == []


def test_a_good_sweep_request_still_starts(runs):
    subjects = [{"slug": "germany", "name": "Germany", "entity_type": "country"}]
    response = TestClient(web_app.app).post(
        "/api/sweep", json={"subjects": subjects, "sources": ["pageviews"], "days": 30}
    )
    assert response.status_code == 200 and response.json()["subjects"] == 1
    for _ in range(50):
        if runs:
            break
        time.sleep(0.02)
    got, days, only, history = runs[0]
    assert got == subjects and days == 30 and only == ("pageviews",) and not history


@pytest.mark.parametrize("slug", ["%2E%2E", "%2E"])
def test_a_dot_slug_is_not_found(slug):
    response = TestClient(web_app.app).get(f"/api/subject/{slug}")
    assert response.status_code == 404


def test_series_paths_refuse_a_slug_that_climbs(tmp_path):
    for bad in ("..", ".", "", "a/b", "a\\b"):
        with pytest.raises(store.BadSlug):
            store.series_path(bad, "pageviews", tmp_path)
    assert store.series_path("germany", "pageviews", tmp_path).parent.name == "germany"


def test_list_limits_are_clamped():
    client = TestClient(web_app.app)
    assert client.get("/api/watchlist?limit=-1").status_code == 200
    assert client.get("/api/findings?limit=-5").status_code == 200


def _library(folder):
    (folder / "subjects").mkdir(parents=True)
    (folder / "index.json").write_text(json.dumps([{"slug": "x", "name": "X"}]))
    return folder


def test_dossier_link_follows_the_library_dossier_was_pointed_at(tmp_path, monkeypatch):
    lib = _library(tmp_path / "moved" / "DossierData")
    choice = tmp_path / "location.json"
    choice.write_text(json.dumps({"path": str(lib)}))
    monkeypatch.setattr(dossier_link, "DOSSIER_CHOICE", choice)
    monkeypatch.setattr(dossier_link, "DOSSIER_USB", tmp_path / "nousb")
    monkeypatch.setattr(dossier_link, "DOSSIER_LOCAL", _library(tmp_path / "local"))
    assert dossier_link.root() == lib
    assert dossier_link.library() == [{"slug": "x", "name": "X"}]


def test_a_choice_that_is_not_a_library_is_ignored(tmp_path, monkeypatch):
    choice = tmp_path / "location.json"
    choice.write_text(json.dumps({"path": str(tmp_path / "gone")}))
    local = _library(tmp_path / "local")
    monkeypatch.setattr(dossier_link, "DOSSIER_CHOICE", choice)
    monkeypatch.setattr(dossier_link, "DOSSIER_USB", tmp_path / "nousb")
    monkeypatch.setattr(dossier_link, "DOSSIER_LOCAL", local)
    assert dossier_link.root() == local
    choice.write_text("not json")
    assert dossier_link.root() == local


def test_foresight_data_beside_the_chosen_library_is_used(tmp_path, monkeypatch):
    lib = _library(tmp_path / "moved" / "DossierData")
    beside = tmp_path / "moved" / "ForesightData"
    (beside / "signals").mkdir(parents=True)
    choice = tmp_path / "location.json"
    choice.write_text(json.dumps({"path": str(lib)}))
    monkeypatch.setattr(dossier_link, "DOSSIER_CHOICE", choice)
    monkeypatch.setattr(store, "USB_ROOT", tmp_path / "nousb" / "ForesightData")
    monkeypatch.setattr(store, "LOCAL_ROOT", tmp_path / "local-fs")
    monkeypatch.setattr(store, "_resolved", None)
    root = store.data_root(refresh=True)
    assert root.path == beside and not root.on_usb
    assert "beside" in root.detail


def test_without_foresight_data_beside_it_the_fallback_still_applies(
    tmp_path, monkeypatch
):
    lib = _library(tmp_path / "moved" / "DossierData")
    choice = tmp_path / "location.json"
    choice.write_text(json.dumps({"path": str(lib)}))
    monkeypatch.setattr(dossier_link, "DOSSIER_CHOICE", choice)
    monkeypatch.setattr(store, "USB_ROOT", tmp_path / "nousb" / "ForesightData")
    monkeypatch.setattr(store, "LOCAL_ROOT", tmp_path / "local-fs")
    monkeypatch.setattr(store, "_resolved", None)
    root = store.data_root(refresh=True)
    assert root.path == tmp_path / "local-fs"
    assert not (tmp_path / "moved" / "ForesightData").exists()


def test_tests_never_reach_the_real_data_folder():
    assert str(store.data_root().path).startswith(
        str(dossier_link.DOSSIER_CHOICE.parent)
    )


def test_an_overlong_slug_is_refused(runs):
    long = "x" * (store.MAX_SLUG + 1)
    with pytest.raises(store.BadSlug):
        store.check_slug(long)
    assert store.check_slug("x" * store.MAX_SLUG)
    client = TestClient(web_app.app)
    r = client.post("/api/sweep", json={"subjects": [{"slug": long}]})
    assert r.status_code == 400 and not runs
    assert (
        client.post("/api/plans", json={"slug": long, "tier": "rules"}).status_code
        == 404
    )
    assert client.post("/api/plans/learn", json={"slug": long}).status_code == 404


def test_slugify_stays_within_the_slug_limit():
    slug = store.slugify("Ada " * 100)
    assert store.check_slug(slug) == slug and store.slugify(slug) == slug
