"""Quiet conversations in no folder move to Archived (Emerson, 2026-09-27:
"auto archive ... conversations that aren't in a folder ... 2 hours old")."""

import json
import time

import projects
import runner
import web_app
from fastapi.testclient import TestClient

FORGE = {"X-Forge": "1"}
HOUR = 3600


def make(reg, age_hours, folder=""):
    conv = reg.create()
    conv.meta["updated"] = conv.meta["created"] = time.time() - age_hours * HOUR
    conv.meta["folder"] = folder
    conv.save_meta()
    return conv.meta["id"]


def opened(reg, conv_id):
    conv = reg.get(conv_id)
    assert conv is not None
    return conv


def archived(reg):
    return {m["id"] for m in reg.list() if m.get("archived")}


def test_only_quiet_conversations_in_no_folder_are_archived(tmp_path):
    reg = runner.Registry(tmp_path / "data")
    old = make(reg, 3)
    fresh = make(reg, 1)
    filed = make(reg, 5, folder="work")
    busy = make(reg, 5)
    opened(reg, busy).busy = True
    assert archived(reg) == {old}
    saved = json.loads((tmp_path / "data/conversations" / f"{old}.json").read_text())
    assert saved["archived"] and saved["title"] == opened(reg, old).meta["title"]
    assert fresh and filed  # kept out


def test_an_open_copy_keeps_the_stamp_when_it_saves(tmp_path):
    reg = runner.Registry(tmp_path / "data")
    old = make(reg, 3)
    conv = opened(reg, old)
    reg.list()
    conv.save_meta()
    assert archived(runner.Registry(tmp_path / "data")) == {old}


def test_zero_hours_archives_nothing(tmp_path):
    reg = runner.Registry(tmp_path / "data")
    reg.archive_hours = lambda: 0
    make(reg, 50)
    assert archived(reg) == set()


def test_restore_filing_and_manual_archive_through_the_api(tmp_path, monkeypatch):
    reg = runner.Registry(tmp_path / "data")
    monkeypatch.setattr(web_app, "conversations", reg)
    client = TestClient(web_app.app)
    a, b, c = make(reg, 3), make(reg, 3), make(reg, 0)
    assert archived(reg) == {a, b}
    url = "/api/conversations/{}/settings"
    client.post(url.format(a), json={"archived": False}, headers=FORGE)
    client.post("/api/folders", json={"name": "kept"}, headers=FORGE)
    client.post(url.format(b), json={"folder": "kept"}, headers=FORGE)
    client.post(url.format(c), json={"archived": True}, headers=FORGE)
    # brought back = a fresh quiet window, so the next listing leaves it alone
    assert archived(reg) == {c}
    shown = client.get("/api/conversations", headers=FORGE).json()["conversations"]
    assert {m["id"] for m in shown if m.get("archived")} == {c}


def test_the_hours_come_from_forge_settings(monkeypatch):
    monkeypatch.setattr(
        web_app.forge_theme, "load", lambda: {"claude_archive_hours": 5}
    )
    assert web_app.conversations.archive_hours() == 5.0


def test_archived_tasks_leave_the_enjoy_loose_list(tmp_path):
    reg = runner.Registry(tmp_path / "data")
    old, fresh = make(reg, 3), make(reg, 0)
    assert [t["id"] for t in projects.listing(reg)["loose"]] == [fresh]
    assert old
