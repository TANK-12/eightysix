"""U1 sweep (2026-10-08): reading a project or series that is not there is a
404 and creates nothing; names too long for a folder are a 400, not a 500.
Self-contained (its own fixture) so it runs with or without conftest.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novelforge import project as projectmod  # noqa: E402


@pytest.fixture
def u1_client(tmp_path, monkeypatch):
    for key in ("PROJECTS_DIR", "SERIES_DIR", "TRASH_DIR"):
        d = tmp_path / key.lower()
        d.mkdir()
        # TRASH_DIR only exists in newer versions of project.py.
        monkeypatch.setattr(projectmod, key, str(d), raising=False)
    monkeypatch.setenv("FORGE_JAN_SETTINGS_DIR", str(tmp_path / "jan"))
    import web_app

    return TestClient(web_app.app), tmp_path


def test_reading_an_unknown_project_creates_nothing(u1_client):
    client, tmp = u1_client
    assert client.get("/api/projects/nope").status_code == 404
    assert os.listdir(tmp / "projects_dir") == []
    r = client.post("/api/projects", json={"name": "Real Book"})
    assert r.status_code == 200
    slug = r.json()["name"]
    assert client.get(f"/api/projects/{slug}").status_code == 200
    # The display name still finds it, as before.
    assert client.get("/api/projects/Real Book").status_code == 200


def test_reading_an_unknown_series_creates_nothing(u1_client):
    client, tmp = u1_client
    assert client.get("/api/series/nope").status_code == 404
    assert os.listdir(tmp / "series_dir") == []
    assert client.post("/api/series", json={"name": "Saga"}).status_code == 200
    assert client.get("/api/series/Saga").status_code == 200


def test_empty_and_overlong_names_are_refused(u1_client):
    client, tmp = u1_client
    assert client.post("/api/series", json={"name": "  "}).status_code == 400
    long_name = "a" * 5000
    r = client.post("/api/projects", json={"name": long_name})
    assert r.status_code == 400 and "too long" in r.json()["detail"]
    assert client.post("/api/series", json={"name": long_name}).status_code == 400
    assert client.post("/api/projects", json={"name": "b" * 120}).status_code == 200
    assert client.post("/api/projects", json={"name": "漫画 ünï 📖"}).status_code == 200
    assert os.listdir(tmp / "series_dir") == []


def test_dot_names_stay_inside_the_data_folders(u1_client):
    # Critic (2026-10-08): "." and ".." named the projects folder itself or
    # its parent, so reads passed the 404 guard and writes landed outside.
    client, tmp = u1_client
    for raw in ("%2E", "%2E%2E"):
        assert client.get(f"/api/projects/{raw}").status_code == 404
        assert client.get(f"/api/series/{raw}").status_code == 404
    assert projectmod.slugify("..") == "untitled"
    assert projectmod.slugify(".hidden.book") == "hidden.book"
    for name in (".", ".."):
        r = client.post("/api/projects", json={"name": name})
        assert r.status_code == 200 and r.json()["name"] == "untitled"
    for stray in ("bible.json", "state.json", "chapters"):
        assert not (tmp / stray).exists()
        assert not (tmp / "projects_dir" / stray).exists()
    assert os.listdir(tmp / "projects_dir") == ["untitled"]


def test_name_length_counts_bytes(u1_client):
    # 100 CJK characters pass a 120-character check but are 300 bytes,
    # over the 255-byte folder-name limit: a 400, not a 500.
    client, tmp = u1_client
    for route in ("/api/projects", "/api/series"):
        r = client.post(route, json={"name": "漫" * 100})
        assert r.status_code == 400 and "too long" in r.json()["detail"]
    assert client.post("/api/projects", json={"name": "漫" * 60}).status_code == 200
