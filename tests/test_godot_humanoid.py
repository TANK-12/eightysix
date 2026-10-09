"""shared/bridges/godot/humanoid.py: bone maps onto Godot's humanoid profile."""

from __future__ import annotations

import sys
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORGE / "shared" / "bridges" / "godot"))

import humanoid  # noqa: E402  # pyright: ignore[reportMissingImports]

VRM = FORGE / "shared/assets/characters/hairsample_female/HairSample_Female.vrm"
UAL = (
    FORGE
    / "shared/assets/animations/universal_animation_library"
    / "AnimationLibrary_Godot_Standard.gltf"
)


def test_vrm0_table_becomes_profile_names():
    m = humanoid.vrm_bone_map(VRM)
    assert m["Hips"] == "J_Bip_C_Hips"
    assert m["LeftUpperArm"] == "J_Bip_L_UpperArm"
    # VRM 0.x counts thumbs from Proximal; Godot from Metacarpal.
    assert m["LeftThumbMetacarpal"] == "J_Bip_L_Thumb1"
    assert m["LeftThumbDistal"] == "J_Bip_L_Thumb3"
    assert m["Root"] == "Root"
    assert len(m) == 55


def test_vrm1_names_pass_through():
    assert humanoid._profile_name("leftThumbMetacarpal", vrm0=False) == (
        "LeftThumbMetacarpal"
    )
    assert humanoid._profile_name("upperChest", vrm0=False) == "UpperChest"


def test_rigify_map_covers_the_animation_library():
    m = humanoid.bone_map_for(UAL)
    assert m["LeftLittleDistal"] == "DEF-f_pinky.03.L"
    assert m["RightIndexProximal"] == "DEF-f_index.01.R"
    assert len(m) == 53


def test_skeleton_paths():
    assert humanoid.skeleton_path(VRM) == "Skeleton3D"
    assert humanoid.skeleton_path(UAL) == "Rig/Skeleton3D"


def test_import_file_names_the_bone_map():
    text = humanoid.retarget_import("res://a.tres", "Rig/Skeleton3D")
    assert '"PATH:Rig/Skeleton3D"' in text
    assert 'Resource("res://a.tres")' in text
    assert text.startswith("[remap]")
