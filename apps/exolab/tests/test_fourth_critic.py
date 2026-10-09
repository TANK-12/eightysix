"""The fourth critic's findings of 2026-10-08 (docs/2026-10-08-critic-4.md),
each pinned so it stays fixed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import web_app
from conftest import prof
from exolab import arm, benches, registry


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(web_app.app)


def _run(client: TestClient, model: str, test: str, p: dict, **extra) -> dict:
    r = client.post("/api/run", json=dict(model=model, test=test, profile=p, **extra))
    assert r.status_code == 200, r.text
    return r.json()


def _card(result: dict, title: str) -> dict:
    return next(c for c in result["cards"] if c["title"] == title)


# ----- C4-M1: keys exactly 0.05 s apart are allowed -----


@pytest.mark.parametrize("pair", [(0.25, 0.3), (0.9, 0.95), (1.1, 1.15)])
def test_keys_exactly_the_minimum_apart_pass(pair) -> None:
    a, b = pair
    keys = [{"t": 0.0}, {"t": a, "elev": 30.0}, {"t": b, "elev": 40.0}]
    keys.append({"t": 1.5, "elev": 0.0})
    assert benches.sample(keys, 30)


def test_keys_under_the_minimum_say_so() -> None:
    keys = [{"t": 0.0}, {"t": 0.9, "elev": 30.0}, {"t": 0.949, "elev": 40.0}]
    with pytest.raises(ValueError, match=r"0\.049 s apart"):
        benches.sample(keys + [{"t": 1.5}], 30)


def test_throw_with_a_key_at_the_minimum_runs(client) -> None:
    p = prof(overrides={"motions": {"throw": {"keys.1.t": 0.9}}})
    _run(client, "exo_full", "shoulder_motions", p, only="throw")


# ----- C4-M2: the lift card times the lift by its last key in time -----


@pytest.mark.parametrize(
    "swap, cycle", [({"3": 0.0, "0": 3.5}, "3.5"), ({"3": 0.5}, "2.0")]
)
def test_lift_card_uses_the_motions_end(client, swap, cycle) -> None:
    edits = {f"params.keys.{i}.t": t for i, t in swap.items()}
    p = prof(overrides={"tests": {"lift_cycle": edits}})
    card = _card(_run(client, "exo_full", "lift_cycle", p), "Lifts per charge")
    assert f"{cycle} s a lift" in card["text"]


def _put(client: TestClient, name: str, p: dict) -> tuple[int, str]:
    r = client.put(f"/api/profiles/{name}", json=p)
    return r.status_code, r.text


# ----- C4-M3: the cuff liner is no pick (nothing models it) -----


def test_cuff_liner_is_fixed(client) -> None:
    p = prof(overrides={"models": {"exo_full": {"cuffs.0.liner": "steel_4340"}}})
    code, text = _put(client, "liner", p)
    assert code == 400 and "fixed" in text, text


# ----- C4-L1: "has a motor" comes from knobs.json, not a list in the physics -----


def test_typed_torque_gives_a_bearing_no_motor(reg) -> None:
    typed = prof(
        overrides={
            "actuators": {"free_bearing": {"torque_cont_nm": 50, "torque_peak_nm": 100}}
        }
    )
    sags = []
    for p in (prof(), typed):
        rig = arm.build(reg, "exo_lite", p)
        j3 = rig.suit.joints[2]
        assert j3.actuator_id == "free_bearing" and not j3.motor and not j3.powered
        fr = arm.kinematics(rig, 90.0, 90.0, 0.0, 0.0, 5.0)
        sags.append(arm.loads(rig, fr)["hand_sag_mm"])
    assert sags[0] == pytest.approx(sags[1])


def test_a_motor_drive_still_has_a_motor(reg) -> None:
    j1 = arm.build(reg, "exo_full", prof()).suit.joints[0]
    assert j1.motor and j1.powered


# ----- C4-L2: a passive drive takes only the knobs it has something for -----


@pytest.mark.parametrize(
    "knobs, ok",
    [
        ({"parts": {"exo_lite/J3": {"stiffness": 4}}}, False),
        ({"parts": {"exo_lite/J3": {"strength": 0.25}}}, False),
        ({"parts": {"exo_lite/J3": {"weight": 2}}}, True),
        ({"parts": {"exo_lite/knee": {"strength": 0.5}}}, False),
        ({"parts": {"exo_lite/knee": {"weight": 2}}}, True),
        ({"actuators": {"free_bearing": {"strength": 4}}}, False),
        ({"actuators": {"free_bearing": {"stiffness": 4}}}, False),
        ({"actuators": {"free_bearing": {"weight": 2}}}, True),
        ({"actuators": {"spring_balance": {"stiffness": 2}}}, False),
        ({"actuators": {"spring_balance": {"strength": 0.5}}}, True),
        ({"parts": {"exo_full/J1": {"stiffness": 2, "power": 2}}}, True),
    ],
)
def test_passive_drives_take_only_live_knobs(client, knobs, ok) -> None:
    code, text = _put(client, "passive-knobs", prof(knobs=knobs))
    assert (code == 200) == ok, text


def test_a_weaker_spring_carries_less(reg) -> None:
    """Strength on a spring is the one knob besides weight that it reads:
    lowered, it caps the spring's torque on an arm joint."""
    swap = {"models": {"exo_lite": {"elbow.actuator": "spring_balance"}}}
    weak = prof({"actuators": {"spring_balance": {"strength": 0.25}}}, swap)
    out = []
    for p in (prof(overrides=swap), weak):
        rig = arm.build(reg, "exo_lite", p)
        fr = arm.kinematics(rig, 90.0, 0.0, 0.0, 90.0, 5.0)
        out.append(arm.loads(rig, fr)["unpowered_nm"])
    assert out[1] > out[0]


