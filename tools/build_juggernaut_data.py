#!/usr/bin/env python3
"""Generate the real Juggernaut's parts.json entries and mechs.json placement (lane A2).

Reads assets/models/juggernaut/juggernaut_mk2.json (synced from B1's export by
tools/sync_models.py) and writes:
  - data/parts.json: one entry per real part ("jg2_<bone>", real mass, collider = the export's
    own convex hulls by name, read at build time by MechBuilder) and one per leg actuator ("jg2_act_<joint>.<leg>", zero mass since the
    housing part already carries it, real game_motor and test_bench figures from the export,
    plus a linear-equivalent "bench" block so the existing charge-jump maths (which assumes a
    linear ram) keeps working -- reasoned, not measured; lane B6 owns real rotary bench physics).
  - data/mechs.json: the "juggernaut_m2" entry's parts/legs (with each leg's sole socket)/
    stance/cameras/model_origin, and flips "status" from "planned" to "ready".

The RigidBody3D's local origin is the model's "body" bone (chest height, not the ground), the
same convention the stand-in uses (hips sit a bit below the origin). Re-run this after every
`tools/sync_models.py juggernaut` that changes the export's joints or masses.
"""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_JSON = ROOT / "assets" / "models" / "juggernaut" / "juggernaut_mk2.json"
PARTS_JSON = ROOT / "data" / "parts.json"
MECHS_JSON = ROOT / "data" / "mechs.json"

LEGS = ["FR", "FL", "RR", "RL"]
CHAIN_JOINTS = ["hip_yaw", "hip_pitch", "knee", "ankle"]


def sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def dist(a, b):
    return math.dist(a, b)


def segment_frame(a, b):
    """Origin at the midpoint, local Z along a->b, matching scripts/locomotion/leg_ik.gd's
    `segment()` (Basis.looking_at with an UP hint unless the segment is nearly vertical).
    """
    d = sub(b, a)
    length = math.dist([0, 0, 0], d)
    z = [d[0] / length, d[1] / length, d[2] / length]
    up = (0.0, 1.0, 0.0) if abs(z[1]) < 0.98 else (0.0, 0.0, 1.0)
    x = cross(up, z)
    xlen = math.dist([0, 0, 0], x)
    x = [v / xlen for v in x]
    y = cross(z, x)
    origin = [(a[i] + b[i]) * 0.5 for i in range(3)]
    return origin, x, y, z


def cross(a, b):
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def local_extents(hull, origin, x, y, z):
    """Hull point extents along a segment's local axes: how wide/tall/long its box should be."""
    xs, ys, zs = [], [], []
    for p in hull:
        r = sub(p, origin)
        xs.append(dot(r, x))
        ys.append(dot(r, y))
        zs.append(dot(r, z))
    return max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)


def aabb_size(hull):
    xs = [p[0] for p in hull]
    ys = [p[1] for p in hull]
    zs = [p[2] for p in hull]
    return [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]


