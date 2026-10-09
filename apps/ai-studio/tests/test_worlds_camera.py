"""Camera moves: every action moves the picture the way a viewer expects."""

import itertools
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from worlds import camera  # noqa: E402  # pyright: ignore[reportMissingImports]

W, H = 512, 288

# action -> expected (zoom vs 1, content x shift sign, content y shift sign)
EXPECTED = {
    "forward": (1, 0, 0),
    "back": (-1, 0, 0),
    "left": (0, 1, 0),
    "right": (0, -1, 0),
    "turn_left": (0, 1, 0),
    "turn_right": (0, -1, 0),
    "rise": (0, 0, 1),
    "sink": (0, 0, -1),
    "look_up": (0, 0, 1),
    "look_down": (0, 0, -1),
    "stay": (0, 0, 0),
}


def sign(v, eps=1e-9):
    return 0 if abs(v) < eps else (1 if v > 0 else -1)


def test_every_action_has_an_expectation():
    assert set(EXPECTED) == set(camera.ACTIONS)


@pytest.mark.parametrize("action", sorted(EXPECTED))
@pytest.mark.parametrize("yaw_deg", [-170, -90, -20, 0, 35, 90, 180])
def test_warp_direction_for_every_action_and_heading(action, yaw_deg):
    start = dict(camera.START, yaw=math.radians(yaw_deg), x=3.0, z=-2.0)
    poses, end = camera.plan_chunk(start, [action], 9)
    zoom, ux, uy = camera.warp(start, end, W, H)
    assert (sign(zoom - 1), sign(ux), sign(uy)) == EXPECTED[action]


def test_plan_chunk_starts_at_start_and_ends_at_end():
    for actions in itertools.product(["forward", "turn_left", "rise"], repeat=2):
        poses, end = camera.plan_chunk(camera.START, list(actions), 17)
        assert len(poses) == 17
        assert poses[0] == camera.START
        for k in end:
            assert poses[-1][k] == pytest.approx(end[k], abs=1e-9)


def test_tcw_is_a_rigid_world_to_camera_matrix():
    for x, yaw, pitch in itertools.product(
        [-2.0, 0.0, 5.0], [-2.0, 0.0, 1.3], [-0.5, 0.0, 0.7]
    ):
        pose = {"x": x, "y": -1.0, "z": 2.0, "yaw": yaw, "pitch": pitch}
        m = camera.tcw(pose)
        r = [m[0:3], m[4:7], m[8:11]]
        t = [m[3], m[7], m[11]]
        for i, j in itertools.product(range(3), repeat=2):
            dot = sum(r[i][k] * r[j][k] for k in range(3))
            assert dot == pytest.approx(1.0 if i == j else 0.0, abs=1e-9)
        centre = [pose["x"], pose["y"], pose["z"]]
        cam = [sum(r[i][k] * centre[k] for k in range(3)) + t[i] for i in range(3)]
        assert cam == pytest.approx([0, 0, 0], abs=1e-9)
        assert m[12:] == [0.0, 0.0, 0.0, 1.0]


def test_identity_pose_is_identity_matrix():
    assert camera.tcw(camera.START) == pytest.approx(
        [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    )


def test_affine_keeps_centre_when_only_zooming():
    a, b, c, d, e, f = camera.affine_for_pil(2.0, 0.0, 0.0, W, H)
    assert (a * W / 2 + b * H / 2 + c, d * W / 2 + e * H / 2 + f) == pytest.approx(
        (W / 2, H / 2)
    )


@pytest.mark.parametrize("bad", [[], ["fly"], "forward", None])
def test_bad_actions_are_refused(bad):
    with pytest.raises(ValueError):
        camera.check_actions(bad)
