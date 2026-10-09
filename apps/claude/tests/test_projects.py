"""A15: the Enjoy layout's projects, tasks, notes, workflows and the
running / needs you states, on top of the same conversations and folders."""

import time
from pathlib import Path

import pytest

import projects
import runner


@pytest.fixture
def reg(tmp_path):
    return runner.Registry(tmp_path / "data")


def task(reg, folder="", **meta):
    conv = reg.create(str(reg.data_dir.parent), "", runner.DEFAULT_MODE, "", "")
    if folder:
        reg.file_into(conv.meta["id"], folder)
    conv.meta.update(meta)
    conv.save_meta()
    return conv.meta["id"]


def test_a_project_is_a_folder_and_keeps_its_extras_through_a_rename(reg, tmp_path):
    made = projects.create(reg, "Cosmos", str(tmp_path))
    assert made["name"] == "Cosmos" and made["cwd"] == str(tmp_path) and made["id"]
    assert any(
        f["name"] == "Cosmos" for f in reg.folders()
    )  # the classic layout sees it
    reg.update_folder("Cosmos", new_name="Cosmos app")  # renamed in the classic layout
    again = projects.get(reg, made["id"])
    assert again["name"] == "Cosmos app" and again["cwd"] == str(tmp_path)


def test_a_plain_folder_is_a_project_too(reg):
    reg.add_folder("Old folder")
    listed = projects.listing(reg)
    assert [p["name"] for p in listed["projects"]] == ["Old folder"]
    assert listed["projects"][0]["id"]  # given a stable id on first sight
    assert projects.listing(reg)["projects"][0]["id"] == listed["projects"][0]["id"]


def test_a_project_needs_a_real_working_folder(reg, tmp_path):
    with pytest.raises(ValueError):
        projects.create(reg, "Nowhere", str(tmp_path / "missing"))


def test_tasks_are_the_conversations_filed_in_the_project(reg, tmp_path):
    p = projects.create(reg, "Forge", str(tmp_path))
    inside = task(reg, "Forge")
    loose = task(reg)
    listed = projects.listing(reg)
    assert [t["id"] for t in listed["projects"][0]["tasks"]] == [inside]
    assert [t["id"] for t in listed["loose"]] == [loose]
    assert p["id"] == listed["projects"][0]["id"]


def test_running_needs_you_and_quiet():
    now = time.time()
    fresh = {"id": "a", "busy": False}
    assert projects.state(fresh) == "new"
    assert (
        projects.state({"busy": True, "last_turn": {"at": now, "ok": True}})
        == "running"
    )
    unread = {"busy": False, "last_turn": {"at": now, "ok": True}, "seen": now - 5}
    assert projects.state(unread) == "needs you"
    read = {"busy": False, "last_turn": {"at": now, "ok": True}, "seen": now + 1}
    assert projects.state(read) == "quiet"
    failed = {"busy": False, "last_turn": {"at": now, "ok": False}, "seen": now + 1}
    assert projects.state(failed) == "needs you"
    refused = {
        "busy": False,
        "last_turn": {"at": now, "ok": True, "denied": 2},
        "seen": now + 1,
    }
    assert projects.state(refused) == "needs you"


def test_listing_counts_what_is_running_and_what_needs_you(reg, tmp_path):
    projects.create(reg, "P", str(tmp_path))
    task(reg, "P", last_turn={"at": time.time(), "ok": False})
    task(reg, "P")
    row = projects.listing(reg)["projects"][0]
    assert row["counts"] == {"running": 0, "needs you": 1}
    assert [t["state"] for t in row["tasks"]].count("needs you") == 1


def test_notes_are_markdown_files_that_round_trip(reg, tmp_path):
    p = projects.create(reg, "Notes", str(tmp_path))
    projects.save_note(reg, p["id"], "Plan for v2", "# v2\n\n- faster")
    assert [n["name"] for n in projects.notes(reg, p["id"])] == ["Plan for v2"]
    assert projects.read_note(reg, p["id"], "Plan for v2") == "# v2\n\n- faster"
    projects.delete_note(reg, p["id"], "Plan for v2")
    assert projects.notes(reg, p["id"]) == []


def test_note_names_cannot_leave_the_project(reg, tmp_path):
    p = projects.create(reg, "Safe", str(tmp_path))
    projects.save_note(reg, p["id"], "../../escape", "x")
    assert not (reg.data_dir.parent / "escape.md").exists()
    assert [n["name"] for n in projects.notes(reg, p["id"])] == ["escape"]


def test_workflows_are_saved_and_checked(reg, tmp_path):
    p = projects.create(reg, "Flows", str(tmp_path))
    flows = [{"name": "Release", "steps": ["run the tests", "bump the version"]}]
    assert projects.update(reg, p["id"], workflows=flows)["workflows"] == flows
    with pytest.raises(ValueError):
        projects.update(reg, p["id"], workflows=[{"name": "", "steps": ["x"]}])
    with pytest.raises(ValueError):
        projects.update(reg, p["id"], workflows=[{"name": "Empty", "steps": []}])


def test_a_workflow_becomes_one_prompt():
    flow = {"name": "Release", "steps": ["run the tests", "bump the version"]}
    text = projects.workflow_prompt(flow)
    assert text.startswith("Workflow: Release")
    assert "1. run the tests" in text and "2. bump the version" in text


def test_a_finished_turn_is_recorded_for_needs_you(reg):
    conv = reg.create(str(reg.data_dir.parent), "", runner.DEFAULT_MODE, "", "")
    conv.note_turn({"type": "result", "subtype": "success", "permission_denials": [{}]})
    assert (
        conv.meta["last_turn"]["ok"] is True and conv.meta["last_turn"]["denied"] == 1
    )
    conv.note_turn(
        {"type": "result", "subtype": "error_during_execution", "is_error": True}
    )
    assert conv.meta["last_turn"]["ok"] is False


def test_running_a_workflow_starts_a_task_in_its_project(tmp_path, monkeypatch):
    import sys

    from fastapi.testclient import TestClient

    import web_app

    fake = Path(__file__).with_name("fake_claude.py")
    monkeypatch.setenv("FORGE_CLAUDE_BIN", f"{sys.executable} {fake}")
    reg = runner.Registry(tmp_path / "data")
    monkeypatch.setattr(web_app, "conversations", reg)
    client = TestClient(web_app.app)
    h = {"X-Forge": "1"}
    p = client.post(
        "/api/projects", json={"name": "Web", "cwd": str(tmp_path)}, headers=h
    ).json()
    flows = [{"name": "Tidy", "steps": ["format the code"]}]
    client.post(f"/api/projects/{p['id']}", json={"workflows": flows}, headers=h)
    made = client.post(f"/api/projects/{p['id']}/workflows/0/run", headers=h)
    assert made.status_code == 200, made.text
    meta = made.json()
    assert meta["folder"] == "Web" and meta["title"] == "Tidy"
    row = client.get("/api/projects", headers=h).json()["projects"][0]
    assert [t["id"] for t in row["tasks"]] == [meta["id"]]
    assert (
        client.post(f"/api/projects/{p['id']}/workflows/5/run", headers=h).status_code
        == 404
    )