# ----- C4-L3: a profile that saves also runs -----


@pytest.mark.parametrize(
    "overrides, says",
    [
        ({"human": {"rom": {"plane_deg.0": -60}}}, "must rise"),
        ({"human": {"rom": {"plane_deg.0": 140, "plane_deg.8": -90}}}, "must rise"),
        ({"motions": {"throw": {"keys.1.t": 0.92}}}, "apart"),
        ({"tests": {"lift_cycle": {"params.keys.2.t": 1.52}}}, "apart"),
    ],
)
def test_cross_field_problems_are_refused_on_save(client, overrides, says) -> None:
    code, text = _put(client, "cross", prof(overrides=overrides))
    assert code == 400 and says in text, text


def test_edits_that_keep_the_rules_still_save(client) -> None:
    edits = {
        "human": {"rom": {"plane_deg.0": -80}},
        "motions": {"throw": {"keys.1.t": 0.9}},
        "tests": {"lift_cycle": {"params.keys.2.t": 1.55}},
    }
    code, text = _put(client, "cross-ok", prof(overrides=edits))
    assert code == 200, text


# ----- C4-L4: a range sweep over a sliver of the range is no clean pass -----


def test_full_range_is_all_tested(client) -> None:
    res = _run(client, "exo_full", "shoulder_rom", prof())
    card = _card(res, "Range tested")
    assert card["level"] == "pass" and card["value"] == "100%"


@pytest.mark.parametrize(
    "rom",
    [
        {f"max_elevation_deg.{i}": 0 for i in range(9)},
        {f"plane_deg.{i}": 29 + 0.2 * i for i in range(9)},
    ],
)
def test_a_trivial_sweep_says_how_little_it_tested(client, rom) -> None:
    res = _run(
        client, "exo_full", "shoulder_rom", prof(overrides={"human": {"rom": rom}})
    )
    card = _card(res, "Range tested")
    assert card["level"] == "warn" and "says little" in card["text"]
    assert res["verdict"] != "pass"


# ----- C4-L5: the model says which knobs each part reads now -----


def test_model_lists_part_knobs(client) -> None:
    base = client.post("/api/model", json={"model": "exo_full", "profile": prof()})
    assert "power" in base.json()["part_knobs"]["J1"]
    swap = prof(
        overrides={
            "mechanisms": {"girdle_tracking": {"joints.0.actuator": "free_bearing"}}
        }
    )
    got = client.post("/api/model", json={"model": "exo_full", "profile": swap})
    assert got.json()["part_knobs"]["J1"] == ["weight"]
    lite = client.post("/api/model", json={"model": "exo_lite", "profile": prof()})
    assert lite.json()["part_knobs"]["knee"] == ["weight"]


# ----- C4-L6: digit look-alikes of "baseline" -----


@pytest.mark.parametrize("name", ["6aseline", "base7ine", "8a5e11ne", "Base1ine"])
def test_digit_look_alikes_are_refused(client, name) -> None:
    assert _put(client, name, prof())[0] == 400


def test_a_name_that_only_starts_like_baseline_saves(client) -> None:
    assert _put(client, "baseline2", prof())[0] == 200


# ----- C4-L7: a failed save leaves no temp file -----


def test_failed_save_leaves_no_temp_file(client) -> None:
    folder = registry.profile_path("isdir")
    folder.mkdir(parents=True)
    try:
        assert _put(client, "isdir", prof())[0] == 400
        assert not folder.with_suffix(".tmp").exists()
    finally:
        folder.rmdir()
