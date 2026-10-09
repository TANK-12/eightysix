"""2.5D wallpapers (S23): shared/forge_layers.py and the theme's layer fields.

The model run itself (onnxruntime, about 8 s of CPU) is not repeated here;
it was run once on the real wallpaper on 2026-09-28 (see the S26 brief).
These cover everything around it: where the files go, when a job starts,
that nothing is installed or downloaded, and which mask becomes the subject.
"""

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

import forge_layers  # noqa: E402
import forge_theme  # noqa: E402


def test_ready_only_when_the_files_are_there(tmp_path):
    assert forge_layers.ready("k", tmp_path) is None
    p = forge_layers.layer_paths("k", tmp_path)
    p["info"].write_text(json.dumps({"subject": "character"}))
    assert forge_layers.ready("k", tmp_path) is None  # no layers yet
    p["fg"].write_bytes(b"x")
    p["bg"].write_bytes(b"x")
    assert forge_layers.ready("k", tmp_path) == {"subject": "character"}
    p["info"].write_text(json.dumps({"subject": "none", "error": "no models"}))
    flat = forge_layers.ready("k", tmp_path)
    assert flat is not None and flat["subject"] == "none"  # flat, final


def test_start_runs_once_in_the_background(tmp_path, monkeypatch):
    image = tmp_path / "k.jpg"
    image.write_bytes(b"jpg")
    monkeypatch.setattr(forge_layers, "find_python", lambda: "/venv/bin/python")
    monkeypatch.setattr(forge_layers, "find_models", lambda: {"seg": 1, "depth": 2})
    runs = []
    popen = lambda argv, **kw: runs.append((argv, kw))  # noqa: E731
    assert forge_layers.start(image, "k", tmp_path, popen=popen)
    argv, kw = runs[0]
    assert argv[:4] == ["nice", "-n", "19", "/venv/bin/python"]
    assert argv[-4:] == ["make", str(image), "k", str(tmp_path)]
    assert kw["start_new_session"]
    # a job is running (its lock is fresh): no second one
    assert not forge_layers.start(image, "k", tmp_path, popen=popen)
    # a lock left by a crash long ago does not block it for ever
    lock = forge_layers.layer_paths("k", tmp_path)["lock"]
    old = time.time() - 3600
    import os

    os.utime(lock, (old, old))
    assert forge_layers.start(image, "k", tmp_path, popen=popen)
    # made (or failed) once: never again
    forge_layers.layer_paths("k", tmp_path)["info"].write_text('{"subject": "none"}')
    assert not forge_layers.start(image, "k", tmp_path, popen=popen)
    assert len(runs) == 2


def test_start_needs_models_and_a_python_already_here(tmp_path, monkeypatch):
    image = tmp_path / "k.jpg"
    image.write_bytes(b"jpg")
    monkeypatch.setattr(forge_layers, "find_python", lambda: None)
    assert not forge_layers.start(image, "k", tmp_path, popen=lambda *a, **k: 1 / 0)
    monkeypatch.setattr(forge_layers, "find_python", lambda: "/py")
    monkeypatch.setattr(forge_layers, "find_models", lambda: None)
    assert not forge_layers.start(image, "k", tmp_path, popen=lambda *a, **k: 1 / 0)


def test_find_python_picks_a_venv_that_has_everything(tmp_path):
    for app, libs in (("a", ["numpy"]), ("b", ["numpy", "PIL", "onnxruntime"])):
        site = tmp_path / app / ".venv/lib/python3.14/site-packages"
        for lib in libs:
            (site / lib).mkdir(parents=True)
        (tmp_path / app / ".venv/bin").mkdir(parents=True)
        (tmp_path / app / ".venv/bin/python").write_text("")
    assert forge_layers.find_python(tmp_path) == str(tmp_path / "b/.venv/bin/python")


def test_find_models_prefers_the_quicker_depth_model(tmp_path):
    assert forge_layers.find_models(tmp_path) is None
    for rel in ("scene-seg/isnetis.onnx", "scene-depth_base/model.onnx"):
        (tmp_path / rel).parent.mkdir(parents=True)
        (tmp_path / rel).write_bytes(b"onnx")
    found = forge_layers.find_models(tmp_path)
    assert found is not None and found["depth"].parent.name == "scene-depth_base"
    (tmp_path / "scene-depth_small").mkdir()
    (tmp_path / "scene-depth_small/model.onnx").write_bytes(b"onnx")
    found = forge_layers.find_models(tmp_path)
    assert found is not None and found["depth"].parent.name == "scene-depth_small"


def test_the_subject_is_a_character_else_the_near_scene_else_nothing():
    np = pytest.importorskip("numpy")
    depth = np.tile(np.linspace(0, 1, 100), (100, 1))  # nearer to the right
    seg = np.zeros((100, 100))
    seg[40:60, 40:60] = 1  # a character, 4% of the picture
    mask, what = forge_layers.pick_subject(seg, depth)
    assert what == "character" and mask is seg
    mask, what = forge_layers.pick_subject(np.zeros((100, 100)), depth)
    assert what == "near" and mask[:, -1].mean() > 0.9 and mask[:, 0].mean() == 0
    mask, what = forge_layers.pick_subject(
        np.zeros((100, 100)), np.full((100, 100), 0.5)
    )
    assert what == "none" and not mask.any()


def test_the_theme_hands_the_hub_the_layers(tmp_path, monkeypatch):
    image = tmp_path / "k.jpg"
    image.write_bytes(b"jpg")
    started = []
    monkeypatch.setattr(forge_layers, "start", lambda *a: started.append(a))
    off = forge_theme.wallpaper_layers({"wall_3d": False}, image, None)
    assert off["wallpaper_fg"] == "" and not started
    on = forge_theme.wallpaper_layers({"wall_3d": True}, image, None)
    assert on["wallpaper_fg"] == "" and len(started) == 1  # making them now
    p = forge_layers.layer_paths("k", tmp_path)
    p["info"].write_text('{"subject": "near"}')
    p["fg"].write_bytes(b"x")
    p["bg"].write_bytes(b"x")
    on = forge_theme.wallpaper_layers({"wall_3d": True}, image, None)
    assert on["wallpaper_fg"] == p["fg"].as_uri() and on["wallpaper_subject"] == "near"
    assert on["wallpaper_bg"] == p["bg"].as_uri()


def test_the_settings_and_the_popup():
    s = forge_theme.SETTINGS
    assert s["wall_3d"]["default"] is False
    assert s["wall_3d_depth"]["kind"] == "number"
    assert {"wall_3d", "wall_3d_depth", "wall_3d_beat"} <= set(
        forge_theme.VISUALS_POPUP
    )
