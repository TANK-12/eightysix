"""Camera moves for world sessions: key actions -> per-frame camera poses.

Stdlib only, so world workers in other virtualenvs can copy it. Conventions
follow OpenCV: x right, y down, z forward. ``yaw`` > 0 turns right, ``pitch``
> 0 looks up. Distances are in "steps" (one forward action moves one step).
"""

import math

STEP = 1.0  # distance one move action covers
TURN = math.radians(20)  # angle one turn action covers
FOV = math.radians(60)  # horizontal field of view assumed for 2D warps
SCENE_DEPTH = 4.0  # assumed distance to the scene, for 2D warps

# action -> (dx, dy, dz in camera space, dyaw, dpitch) for one whole action.
ACTIONS = {
    "forward": (0.0, 0.0, STEP, 0.0, 0.0),
    "back": (0.0, 0.0, -STEP, 0.0, 0.0),
    "left": (-STEP, 0.0, 0.0, 0.0, 0.0),
    "right": (STEP, 0.0, 0.0, 0.0, 0.0),
    "rise": (0.0, -STEP, 0.0, 0.0, 0.0),
    "sink": (0.0, STEP, 0.0, 0.0, 0.0),
    "turn_left": (0.0, 0.0, 0.0, -TURN, 0.0),
    "turn_right": (0.0, 0.0, 0.0, TURN, 0.0),
    "look_up": (0.0, 0.0, 0.0, 0.0, TURN),
    "look_down": (0.0, 0.0, 0.0, 0.0, -TURN),
    "stay": (0.0, 0.0, 0.0, 0.0, 0.0),
}

# Plain button labels for the player.
ACTION_LABELS = {
    "forward": "Walk forward",
    "back": "Walk back",
    "left": "Step left",
    "right": "Step right",
    "rise": "Go up",
    "sink": "Go down",
    "turn_left": "Turn left",
    "turn_right": "Turn right",
    "look_up": "Look up",
    "look_down": "Look down",
    "stay": "Stay and look",
}

START = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0, "pitch": 0.0}


def check_actions(actions):
    """Return the list of actions, or raise ValueError naming a bad one."""
    if not isinstance(actions, (list, tuple)) or not actions:
        raise ValueError("Pick at least one move")
    for a in actions:
        if a not in ACTIONS:
            raise ValueError(f"Unknown move: {a}")
    return list(actions)


def _rot_cw(yaw, pitch):
    """Camera-to-world rotation (3x3, rows) for a yaw then a pitch."""
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    ry = [[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]]
    rx = [[1.0, 0.0, 0.0], [0.0, cp, -sp], [0.0, sp, cp]]
    return [
        [sum(ry[i][k] * rx[k][j] for k in range(3)) for j in range(3)] for i in range(3)
    ]


def _apply(pose, move, fraction):
    dx, dy, dz, dyaw, dpitch = (v * fraction for v in move)
    r = _rot_cw(pose["yaw"], 0.0)  # moves stay level: walking ignores pitch
    return {
        "x": pose["x"] + r[0][0] * dx + r[0][1] * dy + r[0][2] * dz,
        "y": pose["y"] + r[1][0] * dx + r[1][1] * dy + r[1][2] * dz,
        "z": pose["z"] + r[2][0] * dx + r[2][1] * dy + r[2][2] * dz,
        "yaw": pose["yaw"] + dyaw,
        "pitch": max(-1.2, min(1.2, pose["pitch"] + dpitch)),
    }


def plan_chunk(pose, actions, frames):
    """Poses for ``frames`` frames that play ``actions`` one after another.

    Frame 0 is the starting pose; the last frame has finished every action.
    Returns (poses, end_pose).
    """
    actions = check_actions(actions)
    if frames < 2:
        raise ValueError("A step needs at least two frames")
    span = (frames - 1) / len(actions)
    poses = [dict(pose)]
    starts = [dict(pose)]
    for a in actions:
        starts.append(_apply(starts[-1], ACTIONS[a], 1.0))
    for i in range(1, frames):
        t = i / span
        idx = min(int(t), len(actions) - 1)
        poses.append(_apply(starts[idx], ACTIONS[actions[idx]], t - idx))
    return poses, starts[-1]


def tcw(pose):
    """World-to-camera 4x4 matrix (row-major, 16 floats), OpenCV style."""
    r = _rot_cw(pose["yaw"], pose["pitch"])
    rt = [[r[j][i] for j in range(3)] for i in range(3)]
    c = (pose["x"], pose["y"], pose["z"])
    t = [-sum(rt[i][k] * c[k] for k in range(3)) for i in range(3)]
    return [*rt[0], t[0], *rt[1], t[1], *rt[2], t[2], 0.0, 0.0, 0.0, 1.0]


def relative(start, pose):
    """Motion from ``start`` to ``pose`` in the start camera's frame:
    (dx, dy, dz, dyaw, dpitch)."""
    r = _rot_cw(start["yaw"], 0.0)
    d = (pose["x"] - start["x"], pose["y"] - start["y"], pose["z"] - start["z"])
    local = [sum(r[k][i] * d[k] for k in range(3)) for i in range(3)]
    return (*local, pose["yaw"] - start["yaw"], pose["pitch"] - start["pitch"])


def warp(start, pose, width, height):
    """2D stand-in for a camera move, for a flat picture.

    Returns (zoom, ux, uy): scale about the centre and how far the content
    moves, in pixels (x right, y down). Forward zooms in, back zooms out,
    turning or stepping left moves the content right, and so on.
    """
    dx, dy, dz, dyaw, dpitch = relative(start, pose)
    f = (width / 2) / math.tan(FOV / 2)
    depth = SCENE_DEPTH
    zoom = depth / max(depth - dz, depth * 0.25)
    zoom = max(0.4, min(4.0, zoom))
    ux = -dx * f / depth - f * math.tan(dyaw)
    uy = -dy * f / depth + f * math.tan(dpitch)
    return zoom, ux, uy


def affine_for_pil(zoom, ux, uy, width, height):
    """PIL ``Image.AFFINE`` data mapping output pixels to input pixels."""
    cx, cy = width / 2, height / 2
    inv = 1.0 / zoom
    return (inv, 0.0, cx - (cx + ux) * inv, 0.0, inv, cy - (cy + uy) * inv)
