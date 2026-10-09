"""U1 sweep (2026-10-08): bad input is a 4xx, never a 500."""

import importlib

import pytest
from fastapi.testclient import TestClient

from panelforge import paths
from panelforge.render.fixture import add_scene_layers, make_chapter


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    from panelforge import jobs as jobs_mod

    importlib.reload(paths)
    importlib.reload(jobs_mod)
    paths.ensure_roots()
    assert paths.DATA_ROOT == tmp_path  # never the real ~/PanelForgeData
    ch = make_chapter(tmp_path, n_panels=2)
    add_scene_layers(ch)
    import web_app

    importlib.reload(web_app)
    c = TestClient(web_app.app, raise_server_exceptions=False)
    c.series, c.chapter = ch.parent.parent.name, ch.name  # type: ignore[attr-defined]
    return c


@pytest.mark.parametrize(
    "method,route", [("put", "panels"), ("put", "script"), ("put", "bubbles")]
)
def test_infinity_body_is_a_422_not_a_500(client, method, route):
    url = f"/api/chapters/{client.series}/{client.chapter}/{route}"
    r = client.request(
        method.upper(),
        url,
        content=b"1e999",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail and all("input" not in d for d in detail)


def test_infinity_inside_a_job_body_starts_nothing(client):
    url = f"/api/chapters/{client.series}/{client.chapter}/render"
    r = client.post(url, content=b"1e999", headers={"Content-Type": "application/json"})
    assert r.status_code == 422, r.text
    assert client.get("/api/jobs").json()["jobs"] == []


def test_overlong_ids_are_never_a_500(client):
    # an unknown series lists no chapters (200), the rest answer 404
    long = "x" * 3000
    for url in (
        f"/api/series/{long}/chapters",
        f"/api/series/{long}/cast",
        f"/api/chapters/{long}/0001/panels",
        f"/api/chapters/{client.series}/{long}/panels",
    ):
        r = client.get(url)
        assert r.status_code in (200, 404), (url[:60], r.status_code, r.text[:200])


def test_other_disk_errors_still_surface(client, monkeypatch):
    import web_app

    def boom():
        raise PermissionError(13, "denied")

    monkeypatch.setattr(web_app.jobs, "all_jobs", boom)
    assert client.get("/api/jobs").status_code == 500


@pytest.mark.parametrize(
    "bad", [b"1e999", b"-1e999", b"NaN", b"Infinity", b"-Infinity"]
)
def test_non_finite_numbers_inside_a_body_are_refused(client, bad):
    url = f"/api/chapters/{client.series}/{client.chapter}/script"
    before = client.get(url).json()
    body = b'{"lines": [], "deep": {"x": [1, ' + bad + b"]}}"
    r = client.put(url, content=body, headers={"Content-Type": "application/json"})
    assert r.status_code == 422, r.text
    assert "finite" in r.json()["detail"]
    after = client.get(url)
    assert after.status_code == 200 and after.json() == before


def test_finite_and_non_json_bodies_still_pass(client):
    url = f"/api/chapters/{client.series}/{client.chapter}/script"
    doc = client.get(url).json()
    doc["note"] = 1.5e300
    assert client.put(url, json=doc).status_code == 200
    assert client.get(url).json()["note"] == 1.5e300
    # a route without a body ignores whatever text is sent to it
    r = client.get("/api/jobs", headers={"Content-Type": "application/json"})
    assert r.status_code == 200


@pytest.mark.parametrize("bad", ["%2e%2e", "%2e", "a%5cb"])
def test_dot_ids_never_reach_the_data_root(client, bad):
    r = client.put(f"/api/series/{bad}/words", json={"words": []})
    assert r.status_code == 404, r.text
    assert not (paths.DATA_ROOT / "glossary.json").exists()
    assert not (paths.DATA_ROOT / "series" / "glossary.json").exists()
    r = client.get(f"/api/chapters/{client.series}/{bad}/panels")
    assert r.status_code == 404, r.text
