"""Crucible's play.py commands: they run the JS world through node."""

from __future__ import annotations

import json
import shutil

import pytest

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


@pytest.fixture
def m(load_curio):
    return load_curio("crucible")


def test_nothing_happens_at_import(m, data_dir):
    assert not data_dir.exists()
    assert set(m.COMMANDS) == {"run", "keep"}
    for fn, text in m.COMMANDS.values():
        assert callable(fn) and text


@needs_node
def test_every_scene_runs(m):
    for scene in m.SCENES:
        out = m.run_scene(scene, 5, 40)
        assert out["scene"] == scene and out["steps"] == 5
        assert out["picture"] and all(len(line) <= 40 for line in out["picture"])
        assert out["data"]["v"] == 1 and out["data"]["tick"] == 5


@needs_node
def test_run_prints_a_picture_and_melts_ore(m, capsys):
    assert m.cli_run(["starter", "--steps", "500"]) == 0
    text = capsys.readouterr().out
    assert "starter after 500 steps" in text
    assert "molten iron" in text and "# stone" in text
    melted = int(text.split("so far: ")[1].split(" melted")[0])
    assert melted > 100


@needs_node
def test_run_is_deterministic(m):
    a = m.run_scene("bloomery", 60)
    b = m.run_scene("bloomery", 60)
    assert a["data"] == b["data"] and a["picture"] == b["picture"]


def test_unknown_scene_is_refused(m, capsys):
    with pytest.raises(SystemExit):
        m.cli_run(["nowhere"])
    with pytest.raises(ValueError):
        m.run_scene("nowhere", 1)


@needs_node
def test_keep_saves_a_keepsake(m, data_dir, capsys):
    import store

    assert m.cli_keep(["thaw", "--steps", "30", "--name", "Cold cave"]) == 0
    assert "Kept as" in capsys.readouterr().out
    rows = [r for r in store.list_keepsakes("crucible") if not r["seed"]]
    assert [r["name"] for r in rows] == ["Cold cave"]
    full = store.load_keepsake("crucible", rows[0]["slug"])
    assert full["data"]["tick"] == 30 and full["author"] == "Claude"
    assert len(json.dumps(full["data"])) < 100_000
    assert data_dir.exists()


def test_missing_node_is_a_plain_message(m, monkeypatch, capsys):
    monkeypatch.setattr(m.shutil, "which", lambda _name: None)
    assert m.cli_run(["starter"]) == 1
    assert "node is not on PATH" in capsys.readouterr().out
