"""The third critic's findings of 2026-10-08 (docs/2026-10-08-critic-3.md),
each pinned so it stays fixed: power costs mass in proportion on drives and
on the battery, a drive without a motor takes no power knob, part names are
not free text, a motion's keys must be spread in time, an unreadable
profile file or a range sweep with nothing to sweep gives 4xx, and names
that read like "baseline" are refused."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import web_app
from conftest import every, prof
from exolab import arm, benches, registry


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(web_app.app)


# ----- M2: power x k is k times the watts for k times the mass -----


def test_power_buys_watts_in_proportion_to_mass(reg) -> None:
    """Power x4 on a motor: twice the torque and twice the top speed, so
    four times the watts, for four times the mass and rotor inertia; the
    same as a type knob or a part knob."""
    base = arm.build(reg, "exo_full", None).suit.joints[0]
    assert base.powered and base.inertia > 0
    for p in (
        every(reg, "actuators", "power", 4),
        prof({"parts": {"exo_full/J1": {"power": 4}}}),
    ):
        j = arm.build(reg, "exo_full", p).suit.joints[0]
        assert j.torque_peak == pytest.approx(2 * base.torque_peak)
        assert j.torque_cont == pytest.approx(2 * base.torque_cont)
        assert j.speed_max == pytest.approx(2 * base.speed_max)
        assert j.power_cont == pytest.approx(4 * base.power_cont)
        assert j.mass == pytest.approx(4 * base.mass)
        assert j.remote_mass == pytest.approx(4 * base.remote_mass)
        assert j.inertia == pytest.approx(4 * base.inertia)


def test_no_power_knob_on_a_drive_without_a_motor(reg, client) -> None:
    """A free bearing has no motor: power leaves it alone in the physics,
    is refused on save and is named on a run."""
    lite = arm.build(reg, "exo_lite", None).suit
    j = next(j for j in lite.joints if j.actuator_id == "free_bearing")
    for p in (
        prof({"actuators": {"free_bearing": {"power": 20}}}),
        prof({"parts": {f"exo_lite/{j.key}": {"power": 20}}}),
    ):
        assert arm.build(reg, "exo_lite", p).suit.mass == pytest.approx(lite.mass)
        r = client.put("/api/profiles/passive power", json=p)
        assert r.status_code == 400 and "motor" in r.text
        body = {"model": "exo_lite", "test": "shoulder_hold", "profile": p}
        r = client.post("/api/run", json=body)
        assert r.status_code == 200
        assert any("motor" in w for w in r.json()["warnings"])


def test_part_knobs_a_part_never_reads_are_refused(reg) -> None:
    """A link has no motor and a battery no stiffness: knobs.json says
    which knobs each kind of part reads."""
    for part, knob in (
        ("upper_arm_link", "power"),
        ("upper_arm_cuff", "strength"),
        ("battery", "stiffness"),
    ):
        if part not in reg.part_ids("exo_full", None):
            continue
        _, errors = reg.check_knobs({"parts": {f"exo_full/{part}": {knob: 2}}})
        assert errors and knob in errors[0], (part, knob)
    clean, errors = reg.check_knobs({"parts": {"exo_full/battery": {"power": 2}}})
    assert not errors and clean


# ----- M1: a bigger battery is a heavier battery -----


def test_a_bigger_battery_weighs_more(reg) -> None:
    """Power on the battery is more cells: twice the energy and twice the
    battery mass. Weight alone is dead mass and adds no energy."""
    base = arm.build(reg, "exo_full", None).suit
    big = arm.build(
        reg, "exo_full", prof({"parts": {"exo_full/battery": {"power": 2}}})
    ).suit
    assert big.battery_wh == pytest.approx(2 * base.battery_wh)
    assert big.masses["Battery"] == pytest.approx(2 * base.masses["Battery"])
    heavy = arm.build(
        reg, "exo_full", prof({"parts": {"exo_full/battery": {"weight": 2}}})
    ).suit
    assert heavy.battery_wh == pytest.approx(base.battery_wh)
    assert heavy.masses["Battery"] == pytest.approx(2 * base.masses["Battery"])


# ----- M3: a part's name is a key in the physics, so it is fixed -----


@pytest.mark.parametrize("path", ["shells.0.name", "links.3.name"])
def test_part_names_are_fixed(reg, path) -> None:
    _, errors = reg.check_overrides({"models": {"exo_full": {path: "Battery"}}})
    assert errors and "fixed" in errors[0]


def test_item_names_stay_free(reg) -> None:
    clean, errors = reg.check_overrides({"materials": {"pa12": {"name": "Nylon"}}})
    assert not errors and clean


# ----- L3: id-looking text that builds the item, or that nothing reads -----


@pytest.mark.parametrize(
    "kind, item, path",
    [
        ("actuators", "hydraulic", "kind"),
        ("mechanisms", "girdle_tracking", "girdle.joint"),
    ],
)
def test_id_looking_text_that_is_not_a_pick_stays_fixed(reg, kind, item, path) -> None:
    # hydraulic's kind is also an actuator id but decides how the drive is
    # built; the girdle's joint names its bearing and nothing reads it.
    _, errors = reg.check_overrides({kind: {item: {path: "harmonic_m"}}})
    assert errors and "fixed" in errors[0]


def test_real_id_picks_still_take_an_id(reg) -> None:
    edit = {"mechanisms": {"girdle_tracking": {"joints.0.actuator": "harmonic_m"}}}
    clean, errors = reg.check_overrides(edit)
    assert not errors and clean


def test_free_text_is_short(reg) -> None:
    _, errors = reg.check_overrides({"materials": {"pa12": {"name": "x" * 300}}})
    assert errors and "characters" in errors[0]


# ----- M4: a motion's keys must be spread in time -----


@pytest.mark.parametrize(
    "times",
    [[2.0, 2.0, 2.0, 2.0], [0.0, 1e-300, 2e-300, 0.1], [0.0, 0.5, 0.52, 1.0]],
)
def test_motion_keys_must_be_spread(times) -> None:
    keys = [{"t": t, "elev": 30.0 * i} for i, t in enumerate(times)]
    with pytest.raises(ValueError, match="apart"):
        benches.sample(keys, 60)


def test_squeezed_throw_is_refused(client) -> None:
    p = prof(overrides={"motions": {"throw": {f"keys.{i}.t": 2.0 for i in range(5)}}})
    body = {"model": "exo_full", "test": "shoulder_motions", "profile": p}
    r = client.post("/api/run", json=dict(body, only="throw"))
    assert r.status_code == 400 and "apart" in r.text


# ----- L1: a profile file the server cannot read -----


def test_unreadable_profile_file_is_not_a_500(client) -> None:
    folder = registry.PROFILE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    odd = folder / "isdir.json"
    odd.mkdir()
    try:
        assert "isdir" not in client.get("/api/profiles").json()
        body = {"model": "exo_full", "test": "shoulder_hold", "profile": "isdir"}
        for r in (
            client.get("/api/profiles/isdir"),
            client.post("/api/run", json=body),
            client.post("/api/profiles/isdir/copy", json={"to": "isdir2"}),
            client.put("/api/profiles/isdir", json={}),
        ):
            assert 400 <= r.status_code < 500, (r.status_code, r.text)
    finally:
        odd.rmdir()


# ----- L6: a human range with nothing to sweep -----


@pytest.mark.parametrize(
    "edits",
    [
        {"plane_deg.0": 140, "plane_deg.8": -90},
        {"plane_deg.0": 30, "plane_deg.8": 30},
    ],
)
def test_range_sweep_needs_rising_planes(client, edits) -> None:
    p = prof(overrides={"human": {"rom": edits}})
    body = {"model": "exo_full", "test": "shoulder_rom", "profile": p}
    r = client.post("/api/run", json=body)
    assert r.status_code == 400 and "plane" in r.text


# ----- L8: names that read like "baseline" -----


@pytest.mark.parametrize(
    "name", ["b4seline", "8aseline", "ba5eline", "8a5e1ine", "BASE-LINE"]
)
def test_digit_look_alikes_are_reserved(name) -> None:
    assert registry.reserved(name)


@pytest.mark.parametrize("name", ["baselines", "my baseline", "base 2"])
def test_near_names_are_not_reserved(name) -> None:
    assert not registry.reserved(name)


# ----- limits.json: the game base numbers a stat divides by -----


@pytest.mark.parametrize(
    "path", ["human_sprint_w", "armour.body_area_m2", "armour.ref_mpa"]
)
def test_game_divisors_stay_above_zero(reg, path) -> None:
    _, errors = reg.check_overrides({"game": {"base": {path: 0}}})
    assert errors, path
