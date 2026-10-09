"""The test benches on the two built suits, and what the knobs do to them."""

from __future__ import annotations

import json
import math

import pytest
from conftest import every, prof

from exolab import arm, benches, derive

READY = ("exo_full", "exo_lite")


def run(reg, model: str, test: str, profile: dict | None = None) -> dict:
    rig = arm.build(reg, model, profile)
    return benches.run(rig, reg.effective("tests", test, profile), reg)


@pytest.fixture(scope="module")
def base(reg) -> dict:
    return {(m, t): run(reg, m, t) for m in READY for t in reg.ids("tests")}


def worst_load(res: dict) -> int:
    return max(max(r["load_pct"].values(), default=0) for r in res["rows"])


def worst_sag(res: dict) -> float:
    return max(r["hand_sag_mm"] for r in res["rows"])


def test_every_built_suit_runs_every_test(reg, base) -> None:
    assert len(base) == len(READY) * len(reg.ids("tests")) >= 8
    for (model, test), res in base.items():
        assert res["verdict"] in benches.LEVELS, (model, test)
        # "out" is a neutral card (close_fit's body self-contact: not the suit's fault).
        assert res["cards"] and all(
            c["level"] in (*benches.LEVELS, "out") for c in res["cards"]
        )
        assert res["model"] == model and res["test"] == test
        json.dumps(res, allow_nan=False)  # no NaN or infinity reaches the page


def test_every_test_kind_has_a_bench(reg) -> None:
    for t in reg.ids("tests"):
        assert reg.get("tests", t)["kind"] in benches.KINDS


def test_unknown_test_kind_is_refused(reg) -> None:
    with pytest.raises(ValueError, match="no bench"):
        benches.run(arm.build(reg, "exo_lite", None), {"kind": "teleport"}, reg)


def test_full_suit_follows_the_shoulder(base) -> None:
    m = base[("exo_full", "shoulder_rom")]["metrics"]
    assert m["followed_pct"] >= 95
    assert m["worst_misalign_mm"] < 10


def test_girdle_tracking_beats_a_fixed_gimbal(reg) -> None:
    def misalign(mech: str) -> float:
        over = {"models": {"exo_lite": {"shoulder.mechanism": mech}}}
        res = run(reg, "exo_lite", "shoulder_rom", prof(overrides=over))
        return res["metrics"]["worst_misalign_mm"]

    assert misalign("tilted_gimbal") > misalign("girdle_tracking") + 20


def test_rom_map_covers_the_reachable_range(base) -> None:
    cells = base[("exo_full", "shoulder_rom")]["map"]["cells"]
    levels = {c["level"] for c in cells}
    assert "out" in levels and "pass" in levels
    assert levels <= {"out", *benches.LEVELS}


def test_more_power_lowers_motor_load(reg, base) -> None:
    for model in READY:
        # power x4 is twice the torque on drives four times the mass
        res = run(reg, model, "shoulder_hold", every(reg, "actuators", "power", 4))
        assert worst_load(res) < 0.7 * worst_load(base[(model, "shoulder_hold")])


def test_softer_materials_sag_more(reg, base) -> None:
    for model in READY:
        res = run(
            reg, model, "shoulder_hold", every(reg, "materials", "stiffness", 0.2)
        )
        assert worst_sag(res) > 2 * worst_sag(base[(model, "shoulder_hold")])


def test_motions_report_every_motion(reg, base) -> None:
    params = reg.get("tests", "shoulder_motions").get("params", {})
    want = list(params.get("motions", reg.ids("motions")))
    for model in READY:
        res = base[(model, "shoulder_motions")]
        assert [m["id"] for m in res["motions"]] == want and len(want) >= 3
        assert all(m["frames"] for m in res["motions"])