def main() -> int:
    model = json.loads(MODEL_JSON.read_text())
    joints = {j["bone"]: j for j in model["joints"]}
    parts_by_bone = {}
    for p in model["parts"]:
        parts_by_bone.setdefault(p["bone"], []).append(p)
    sockets = {s["name"]: s for s in model["sockets"]}
    actuators_by_joint = {a["joint"]: a for a in model["actuators"]}

    origin = joints["body"]["head"]  # RigidBody3D local (0,0,0): chest height, x=z=0
    src = f"B1 export from {model['source_blend']}"
    shift = lambda p: [p[0] - origin[0], p[1] - origin[1], p[2] - origin[2]]

    new_parts = {}
    leg_defs = {}

    # --- legs: thigh (upper), shin (lower), foot -------------------------------------------
    for leg in LEGS:
        hip = shift(joints[f"coxa.{leg}"]["head"])
        upper_len = dist(joints[f"thigh.{leg}"]["head"], joints[f"shin.{leg}"]["head"])
        lower_len = dist(joints[f"shin.{leg}"]["head"], joints[f"foot.{leg}"]["head"])

        thigh_hull = parts_by_bone[f"thigh.{leg}"][0]["hull"]
        shin_hull = parts_by_bone[f"shin.{leg}"][0]["hull"]
        foot_hull = parts_by_bone[f"foot.{leg}"][0]["hull"]
        foot_part = parts_by_bone[f"foot.{leg}"][0]

        o, x, y, z = segment_frame(
            joints[f"thigh.{leg}"]["head"], joints[f"shin.{leg}"]["head"]
        )
        tw, th, _ = local_extents(thigh_hull, o, x, y, z)
        o2, x2, y2, z2 = segment_frame(
            joints[f"shin.{leg}"]["head"], joints[f"foot.{leg}"]["head"]
        )
        sw, sh, _ = local_extents(shin_hull, o2, x2, y2, z2)

        thigh_part = parts_by_bone[f"thigh.{leg}"][0]
        shin_part = parts_by_bone[f"shin.{leg}"][0]

        new_parts[f"jg2_thigh_{leg}"] = {
            "kind": "leg_upper",
            "label": "Juggernaut Model 2 thigh (%s)" % leg,
            "mass_kg": round(thigh_part["mass_kg"], 2),
            "health": 1800,
            "armour_mm": 12,
            "length_m": round(upper_len, 5),
            "collider": _hull_collider(thigh_part, [tw * 0.7, th * 0.7, upper_len]),
            "look": {"color": "#5d6670", "mesh": "box"},
            "source": f"{src}: collision is the export's own convex hull; size is the hull bbox in the segment's frame shrunk 30% (inertia and placeholder only)",
        }
        new_parts[f"jg2_shin_{leg}"] = {
            "kind": "leg_lower",
            "label": "Juggernaut Model 2 shin (%s)" % leg,
            "mass_kg": round(shin_part["mass_kg"], 2),
            "health": 1500,
            "armour_mm": 10,
            "length_m": round(lower_len, 5),
            "collider": _hull_collider(shin_part, [sw * 0.7, sh * 0.7, lower_len]),
            "look": {"color": "#4b545d", "mesh": "box"},
            "source": f"{src}: collision is the export's own convex hull; size is the hull bbox in the segment's frame shrunk 30% (inertia and placeholder only)",
        }
        new_parts[f"jg2_foot_{leg}"] = {
            "kind": "foot",
            "label": "Juggernaut Model 2 foot (%s)" % leg,
            "mass_kg": round(foot_part["mass_kg"], 2),
            "health": 900,
            "armour_mm": 14,
            "collider": _hull_collider(foot_part, aabb_size(foot_hull)),
            "look": {"color": "#454c54", "mesh": "box"},
            "source": f"{src}: collision is the export's own convex hull; size is its axis-aligned bbox",
        }

        acts = []
        for joint_kind in CHAIN_JOINTS:
            joint_id = f"{joint_kind}.{leg}"
            act = actuators_by_joint[joint_id]
            part_id = f"jg2_act_{joint_kind}_{leg}"
            new_parts[part_id] = _actuator_entry(
                joint_kind, leg, act, upper_len, lower_len, src
            )
            acts.append(part_id)

        sole = sockets[f"sole_{leg}"]
        leg_defs[leg.lower()] = {
            "hip": [round(v, 5) for v in hip],
            "sole": [round(v, 5) for v in shift(sole["pos"])],
            "sole_normal": sole.get("normal", [0.0, 1.0, 0.0]),
            "pivot": [round(v, 5) for v in shift(joints[f"thigh.{leg}"]["head"])],
            "knee": [round(v, 5) for v in shift(joints[f"shin.{leg}"]["head"])],
            "ankle": [round(v, 5) for v in shift(joints[f"foot.{leg}"]["head"])],
            "rams": _rams(joints, leg, shift),
            "upper": f"jg2_thigh_{leg}",
            "lower": f"jg2_shin_{leg}",
            "foot": f"jg2_foot_{leg}",
            "actuators": acts,
        }

    # --- fixed chassis parts (everything not a leg segment) --------------------------------
    chassis_placements = []
    leg_bones = set()
    for leg in LEGS:
        leg_bones |= {f"thigh.{leg}", f"shin.{leg}", f"foot.{leg}"}
    seen_names = set()
    for p in model["parts"]:
        bone = p.get("bone", "")
        if bone in leg_bones:
            continue
        name = p["name"].removeprefix("JG2_")
        uniq = name
        n = 2
        while uniq in seen_names:
            uniq = f"{name}_{n}"
            n += 1
        seen_names.add(uniq)
        part_id = "jg2_" + uniq.lower().replace(" ", "_").replace(".", "_")
        com = shift(p["com"])
        size = aabb_size(p["hull"])
        new_parts[part_id] = {
            "kind": p["class"],
            "label": "Juggernaut Model 2: %s" % name,
            "mass_kg": round(p["mass_kg"], 2),
            "health": 1000,
            "armour_mm": 6 if p["class"] == "armour" else 0,
            "collider": _hull_collider(p, size),
            "look": {"color": _colour_for(p["class"]), "mesh": "box"},
            "source": f"{src}: collision is the export's own convex hull(s) at the rest pose; size is the axis-aligned hull bbox",
        }
        chassis_placements.append({"part": part_id, "at": [round(v, 5) for v in com]})

    # --- gun elevation actuator (not a leg joint, but a real actuator) ----------------------
    gun_act = actuators_by_joint.get("gun_elevation")
    if gun_act:
        new_parts["jg2_act_gun_elevation"] = _actuator_entry(
            "gun_elevation", "", gun_act, 0.6, 0.6, src
        )

    # --- mechs.json juggernaut_m2 ------------------------------------------------------------
    stance_hip = leg_defs["fr"]["hip"]
    sole_fr = shift(sockets["sole_FR"]["pos"])
    stance = {
        "height_m": round(-sole_fr[1], 4),
        "foot_out_m": round(abs(sole_fr[0] - stance_hip[0]), 4),
        "foot_forward_m": round(abs(sole_fr[2] - stance_hip[2]), 4),
    }
    cameras = {
        "cockpit": [round(v, 4) for v in shift(sockets["cockpit_camera"]["pos"])],
        "eye": [round(v, 4) for v in shift(sockets["eye_camera"]["pos"])],
    }
    sockets_out = {
        name: {"bone": s["bone"], "at": [round(v, 4) for v in shift(s["pos"])]}
        for name, s in sockets.items()
        if name not in ("cockpit_camera", "eye_camera")
    }

    mechs = json.loads(MECHS_JSON.read_text())
    entry = mechs["entries"]["juggernaut_m2"]
    entry["status"] = "ready"
    entry["parts"] = chassis_placements
    entry["legs"] = leg_defs
    entry["stance"] = stance
    entry["cameras"] = cameras
    entry["sockets"] = sockets_out
    entry["model_origin"] = [round(v, 5) for v in origin]
    entry["origin"] = (
        "model2's 'body' bone (chest height); the coxa/thigh/shin/ram meshes stay fixed to it as ordinary chassis parts, and the gun/subarms are locked (see B1.md locked_bones)"
    )
    entry["source"] = (
        f"generated by tools/build_juggernaut_data.py from assets/models/juggernaut/juggernaut_mk2.json ({src}); re-run after every model re-sync"
    )
    MECHS_JSON.write_text(json.dumps(mechs, indent=2) + "\n")

    parts = json.loads(PARTS_JSON.read_text())
    parts["entries"].update(new_parts)
    PARTS_JSON.write_text(json.dumps(parts, indent=2) + "\n")

    print(f"wrote {len(new_parts)} parts.json entries, mechs.json juggernaut_m2 ready")
    print(f"stance: {stance}")
    total = sum(v["mass_kg"] for v in new_parts.values())
    print(
        f"mass check: {total:.1f} kg from generated parts (export total was {model['total_mass_kg']} kg)"
    )
    return 0


