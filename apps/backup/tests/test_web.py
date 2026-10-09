"""The HTTP layer: the guard, error kinds the page relies on, and a few routes."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import web_app  # noqa: E402
from test_browse import STAMP2, drive  # noqa: E402,F401

H = {"X-Forge": "1"}


@pytest.fixture
def client(drive, monkeypatch):  # noqa: F811
    monkeypatch.setattr(web_app, "cfg", lambda: drive["cfg"])
    return TestClient(web_app.app, base_url="http://127.0.0.1:8468")


def test_guard(client):
    assert client.get("/api/status").status_code == 403
    bad_host = client.get("/api/status", headers=H | {"Host": "evil.example:8468"})
    assert bad_host.status_code == 403
    assert client.get("/api/status", headers=H).status_code == 200


def test_page_and_shared_kit_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "Backup" in page.text
    assert client.get("/shared/forge.css").status_code == 200


def test_no_drive_kind(client, monkeypatch, tmp_path):
    empty = tmp_path / "none"
    empty.mkdir()
    monkeypatch.setenv("BACKUP_DRIVE_DIR", str(empty))
    for url in ("/api/repos", "/api/snap/sets?area=vault"):
        res = client.get(url, headers=H)
        assert res.status_code == 503 and res.json()["kind"] == "no_drive"
    st = client.get("/api/status", headers=H).json()
    assert st["plugged"] is False and "not plugged in" in st["message"]


def test_routes(client):
    sets = client.get("/api/snap/sets?area=vault", headers=H).json()
    assert sets["sets"][0]["name"] == "forge"
    q = f"area=vault&set=forge&snap={STAMP2}"
    listing = client.get(f"/api/snap/list?{q}&path=Forge", headers=H).json()
    assert "app" in [e["name"] for e in listing["entries"]]
    raw = client.get(f"/api/snap/raw?{q}&path=Forge/pic.png", headers=H)
    assert raw.headers["content-type"] == "image/png"
    bad = client.get(f"/api/snap/list?{q}&path=../..", headers=H)
    assert bad.status_code == 400 and bad.json()["kind"] == "bad_input"
    repos = client.get("/api/repos", headers=H).json()["repos"]
    assert repos[0]["label"] == "repo"
    tree = client.get("/api/repos/repo.git/tree", headers=H).json()
    assert tree["readme"] == "README.md"
    log = client.get("/api/repos/repo.git/log?rev=side", headers=H).json()
    sha = log["commits"][0]["sha"]
    assert (
        client.get(f"/api/repos/repo.git/commit/{sha}", headers=H).json()["sha"] == sha
    )
    assert client.get("/api/repos/nope.git/log", headers=H).status_code == 404
    started = client.post("/api/backup", json={"area": "rescue"}, headers=H).json()
    assert started["unit"] == "forge-backup-now@rescue.service"
    assert "RESTORE" in client.get("/api/help", headers=H).json()


@pytest.mark.skipif(web_app.os.geteuid() == 0, reason="root reads everything")
def test_needs_admin_kind(client):
    q = f"area=rescue&set=system&snap={STAMP2}"
    res = client.get(f"/api/snap/list?{q}&path=root/secret", headers=H)
    assert res.status_code == 403 and res.json()["kind"] == "needs_admin"
