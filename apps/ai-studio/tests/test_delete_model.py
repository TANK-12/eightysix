"""Deleting models, including the one that is active (it used to be refused)."""

import json

import pytest

from studio_fakes import entry, put, studio  # noqa: F401
import model_manager  # pyright: ignore[reportMissingImports]


def _part(name):
    return {
        "role": "checkpoint",
        "url": "https://x/" + name,
        "filename": name,
        "size_bytes": 1,
    }


@pytest.fixture
def setup(studio):
    studio.use([entry(m, [_part(f"{m}.safetensors")]) for m in "abc"], default="a")
    for mid in ("a", "b"):
        put(studio.legacy / f"{mid}.safetensors", 1)
    model_manager.set_active_id("b")
    return studio.legacy, studio.fake


def test_deleting_the_active_model_switches_to_another_installed_one(setup):
    folder, fake = setup
    model_manager.delete_model("b")
    assert not (folder / "b.safetensors").exists()
    assert fake.calls == ["stop", ("switch", "a")]
    assert model_manager.get_active_id() == "a"


def test_deleting_every_model_leaves_none_active(setup, studio):
    _, fake = setup
    model_manager.delete_model("b")
    model_manager.delete_model("a")
    assert model_manager.get_active_id() is None
    state = json.loads(model_manager.STATE_PATH.read_text())
    assert state["active"] is None
    assert fake.calls[-1] == "stop"


def test_deleting_an_inactive_model_leaves_the_servers_alone(setup):
    _, fake = setup
    model_manager.delete_model("a")
    assert fake.calls == []
    assert model_manager.get_active_id() == "b"


def test_ensure_running_starts_servers_for_a_model_they_are_not_running(setup):
    _, fake = setup
    model_manager.ensure_running()
    assert fake.calls == [("switch", "b")]
    model_manager.ensure_running()
    assert fake.calls == [("switch", "b")]


def test_deleting_the_active_video_model_clears_it(studio):
    vid = entry("v", [_part("v.gguf")], kind="video")
    studio.use([vid])
    put(studio.parts / "v.gguf", 1)
    model_manager.set_active_video_id("v")
    assert model_manager.get_active_video_id() == "v"
    model_manager.delete_model("v")
    assert model_manager.get_active_video_id() is None
    assert studio.fake.calls == []  # image servers untouched