def _colour_for(cls: str) -> str:
    return {
        "chassis": "#5d6670",
        "cockpit": "#3b4046",
        "armour": "#6b7580",
        "gun_mech": "#454c54",
        "gun_barrel": "#3a3f45",
        "ammo": "#7a4a2a",
        "sensor": "#2f5c6b",
        "joint": "#4b545d",
        "other": "#565f68",
    }.get(cls, "#5d6670")


def _rams(joints: dict, leg: str, shift) -> list:
    """The leg's knee ram (lane A2 part 5): the cylinder rides the thigh and the rod the shin, each
    turning about its own mount to aim at the other's (B1's ram_*_tgt track constraints).
    """
    cyl, rod = joints.get(f"ram_cyl.{leg}"), joints.get(f"ram_rod.{leg}")
    if not cyl or not rod:
        return []
    c = [round(v, 5) for v in shift(cyl["head"])]
    r = [round(v, 5) for v in shift(rod["head"])]
    return [
        {"part": f"JG2_ramcyl.{leg}", "on": "upper", "mount": c, "aim": r},
        {"part": f"JG2_ramrod.{leg}", "on": "lower", "mount": r, "aim": c},
    ]


def _hull_collider(part: dict, size: list) -> dict:
    """The export's own convex hulls: MechBuilder reads parts[].hulls for `hulls_from` from the
    synced export json (the mech's model_data), so the hull points are not copied into parts.json.
    `size` is the box kept for inertia, the placeholder mesh and the fallback when not synced.
    """
    return {
        "shape": "hulls",
        "hulls_from": part["name"],
        "size": [round(v, 3) for v in size],
    }


