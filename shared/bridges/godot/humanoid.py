"""Humanoid retargeting for Godot: one skeleton layout for any character.

Godot plays an animation on a model when both use the same bone names under a
skeleton node of the same name. Its importer does the renaming when an import
is given a BoneMap onto SkeletonProfileHumanoid (Hips, Spine, LeftUpperArm...)
and makes the skeleton the unique node %GeneralSkeleton. This module writes
those BoneMaps and the matching `.import` files:

- a VRM carries its own humanoid bone table, so `vrm_bone_map` reads it
  (VRM 0.x and 1.0) and any VRoid model works without a hand-made list;
- `RIGIFY_BONE_MAP` covers Blender Rigify DEF- bones, which is what
  Quaternius's Universal Animation Library uses.

`retarget_import` writes a minimal `.import` beside the file; Godot fills
every other import option with its default on the first import.

    python3 humanoid.py <project> <model.vrm|anim.gltf> ...   # writes both files
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

# Godot SkeletonProfileHumanoid names for the fingers, as VRM 0.x names them:
# VRM 0.x counts the thumb Proximal/Intermediate/Distal, Godot (like VRM 1.0)
# Metacarpal/Proximal/Distal.
_VRM0_THUMB = {"Proximal": "Metacarpal", "Intermediate": "Proximal", "Distal": "Distal"}

_FINGERS = {
    "index": "Index",
    "f_middle": "Middle",
    "f_ring": "Ring",
    "f_pinky": "Little",
}
_SEGMENTS = ("Proximal", "Intermediate", "Distal")

RIGIFY_BONE_MAP: dict[str, str] = {
    "Root": "root",
    "Hips": "DEF-hips",
    "Spine": "DEF-spine.001",
    "Chest": "DEF-spine.002",
    "UpperChest": "DEF-spine.003",
    "Neck": "DEF-neck",
    "Head": "DEF-head",
}
for _side, _s in (("Left", "L"), ("Right", "R")):
    RIGIFY_BONE_MAP.update(
        {
            f"{_side}Shoulder": f"DEF-shoulder.{_s}",
            f"{_side}UpperArm": f"DEF-upper_arm.{_s}",
            f"{_side}LowerArm": f"DEF-forearm.{_s}",
            f"{_side}Hand": f"DEF-hand.{_s}",
            f"{_side}UpperLeg": f"DEF-thigh.{_s}",
            f"{_side}LowerLeg": f"DEF-shin.{_s}",
            f"{_side}Foot": f"DEF-foot.{_s}",
            f"{_side}Toes": f"DEF-toe.{_s}",
            f"{_side}ThumbMetacarpal": f"DEF-thumb.01.{_s}",
            f"{_side}ThumbProximal": f"DEF-thumb.02.{_s}",
            f"{_side}ThumbDistal": f"DEF-thumb.03.{_s}",
        }
    )
    for _rig, _finger in _FINGERS.items():
        _rig = _rig if _rig.startswith("f_") else "f_" + _rig
        for _n, _seg in enumerate(_SEGMENTS, 1):
            RIGIFY_BONE_MAP[f"{_side}{_finger}{_seg}"] = f"DEF-{_rig}.0{_n}.{_s}"


def gltf_json(path: Path) -> dict:
    """The JSON part of a .gltf, or of a binary .glb / .vrm."""
    data = path.read_bytes()
    if data[:4] != b"glTF":
        return json.loads(data)
    length = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20 : 20 + length])


def _profile_name(vrm_bone: str, vrm0: bool) -> str:
    name = vrm_bone[0].upper() + vrm_bone[1:]
    if vrm0 and "Thumb" in name:
        for old, new in _VRM0_THUMB.items():
            if name.endswith(old):
                return name[: -len(old)] + new
    return name


def vrm_bone_map(path: Path) -> dict[str, str]:
    """Godot profile bone -> the model's bone, from the VRM's humanoid table."""
    doc = gltf_json(path)
    nodes = doc.get("nodes", [])
    ext = doc.get("extensions", {})
    if "VRMC_vrm" in ext:  # VRM 1.0: {"hips": {"node": 3}, ...}
        bones = ext["VRMC_vrm"]["humanoid"]["humanBones"]
        pairs = [(bone, spec["node"]) for bone, spec in bones.items()]
        vrm0 = False
    elif "VRM" in ext:  # VRM 0.x: [{"bone": "hips", "node": 3}, ...]
        pairs = [(b["bone"], b["node"]) for b in ext["VRM"]["humanoid"]["humanBones"]]
        vrm0 = True
    else:
        raise ValueError(f"{path.name} has no VRM humanoid table")
    mapping = {_profile_name(bone, vrm0): nodes[i]["name"] for bone, i in pairs}
    names = {n.get("name") for n in nodes}
    for root in ("Root", "root"):
        if root in names:
            mapping["Root"] = root
            break
    return mapping


def bone_map_for(path: Path) -> dict[str, str]:
    """The right map for a model or animation file, by what it contains."""
    doc = gltf_json(path)
    if {"VRM", "VRMC_vrm"} & set(doc.get("extensions", {})):
        return vrm_bone_map(path)
    names = {n.get("name") for n in doc.get("nodes", [])}
    if "DEF-hips" in names:
        return {k: v for k, v in RIGIFY_BONE_MAP.items() if v in names}
    raise ValueError(f"{path.name}: not a VRM and not a Rigify DEF- skeleton")


def skeleton_path(path: Path) -> str:
    """The Skeleton3D's node path in Godot's import of this file. Godot turns
    the skin's top joint into the Skeleton3D, under that joint's parents."""
    doc = gltf_json(path)
    nodes, skins = doc.get("nodes", []), doc.get("skins", [])
    if not skins:
        return "Skeleton3D"
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    joints = set(skins[0]["joints"])
    top = next(j for j in skins[0]["joints"] if parent.get(j) not in joints)
    chain = []
    i = parent.get(top)
    while i is not None:
        chain.append(nodes[i]["name"])
        i = parent.get(i)
    return "/".join(list(reversed(chain)) + ["Skeleton3D"])


def bone_map_tres(mapping: dict[str, str]) -> str:
    lines = [
        '[gd_resource type="BoneMap" load_steps=2 format=3]',
        "",
        '[sub_resource type="SkeletonProfileHumanoid" id="profile"]',
        "",
        "[resource]",
        'profile = SubResource("profile")',
    ]
    lines += [f'bone_map/{k} = &"{v}"' for k, v in sorted(mapping.items())]
    return "\n".join(lines) + "\n"


def retarget_import(res_map: str, skeleton: str) -> str:
    """A minimal scene .import that retargets `skeleton` with the BoneMap at
    `res_map` (a res:// path); Godot fills in every other option."""
    return (
        "[remap]\n\n"
        'importer="scene"\n'
        'type="PackedScene"\n\n'
        "[params]\n\n"
        "_subresources={\n"
        '"nodes": {\n'
        f'"PATH:{skeleton}": {{\n'
        f'"retarget/bone_map": Resource("{res_map}")\n'
        "}\n}\n}\n"
    )


def write_retarget(project: Path, model: Path) -> tuple[Path, Path]:
    """Write <model>.bonemap.tres and <model>.import inside the project."""
    project, model = project.resolve(), model.resolve()
    tres = model.with_name(model.name + ".bonemap.tres")
    tres.write_text(bone_map_tres(bone_map_for(model)))
    res = "res://" + tres.relative_to(project).as_posix()
    imp = model.with_name(model.name + ".import")
    imp.write_text(retarget_import(res, skeleton_path(model)))
    return tres, imp


if __name__ == "__main__":
    root = Path(sys.argv[1])
    for arg in sys.argv[2:]:
        for written in write_retarget(root, Path(arg)):
            print(written)
