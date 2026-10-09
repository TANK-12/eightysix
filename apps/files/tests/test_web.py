"""The HTTP layer: the X-Forge guard, errors as 400, thumbnails and range reads."""

from __future__ import annotations

import subprocess
import time
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import web_app  # noqa: E402

H = {"X-Forge": "1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FILES_ROOTS", str(tmp_path))
    monkeypatch.setattr(web_app.fsops, "OWN_THUMBS", tmp_path / ".thumbs")
    (tmp_path / "note.txt").write_text("0123456789")
    return TestClient(web_app.app), tmp_path


def test_api_needs_header_or_token(client):
    c, root = client
    assert c.get("/api/list", params={"path": str(root)}).status_code == 403
    assert (
        c.get("/api/list", params={"path": str(root), "t": "wrong"}).status_code == 403
    )
    assert c.get("/api/list", params={"path": str(root)}, headers=H).status_code == 200
    token = c.get("/api/session", headers=H).json()["token"]
    r = c.get("/api/raw", params={"path": str(root / "note.txt"), "t": token})
    assert r.status_code == 200 and r.text == "0123456789"


def test_bad_path_is_400(client):
    c, _ = client
    r = c.get("/api/list", params={"path": "/etc"}, headers=H)
    assert r.status_code == 400 and "outside" in r.json()["detail"]
    r = c.get("/api/raw", params={"path": "/etc/passwd"}, headers=H)
    assert r.status_code == 400


def test_raw_supports_range(client):
    c, root = client
    r = c.get(
        "/api/raw",
        params={"path": str(root / "note.txt")},
        headers={**H, "Range": "bytes=2-4"},
    )
    assert r.status_code == 206 and r.text == "234"


def test_post_routes(client):
    c, root = client
    r = c.post("/api/mkdir", json={"parent": str(root), "name": "Box"}, headers=H)
    assert r.status_code == 200 and (root / "Box").is_dir()
    r = c.post(
        "/api/transfer",
        json={
            "op": "copy",
            "paths": [str(root / "note.txt")],
            "dest": str(root / "Box"),
        },
        headers=H,
    )
    job = r.json()
    for _ in range(100):
        job = c.get(f"/api/jobs/{job['id']}", headers=H).json()
        if job["state"] != "running":
            break
    assert job["state"] == "done" and (root / "Box" / "note.txt").exists()
    r = c.post(
        "/api/rename", json={"path": str(root / "Box"), "name": "Crate"}, headers=H
    )
    assert r.json()["path"].endswith("Crate")


def test_thumbnail_made_by_ffmpeg(client):
    c, root = client
    img = root / "big.png"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "nullsrc=s=1200x900,geq=random(1)*255:128:128",
            "-frames:v",
            "1",
            str(img),
        ],
        check=True,
    )
    r = c.get("/api/thumb", params={"path": str(img)}, headers=H)
    assert r.status_code == 200 and r.content[:2] == b"\xff\xd8"
    assert len(r.content) < img.stat().st_size
    assert (
        c.get(
            "/api/thumb", params={"path": str(root / "note.txt")}, headers=H
        ).status_code
        == 404
    )


def test_static_page_served(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200 and "Files" in r.text


def test_archive_and_restore_routes(client):
    c, root = client
    r = c.post(
        "/api/archive",
        json={"op": "compress", "paths": [str(root / "note.txt")]},
        headers=H,
    )
    assert r.status_code == 200 and r.json()["op"] == "compress"
    job = r.json()
    for _ in range(100):
        job = c.get(f"/api/jobs/{job['id']}", headers=H).json()
        if job["state"] != "running":
            break
        time.sleep(0.05)
    assert job["state"] == "done" and job["results"] == [str(root / "note.zip")]
    assert (
        c.post("/api/archive", json={"op": "rm", "paths": []}, headers=H).status_code
        == 400
    )
    out = c.post("/api/restore", json={"paths": [str(root / "note.txt")]}, headers=H)
    assert out.status_code == 200 and out.json()["restored"] == []
