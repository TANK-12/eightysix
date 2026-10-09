"""Keymap API on a throwaway Hyprland config (U1 sweep): edits stay inside
the keybind files the scope registry lists, and bad input is a calm answer,
never a 500."""

import json
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import editor  # noqa: E402
import sources  # noqa: E402
import web_app  # noqa: E402

BIND = 'hl.bind("SUPER + T", hl.exec("kitty"))\n'


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    hypr = home / ".config" / "hypr"
    (hypr / "hyprland").mkdir(parents=True)
    (hypr / "custom").mkdir()
    (hypr / "hyprland" / "keybinds.lua").write_text(BIND)
    (hypr / "custom" / "keybinds.lua").write_text("")
    (hypr / "hyprland" / "shells.lua").write_text("return {}\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(sources, "HYPR_DIR", hypr)
    monkeypatch.setattr(sources, "SHELLS_LUA", hypr / "hyprland" / "shells.lua")
    monkeypatch.setattr(sources, "VARIABLES_LUA", hypr / "variables.lua")
    monkeypatch.setattr(
        sources,
        "UNIVERSAL_FILES",
        [hypr / "hyprland" / "keybinds.lua", hypr / "custom" / "keybinds.lua"],
    )
    data = tmp_path / "data"
    monkeypatch.setattr(editor, "DATA_DIR", data)
    monkeypatch.setattr(editor, "BACKUPS_DIR", data / "backups")
    monkeypatch.setattr(editor, "HISTORY_FILE", data / "history.jsonl")
    return TestClient(web_app.app, raise_server_exceptions=False), hypr, tmp_path


def edit(client, file, old='"SUPER + T"', new='"SUPER + Y"', line=1):
    body = {
        "targets": [{"file": str(file), "line": line, "old_text": old, "new_text": new}]
    }
    r = client.post("/api/binds/edit", json=body)
    assert r.status_code == 200
    return r.json()["results"][0]


def test_an_edit_to_a_listed_keybind_file_saves_and_undo_brings_it_back(env):
    client, hypr, _ = env
    target = hypr / "hyprland" / "keybinds.lua"
    result = edit(client, target)
    assert result["ok"], result
    assert '"SUPER + Y"' in target.read_text()
    r = client.post(f"/api/undo/{result['history_id']}")
    assert r.status_code == 200
    assert target.read_text() == BIND


def test_a_file_outside_the_scope_registry_is_never_touched(env):
    client, _, tmp = env
    other = tmp / "other.lua"
    other.write_text(BIND)
    result = edit(client, other)
    assert not result["ok"] and "not one of the keybind files" in result["error"]
    assert other.read_text() == BIND
    assert not (tmp / "data" / "backups").exists()


@pytest.mark.parametrize(
    "old, new, says",
    [
        ("", '"X"', "empty"),
        ('"SUPER + T"', "", "empty"),
        ('"SUPER + T"', '"A"\nos.exit()', "one line"),
    ],
)
def test_an_empty_old_combo_or_a_new_line_is_refused(env, old, new, says):
    client, hypr, _ = env
    target = hypr / "hyprland" / "keybinds.lua"
    result = edit(client, target, old=old, new=new)
    assert not result["ok"] and says in result["error"]
    assert target.read_text() == BIND


def test_a_listed_file_that_has_gone_is_an_error_not_a_500(env):
    client, hypr, _ = env
    (hypr / "custom" / "keybinds.lua").unlink()
    result = edit(client, hypr / "custom" / "keybinds.lua")
    assert not result["ok"] and "could not edit" in result["error"]


def test_a_damaged_history_line_is_skipped(env):
    client, _, tmp = env
    (tmp / "data").mkdir()
    good = {"id": "a1", "timestamp": 1.0, "action": "edit", "file": "f", "line": 1,
            "old_text": '"A"', "new_text": '"B"'}  # fmt: skip
    (tmp / "data" / "history.jsonl").write_text(
        "{not json\n" + json.dumps(good) + "\n[1, 2]\n"
    )
    r = client.get("/api/history")
    assert r.status_code == 200 and [e["id"] for e in r.json()["history"]] == ["a1"]


def test_history_lines_of_the_wrong_shape_are_skipped_not_a_500(env):
    client, _, tmp = env
    (tmp / "data").mkdir()
    full = {"id": "a1", "timestamp": 1.0, "action": "edit", "file": "f", "line": 1,
            "old_text": '"A"', "new_text": '"B"'}  # fmt: skip
    odd = [
        {**full, "id": "s", "timestamp": "yesterday"},
        {"id": "short", "timestamp": 3.0},
        {**full, "id": "b", "line": "1"},
    ]
    lines = [json.dumps(full)] + [json.dumps(o) for o in odd]
    (tmp / "data" / "history.jsonl").write_text("\n".join(lines) + "\n")
    r = client.get("/api/history")
    assert r.status_code == 200 and [e["id"] for e in r.json()["history"]] == ["a1"]
    assert client.post("/api/undo/short").status_code == 404


def test_undo_of_an_entry_for_a_file_outside_the_registry_is_refused(env):
    client, _, tmp = env
    other = tmp / "other.lua"
    other.write_text('hl.bind("SUPER + Y", x)\n')
    (tmp / "data").mkdir()
    entry = {
        "id": "b2", "timestamp": 2.0, "action": "edit", "file": str(other),
        "line": 1, "old_text": '"SUPER + T"', "new_text": '"SUPER + Y"',
        "description": None, "scopes": [],
    }  # fmt: skip
    (tmp / "data" / "history.jsonl").write_text(json.dumps(entry) + "\n")
    r = client.post("/api/undo/b2")
    assert r.status_code == 409
    assert "SUPER + Y" in other.read_text()
    assert client.post("/api/undo/nope").status_code == 404


def test_an_infinite_line_number_is_a_422_not_a_500(env):
    client, hypr, _ = env
    body = (
        '{"targets": [{"file": "x", "line": 1e999, "old_text": "a", "new_text": "b"}]}'
    )
    r = client.post(
        "/api/binds/edit", content=body, headers={"content-type": "application/json"}
    )
    assert r.status_code == 422 and "inf" not in r.text.lower()


def test_binds_list_reads_the_throwaway_config(env):
    client, _, _ = env
    binds = client.get("/api/binds").json()["binds"]
    assert any(b["key_display"] == "SUPER + T" and b["editable"] for b in binds)