def _actuator_entry(
    joint_kind: str, leg: str, act: dict, upper_len: float, lower_len: float, src: str
) -> dict:
    bench = act["test_bench"]
    label_leg = f" ({leg})" if leg else ""
    entry = {
        "kind": "actuator",
        "label": "Juggernaut Model 2 %s actuator%s" % (joint_kind, label_leg),
        "mass_kg": 0.0,
        "health": 500,
        "armour_mm": 0,
        "collider": None,
        "joint": joint_kind,
        "game_motor": joint_kind,  # the shared magic-motor kind in tuning.json "motors" (used by all mechs)
        "game_motor_figures": act[
            "game_motor"
        ],  # this actuator's own real max torque/speed, for B6
        "static_torque_nm": act["static_torque_nm"],
        "bench": dict(bench),
        "source": f"{src} (results/B1.md): static need at a two-leg stance, real motor figures reasoned from that torque",
    }
    # rated_power_w/thermal_mass_j_per_k: the shape the game's actuator contract expects
    # (tests/test_registry.gd), aliased from B1's real figures (results/B1.md: 96 V bus, 65%
    # efficiency, 15 kJ/K heat capacity, 80 K limit -- one thermal mass for every actuator).
    entry["bench"]["rated_power_w"] = bench["power_w"]
    entry["bench"]["thermal_mass_j_per_k"] = 15000.0
    # A linear-equivalent view for the existing charge-jump maths (scripts/locomotion/jump_charge.gd
    # only knows peak_force_n/stroke_m/no_load_speed_m_s/lever_arm_m). Reasoned, not measured; B6
    # replaces this with real rotary bench physics.
    if bench["kind"] == "linear":
        entry["bench"]["peak_force_n"] = bench["rated_force_n"]
        entry["bench"]["no_load_speed_m_s"] = bench["speed_m_s"]
        entry["bench"]["lever_arm_m"] = bench["moment_arm_m"]
        entry["bench"]["stroke_m"] = round(0.4 * lower_len, 3)
        entry["bench"]["efficiency"] = 0.85
    else:
        lever = (
            0.5 * upper_len
            if joint_kind in ("hip_yaw", "hip_pitch")
            else 0.25 * lower_len
        )
        lever = max(lever, 0.05)
        entry["bench"]["lever_arm_m"] = round(lever, 3)
        entry["bench"]["peak_force_n"] = round(bench["rated_torque_nm"] / lever, 1)
        entry["bench"]["no_load_speed_m_s"] = round(bench["speed_rad_s"] * lever, 4)
        entry["bench"]["stroke_m"] = round(0.3 * lever, 3)
        entry["bench"]["efficiency"] = 0.85
    return entry


if __name__ == "__main__":
    raise SystemExit(main())
