"""The HTTP side: discovery, curio file serving, the X-Forge rule, keepsakes."""

import json
import textwrap

import pytest
from fastapi.testclient import TestClient

import registry
import store
import web_app

W = {"X-Forge": "1"}


@pytest.fixture
def client():
    return TestClient(web_app.app)


def make_curio(root, cid, server=None, **meta):
    folder = root / cid
    folder.mkdir(parents=True)
    (folder / "curio.json").write_text(json.dumps({"name": cid.title(), **meta}))
    (folder / "curio.js").write_text(
        "export default { mount() { return {unmount() {}}; } };"
    )
    if server is not None:
        (folder / "server.py").write_text(textwrap.dedent(server))
    return folder


def test_discovery_skips_kit_and_reports_broken(tmp_path):
    root = tmp_path / "curios"
    make_curio(root, "beta", order=2)
    make_curio(root, "alpha", order=1)
    (root / "_kit").mkdir()
    (root / "Bad_Name").mkdir()
    (root / "nojson").mkdir()
    noentry = root / "noentry"
    noentry.mkdir()
    (noentry / "curio.json").write_text(
        json.dumps({"name": "x", "entry": "../web_app.py"})
    )
    metas, problems = registry.discover(root)
    assert [m["id"] for m in metas] == ["alpha", "beta"]
    assert len(problems) == 3


def test_a_broken_server_is_reported_not_fatal(tmp_path):
    root = tmp_path / "curios"
    make_curio(root, "boom", server="raise RuntimeError('nope')\n")
    make_curio(
        root,
        "fine",
        server="""
        from fastapi import APIRouter
        router = APIRouter()
        COMMANDS = {}
        """,
    )
    metas, _ = registry.discover(root)
    modules, problems = registry.load_servers(metas, root)
    assert list(modules) == ["fine"] and "boom" in problems[0]
    assert next(m for m in metas if m["id"] == "boom")["server_error"]


def test_real_shelf_lists_curios(client):
    res = client.get("/api/curios")
    assert res.status_code == 200
    body = res.json()
    assert body["problems"] == []
    for row in body["curios"]:
        assert row["id"] and row["name"] and row["entry"].endswith("js")


def test_curio_files_are_served_with_a_whitelist(client):
    assert client.get("/curios/_kit/rng.js").status_code == 200
    assert "javascript" in client.get("/curios/_kit/ui.js").headers["content-type"]
    for bad in (
        "/curios/_kit/../store.py",
        "/curios/_kit/%2e%2e/store.py",
        "/curios/nope/curio.js",
        "/curios/_kit/.hidden.js",
        "/curios/_kit/missing.js",
    ):
        assert client.get(bad).status_code == 404, bad


def test_python_files_are_never_served(client, monkeypatch, tmp_path):
    root = tmp_path / "curios"
    make_curio(root, "demo", server="router = None\n")
    (root / "demo" / "tests").mkdir()
    (root / "demo" / "tests" / "t.test.mjs").write_text("x")
    monkeypatch.setattr(store, "CURIOS_DIR", root)
    monkeypatch.setattr(web_app, "CURIOS", [{"id": "demo"}])
    assert client.get("/curios/demo/curio.js").status_code == 200
    assert client.get("/curios/demo/server.py").status_code == 404
    assert client.get("/curios/demo/tests/t.test.mjs").status_code == 404


def test_writes_need_the_forge_header(client):
    body = {"curio": "x", "name": "y"}
    assert client.post("/api/keepsakes", json=body).status_code == 403
    assert (
        client.post("/api/logbook", json={"title": "t", "body": "b"}).status_code == 403
    )
    big = {"Content-Length": str(web_app.MAX_BODY + 1), **W}
    assert client.post("/api/logbook", content=b"{}", headers=big).status_code == 413


def test_keep_list_edit_put_away(client, monkeypatch, tmp_path):
    root = tmp_path / "curios"
    make_curio(root, "demo")
    monkeypatch.setattr(store, "CURIOS_DIR", root)
    monkeypatch.setattr(web_app, "CURIOS", registry.discover(root)[0])
    res = client.post(
        "/api/keepsakes",
        json={"curio": "demo", "name": "Spark", "note": "n", "data": {"a": [1, 2]}},
        headers=W,
    )
    assert res.status_code == 201 and res.json()["author"] == "Emerson"
    assert (
        client.post(
            "/api/keepsakes", json={"curio": "ghost", "name": "x"}, headers=W
        ).status_code
        == 404
    )
    rows = client.get("/api/keepsakes?curio=demo").json()["keepsakes"]
    assert [r["slug"] for r in rows] == ["spark"]
    assert client.get("/api/keepsakes/demo/spark").json()["data"] == {"a": [1, 2]}
    edited = client.post(
        "/api/keepsakes/demo/spark", json={"name": "Big spark"}, headers=W
    )
    assert edited.json()["name"] == "Big spark"
    assert client.get("/api/curios").json()["curios"][0]["keepsakes"] == 1
    assert client.post("/api/keepsakes/demo/spark/put-away", headers=W).json() == {
        "ok": True
    }
    assert client.get("/api/keepsakes/demo/spark").status_code == 404
    assert client.get("/api/keepsakes/demo/spark/thumb").status_code == 404


def test_logbook_round_trip(client):
    res = client.post("/api/logbook", json={"title": "Note", "body": "Hi."}, headers=W)
    assert res.status_code == 201 and res.json()["author"] == "Emerson"
    titles = [p["title"] for p in client.get("/api/logbook").json()["pages"]]
    assert "Note" in titles
    bad = client.post("/api/logbook", json={"title": "", "body": "x"}, headers=W)
    assert bad.status_code == 400


def test_index_and_shared(client):
    res = client.get("/")
    assert res.status_code == 200 and "Afterglow" in res.text
    assert res.headers["cache-control"] == "no-cache"
    assert client.get("/shared/forge_chrome.js").status_code == 200
