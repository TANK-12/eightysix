"""Human names on conversations (Emerson, 2026-09-27: tabs should read like people)."""

import json

import names
import runner
import web_app
from fastapi.testclient import TestClient

FORGE = {"X-Forge": "1"}


def test_pick_is_stable_and_skips_names_in_use():
    first = names.pick("abc123abc123")
    assert first == names.pick("abc123abc123") and first in names.NAMES
    second = names.pick("abc123abc123", taken=[first.lower()])
    assert second != first and second in names.NAMES


def test_names_repeat_only_when_the_list_is_used_up():
    taken = list(names.NAMES)
    assert names.pick("abc123abc123", taken) == names.pick("abc123abc123")


def test_clean_keeps_one_short_line():
    assert names.clean("  Hana \n  chan ") == "Hana chan"
    assert len(names.clean("x" * 99)) == 32


def test_new_conversations_get_different_names(tmp_path):
    reg = runner.Registry(tmp_path / "data")
    made = [reg.create().meta["name"] for _ in range(10)]
    assert len(set(made)) == 10 and all(n in names.NAMES for n in made)


def test_old_conversations_are_named_once_and_it_sticks(tmp_path):
    folder = tmp_path / "data" / "conversations"
    folder.mkdir(parents=True)
    old = {"id": "0123456789ab", "title": "fix the thing", "updated": 1}
    (folder / "0123456789ab.json").write_text(json.dumps(old))
    reg = runner.Registry(tmp_path / "data")
    name = reg.list()[0]["name"]
    assert name in names.NAMES
    saved = json.loads((folder / "0123456789ab.json").read_text())
    assert saved["name"] == name and saved["title"] == "fix the thing"
    assert runner.Registry(tmp_path / "data").list()[0]["name"] == name


def test_rename_through_the_api(tmp_path, monkeypatch):
    reg = runner.Registry(tmp_path / "data")
    monkeypatch.setattr(web_app, "conversations", reg)
    client = TestClient(web_app.app)
    conv = client.post("/api/conversations", json={}, headers=FORGE).json()
    url = f"/api/conversations/{conv['id']}/settings"
    assert (
        client.post(url, json={"name": " Hana "}, headers=FORGE).json()["name"]
        == "Hana"
    )
    assert client.post(url, json={"name": "  "}, headers=FORGE).json()["name"] == "Hana"
    assert reg.list()[0]["name"] == "Hana"


def test_board_jump_finds_the_session_and_the_page_gets_it_once(tmp_path, monkeypatch):
    reg = runner.Registry(tmp_path / "data")
    monkeypatch.setattr(web_app, "conversations", reg)
    client = TestClient(web_app.app)
    conv = reg.create()
    conv.meta["session_id"] = "5e55-1d"
    conv.save_meta()
    listed = client.get("/api/sessions", headers=FORGE).json()["sessions"]
    assert listed["5e55-1d"]["name"] == conv.meta["name"]
    assert client.post("/api/sessions/nope/focus", headers=FORGE).status_code == 404
    got = client.post("/api/sessions/5e55-1d/focus", headers=FORGE).json()
    assert got["id"] == conv.meta["id"]
    assert (
        client.get("/api/conversations", headers=FORGE).json()["focus"]
        == conv.meta["id"]
    )
    assert client.get("/api/conversations", headers=FORGE).json()["focus"] == ""


def test_a_stale_focus_request_is_dropped(tmp_path, monkeypatch):
    reg = runner.Registry(tmp_path / "data")
    reg.ask_focus("abc")
    monkeypatch.setattr(runner.time, "time", lambda: 10**12)
    assert reg.take_focus() == ""
