"""Godot toolset: starter templates and .glb/.gltf/.vrm import checks.

The last test runs real headless Godot and is skipped when it is missing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acchan.registry import ToolError  # noqa: E402
from acchan.tools import godot  # noqa: E402


def test_templates_are_discovered_with_summaries():
    found = godot.templates()
    assert "third_person" in found
    assert "Phantom Camera" in found["third_person"]
    assert "VRoid" in found["third_person"]


def test_new_project_from_template_copies_its_files(tmp_path):
    root = tmp_path / "game"
    msg = godot.godot_new_project(str(root), template="third_person")
    assert "third_person template" in msg
    for name in ("main.tscn", "player.tscn", "player.gd", "project.godot"):
        assert (root / name).is_file(), name
    assert not (root / "template.json").exists()
    assert "follow_mode = 6" in (root / "main.tscn").read_text()
    # Without node_paths Godot never resolves follow_target and the camera stays put.
    assert (
        'node_paths=PackedStringArray("follow_target")'
        in (root / "main.tscn").read_text()
    )
    assert "AnimationTree" in (root / "player.tscn").read_text()


def test_template_brings_its_character_retargeted(tmp_path):
    root = tmp_path / "game"
    godot.godot_new_project(str(root), template="third_person")
    chars = root / "characters"
    for name in (
        "HairSample_Female.vrm",
        "AnimationLibrary_Godot_Standard.gltf",
        "AnimationLibrary_Godot_Standard.bin",
        "CREDITS.md",
    ):
        assert (chars / name).is_file(), name
    vrm_map = (chars / "HairSample_Female.vrm.bonemap.tres").read_text()
    assert 'bone_map/Hips = &"J_Bip_C_Hips"' in vrm_map
    ual_map = (chars / "AnimationLibrary_Godot_Standard.gltf.bonemap.tres").read_text()
    assert 'bone_map/LeftUpperLeg = &"DEF-thigh.L"' in ual_map
    assert '"PATH:Skeleton3D"' in (chars / "HairSample_Female.vrm.import").read_text()
    assert (
        '"PATH:Rig/Skeleton3D"'
        in (chars / "AnimationLibrary_Godot_Standard.gltf.import").read_text()
    )


def test_missing_template_asset_is_named(tmp_path, monkeypatch):
    monkeypatch.setattr(godot, "ASSETS", tmp_path / "nothing")
    with pytest.raises(ToolError, match="HairSample_Female.vrm"):
        godot.godot_new_project(str(tmp_path / "g"), template="third_person")


def test_plain_project_keeps_default_scene(tmp_path):
    root = tmp_path / "plain"
    godot.godot_new_project(str(root))
    assert not (root / "player.tscn").exists()
    assert (root / "main.tscn").read_text() == godot.MAIN_TSCN


def test_unknown_template_is_refused_before_writing(tmp_path):
    root = tmp_path / "nope"
    with pytest.raises(ToolError, match="third_person"):
        godot.godot_new_project(str(root), template="platformer9000")
    assert not root.exists()


def _model(root: Path, rel: str, meta: str | None) -> None:
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"glTF")
    if meta is not None:
        f.with_name(f.name + ".import").write_text(meta)


def test_import_problems_finds_each_kind(tmp_path):
    (tmp_path / ".godot/imported").mkdir(parents=True)
    (tmp_path / ".godot/imported/ok.scn").write_bytes(b"x")
    ok = '[remap]\nimporter="scene"\npath="res://.godot/imported/ok.scn"\n'
    _model(tmp_path, "models/ok.glb", ok)
    _model(tmp_path, "models/never.glb", None)
    _model(tmp_path, "chars/girl.vrm", None)
    _model(tmp_path, "models/broken.gltf", '[remap]\nimporter="scene"\nvalid=false\n')
    _model(
        tmp_path,
        "models/gone.glb",
        '[remap]\nimporter="scene"\npath="res://.godot/imported/gone.scn"\n',
    )
    _model(tmp_path, "addons/vrm/sample.vrm", None)  # add-on files are ignored
    log = ["WARNING: ok.glb: mesh has no UVs", "unrelated line"]

    problems = godot.import_problems(tmp_path, log)
    text = "\n".join(problems)
    assert "models/never.glb: not imported" in text
    assert "chars/girl.vrm: not imported" in text and "vrm add-on" in text
    assert "models/broken.gltf: import failed" in text
    assert "models/gone.glb: imported file .godot/imported/gone.scn is missing" in text
    assert "models/ok.glb: WARNING: ok.glb: mesh has no UVs" in text
    assert "addons" not in text
    assert len(problems) == 5


def test_import_problems_clean_project(tmp_path):
    assert godot.import_problems(tmp_path, ["WARNING: something else"]) == []


@pytest.mark.skipif(not shutil.which("godot"), reason="Godot is not installed")
def test_third_person_template_opens_clean_in_real_godot(tmp_path):
    root = tmp_path / "tp"
    godot.godot_new_project(str(root), template="third_person")
    assert godot.godot_check(str(root)) == "No script, scene or model import errors."
    # Walk the demo circle headless: the player moves, the tree blends to the
    # jog and the character's own thigh bone swings (the clips reached it).
    probe = root / "walk_probe.gd"
    probe.write_text(WALK_PROBE)
    out = subprocess.run(
        [godot.godot_bin(), "--headless", "--path", str(root), "-s", "walk_probe.gd"],
        env={**os.environ, "FORGE_DEMO_WALK": "1"},
        capture_output=True,
        text=True,
        timeout=180,
    )
    line = next(x for x in out.stdout.splitlines() if x.startswith("WALK "))
    walk = json.loads(line[5:])
    assert walk["moved"] > 1.0, walk
    assert walk["blend"] > 0.5, walk
    assert walk["leg_swing"] > 0.2, walk
    # A clip whose tracks miss the skeleton says so on stderr.
    track_errors = [
        x for x in out.stderr.splitlines() if "ERROR" in x and "track" in x.lower()
    ]
    assert not track_errors, track_errors


WALK_PROBE = """extends SceneTree
var frames := 0
var scene: Node
var player: Node3D
var start: Vector3
var sk: Skeleton3D
var leg := -1
var seen: Array[Quaternion] = []

func _init() -> void:
	scene = load("res://main.tscn").instantiate()
	root.add_child(scene)
	player = scene.find_child("Player", true, false)
	start = player.global_position
	sk = player.get_node("Body/Character").get_node("%GeneralSkeleton")
	leg = sk.find_bone("LeftUpperLeg")

func _process(_delta: float) -> bool:
	frames += 1
	if frames > 30:
		seen.append(sk.get_bone_pose_rotation(leg))
	if frames < 150:
		return false
	var swing := 0.0
	for q in seen:
		swing = maxf(swing, q.angle_to(seen[0]))
	var tree: AnimationTree = player.get_node("AnimationTree")
	print("WALK ", JSON.stringify({
		"moved": player.global_position.distance_to(start),
		"blend": tree.get("parameters/blend_position"),
		"leg_swing": swing,
	}))
	return true
"""