def test_strength_mode_needs_load_bearing_gauntlets(reg) -> None:
    full = derive.derive(reg, "exo_full", None)["strength"]
    lite = derive.derive(reg, "exo_lite", None)["strength"]
    assert full["strength_lift_kg"] > full["lift_kg"] > 5
    assert lite["strength_lift_kg"] == lite["lift_kg"]


def test_stronger_materials_raise_the_break_load(reg) -> None:
    for model in READY:
        before = derive.derive(reg, model, None)["strength"]["break_kg"]
        after = derive.derive(reg, model, every(reg, "materials", "strength", 2))
        assert after["strength"]["break_kg"] > 1.5 * before


def test_derived_stats_are_finite(reg) -> None:
    for model in READY:
        json.dumps(derive.derive(reg, model, None), allow_nan=False)


def test_rom_cells_point_the_right_way(base) -> None:
    """The reach dome: every reachable cell has a unit direction in the body
    frame, and the map says where the shoulder is and how long the arm is."""
    mp = base[("exo_full", "shoulder_rom")]["map"]
    cells = {(c["plane"], c["elev"]): c for c in mp["cells"]}
    for c in mp["cells"]:
        assert abs(math.hypot(*c["dir"]) - 1) < 1e-3
    near = lambda a, b: all(abs(x - y) < 1e-3 for x, y in zip(a, b))  # noqa: E731
    assert near(cells[(90.0, 90.0)]["dir"], [0, 0, 1])  # straight ahead
    assert near(cells[(0.0, 0.0)]["dir"], [0, -1, 0])  # hanging down
    assert near(cells[(0.0, 90.0)]["dir"], [-1, 0, 0])  # out to her right
    assert 0.3 < mp["reach_m"] < 0.8
    assert len(mp["gh"]) == 3 and 1.0 < mp["gh"][1] < 1.6


def _angle_to_axis(lay: dict) -> float:
    """Angle between the upper arm and the first motor axis, folded under 90."""
    u = [e - c for e, c in zip(lay["elbow"], lay["centre"])]
    n = math.hypot(*u)
    dot = abs(sum(a * b / n for a, b in zip(u, lay["axes"][0])))
    return math.degrees(math.acos(min(1.0, dot)))


def test_lock_cones_agree_with_the_lock_check(reg) -> None:
    """The cones drawn round the first axis are the lock zone the check uses:
    a frame fails on lock exactly when the arm lies inside the fail cone."""
    over = {"models": {"exo_lite": {"shoulder.mechanism": "lateral_gimbal"}}}
    rig = arm.build(reg, "exo_lite", prof(overrides=over))
    rules = benches.rules_for(rig, {})
    locked = agree = 0
    for pl in range(-90, 141, 5):
        for el in range(0, 181, 5):
            fr = arm.kinematics(rig, pl, el, 0.0, 30.0, 0.0)
            ld = arm.loads(rig, fr)
            issues = benches.check(rig, fr, ld, rules)
            lay = benches.layout(rig, fr, rules)
            ang = _angle_to_axis(lay)
            if abs(ang - lay["lock"]["fail_deg"]) < 0.3:
                continue
            fails = any(i["code"] == "lock" and i["level"] == "fail" for i in issues)
            assert (ang < lay["lock"]["fail_deg"]) == fails, (pl, el, ang)
            locked += fails
            agree += 1
    assert locked >= 1 and agree > 1000
    fr = arm.kinematics(rig, 0, 90, 0.0, 30.0, 0.0)
    lock = benches.layout(rig, fr, rules)["lock"]
    assert lock["warn_deg"] == pytest.approx(8.63, abs=0.01)
    assert lock["fail_deg"] == pytest.approx(2.87, abs=0.01)
    assert 0.2 < lock["length"] < 0.5
    over = {"models": {"exo_lite": {"shoulder.mechanism": "soft_cable"}}}
    cable = arm.build(reg, "exo_lite", prof(overrides=over))
    fr = arm.kinematics(cable, 0, 90, 0.0, 30.0, 0.0)
    assert "lock" not in benches.layout(cable, fr)
