"""Hostile and careless input: the critic's findings of 2026-10-08, each
pinned so it stays fixed. No typed number may crash a run, every knob must
reach a judged result, and the API answers 4xx, never 500, for bad input."""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

import web_app
from exolab import arm, benches, registry


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(web_app.app)


def _run(reg, model: str, test: str, prof: dict | None = None) -> dict:
    rig = arm.build(reg, model, prof)
    return benches.run(rig, reg.effective("tests", test, prof), reg)


# ----- typed numbers stay inside data/limits.json -----

BAD_OVERRIDES = [
    ("models", "exo_full", "cuffs.0.width_mm", 0),
    ("models", "exo_full", "cuffs.0.gap_mm", -42),
    ("models", "exo_full", "links.2.section.d_mm", 0),
    ("tests", "shoulder_rom", "params.plane_step", 0),
    ("tests", "shoulder_rom", "params.plane_step", 0.01),
    ("tests", "lift_cycle", "params.fps", 0),
    ("tests", "shoulder_motions", "params.fps", 100000),
    ("actuators", "harmonic_s", "speed_max_rad_s", 0),
    ("materials", "al_7075_t6", "density_kg_m3", -1),
]


@pytest.mark.parametrize("kind,item,path,value", BAD_OVERRIDES)
def test_out_of_range_overrides_are_refused(reg, kind, item, path, value) -> None:
    clean, errors = reg.check_overrides({kind: {item: {path: value}}})
    assert clean == {} and len(errors) == 1
    assert "must be between" in errors[0]


def test_a_zero_gap_is_still_allowed(reg) -> None:
    clean, errors = reg.check_overrides({"models": {"exo_full": {"cuffs.0.gap_mm": 0}}})
    assert errors == [] and clean["models"]["exo_full"]["cuffs.0.gap_mm"] == 0


def test_unlisted_fields_keep_sign_and_size(reg) -> None:
    assert reg.limit("materials", "not_listed", 5.0) == (0.0, 5000.0)
    assert reg.limit("materials", "not_listed", 0.0) == (0.0, 1000.0)
    assert reg.limit("materials", "not_listed", -60.0) == (-60000.0, 60000.0)
    assert reg.limit("models", "cuffs.7.width_mm", 1.0) == (10.0, 300.0)


def test_every_limit_names_a_field_and_holds_its_baseline(reg) -> None:
    def leaves(o, p=""):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from leaves(v, f"{p}.{k}" if p else k)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from leaves(v, f"{p}.{i}" if p else str(i))
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            yield p, o

    for kind, pats in reg.limits.items():
        if kind in ("about", "text"):
            continue
        found = {pat: 0 for pat in pats}
        for item in reg.items[kind].values():
            for path, value in leaves(item):
                lo, hi = reg.limit(kind, path, value)
                assert lo <= value <= hi, (kind, item["id"], path)
                for pat in pats:
                    keys, ps = path.split("."), pat.split(".")
                    if len(ps) == len(keys) and all(
                        a in ("*", b) for a, b in zip(ps, keys)
                    ):
                        found[pat] += 1
        derived = reg.knobs.get("derived", {}).get(kind, {})
        assert [p for p, n in found.items() if not n and p not in derived] == []


def test_negative_list_positions_are_no_field(reg) -> None:
    _, errors = reg.check_overrides(
        {"mechanisms": {"girdle_tracking": {"joints.-1.actuator": "harmonic_s"}}}
    )
    assert errors and "no such field" in errors[0]
    assert registry.get_path({"a": [1, 2]}, "a.-1", "none") == "none"


# ----- knobs -----


@pytest.mark.parametrize("bad", [[1], "x", 5])
def test_knobs_must_be_an_object(reg, bad) -> None:
    clean, errors = registry.clean_profile("t", {"knobs": bad}, reg)
    assert clean["knobs"] == {} and errors == ["knobs must be an object"]


def test_knobs_must_name_real_items_and_knobs(reg) -> None:
    raw = {
        "materials": {
            "no_such_item": {"power": 3},
            "pa12": {"power": 2, "weight": "x"},
        },
        "nokind": {"a": {"power": 2}},
        "parts": {"exo_full/J1": {"power": 2}, "no_model/J1": {"power": 2}},
    }
    clean, errors = reg.check_knobs(raw)
    assert clean == {"parts": {"exo_full/J1": {"power": 2.0}}}
    text = " | ".join(errors)
    for why in (
        "no materials item 'no_such_item'",
        "materials/pa12: no 'power' knob",
        "materials/pa12 weight: must be a number",
        "no knobs for 'nokind'",
        "no parts item 'no_model/J1'",
    ):
        assert why in text


def test_power_is_a_bigger_motor_all_round(reg) -> None:
    base = arm.build(reg, "exo_full", None).suit.joints[0]
    act = base.actuator_id
    for p in (1.5, 2.0, 20.0):
        prof = {"knobs": {"actuators": {act: {"power": p}}}}
        j = arm.build(reg, "exo_full", prof).suit.joints[0]
        # torque goes up by the square root: power x4 is twice the torque
        assert j.torque_peak == pytest.approx(base.torque_peak * p**0.5)
        assert j.torque_cont == pytest.approx(base.torque_cont * p**0.5)
        assert j.torque_cont <= j.torque_peak
        part = {"knobs": {"parts": {"exo_full/J1": {"power": p}}}}
        k = arm.build(reg, "exo_full", part).suit.joints[0]
        assert k.torque_peak == pytest.approx(base.torque_peak * p**0.5)
        assert k.torque_cont <= k.torque_peak


def test_a_weak_gearbox_caps_continuous_torque_too(reg) -> None:
    base = arm.build(reg, "exo_full", None).suit.joints[0]
    prof = {"knobs": {"actuators": {base.actuator_id: {"strength": 0.05}}}}
    j = arm.build(reg, "exo_full", prof).suit.joints[0]
    assert j.torque_peak < base.torque_peak and j.torque_cont <= j.torque_peak


# ----- every knob reaches a judged result -----


def test_hand_sag_is_judged_so_stiffness_matters(reg) -> None:
    def sag_issues(res: dict) -> list[dict]:
        return [i for r in res["rows"] for i in r["issues"] if i["code"] == "sag"]

    assert sag_issues(_run(reg, "exo_full", "shoulder_hold")) == []
    soft = {
        "knobs": {"materials": {m: {"stiffness": 0.05} for m in reg.ids("materials")}}
    }
    res = _run(reg, "exo_full", "shoulder_hold", soft)
    assert any(i["level"] == "fail" for i in sag_issues(res))
    assert res["verdict"] == "fail"


def test_a_zero_size_strut_is_an_error_not_a_clean_hold(reg) -> None:
    raw = {"overrides": {"models": {"exo_full": {"links.2.section.d_mm": 0}}}}
    with pytest.raises(ValueError, match="no cross-section"):
        _run(reg, "exo_full", "shoulder_hold", raw)


# ----- bench verdicts -----


def _gimbal(model: str) -> dict:
    return {"overrides": {"models": {model: {"shoulder.mechanism": "tilted_gimbal"}}}}


def test_worst_misalignment_card_can_fail(reg) -> None:
    res = _run(reg, "exo_lite", "shoulder_rom", _gimbal("exo_lite"))
    card = next(c for c in res["cards"] if c["title"] == "Worst misalignment")
    assert res["metrics"]["worst_misalign_mm"] > 30 and card["level"] == "fail"


def test_a_failing_card_keeps_the_rom_headline_off_pass(reg) -> None:
    prof = _gimbal("exo_lite")
    prof["overrides"]["tests"] = {
        "shoulder_rom": {"rules.followed_pass_pct": 0, "rules.followed_warn_pct": 0}
    }
    res = _run(reg, "exo_lite", "shoulder_rom", prof)
    assert res["cards"][0]["level"] == "pass" and res["verdict"] == "warn"


def test_swapping_in_the_cable_keeps_its_own_drive(reg) -> None:
    own = reg.get("mechanisms", "soft_cable")["joints"][0]["actuator"]
    prof = {"overrides": {"models": {"exo_lite": {"shoulder.mechanism": "soft_cable"}}}}
    assert arm.build(reg, "exo_lite", prof).suit.joints[0].actuator_id == own
    assert (
        arm.build(reg, "exo_lite", None).suit.joints[0].actuator_id == "qdd_planetary"
    )


def test_motions_only_must_name_a_motion(reg) -> None:
    rig = arm.build(reg, "exo_full", None)
    test = reg.effective("tests", "shoulder_motions", None)
    test["params"]["only"] = "nope"
    with pytest.raises(KeyError, match="no motion named 'nope'"):
        benches.run(rig, test, reg)


def test_a_lift_with_nothing_powered_says_so(reg) -> None:
    free = {f"joints.{i}.actuator": "free_bearing" for i in range(3)}
    prof = {
        "overrides": {
            "mechanisms": {"girdle_tracking": free},
            "models": {"exo_full": {"elbow.actuator": "free_bearing"}},
        }
    }
    res = _run(reg, "exo_full", "lift_cycle", prof)
    assert res["lifts_per_charge"] is None
    card = next(c for c in res["cards"] if c["title"] == "Lifts per charge")
    assert card["value"] == "no draw" and card["level"] == "warn"
    json.dumps(res, allow_nan=False)


# ----- profile names -----


@pytest.mark.parametrize("name", ["abc\n", "trailing ", "dot.", "Baseline", "BASELINE"])
def test_lookalike_and_trailing_names_are_refused(reg, name) -> None:
    with pytest.raises(ValueError):
        registry.save_profile(name, {}, reg)


def test_ordinary_names_still_save(reg) -> None:
    assert registry.save_profile("My suit 2", {}, reg)["name"] == "My suit 2"
    assert registry.save_profile("a", {}, reg)["name"] == "a"


# ----- over HTTP: 4xx, never 500 -----


@pytest.mark.parametrize("kind,item,path,value", BAD_OVERRIDES)
def test_bad_numbers_come_back_as_warnings(client, kind, item, path, value) -> None:
    model = "exo_full"
    test = item if kind == "tests" else "shoulder_hold"
    prof = {"name": "baseline", "overrides": {kind: {item: {path: value}}}}
    r = client.post("/api/run", json={"model": model, "test": test, "profile": prof})
    assert r.status_code == 200
    assert any("must be between" in w for w in r.json()["warnings"])
    r = client.post("/api/model", json={"model": model, "profile": prof})
    assert r.status_code == 200


@pytest.mark.parametrize(
    "raw",
    [
        '{"model": "exo_full", "payload_kg": Infinity}',
        '{"model": "exo_full", "payload_kg": 1e300}',
        '{"model": "exo_full", "plane": NaN}',
        '{"model": "exo_full", "elev": 200}',
        '{"model": "exo_full", "elbow": -90}',
    ],
)
def test_pose_refuses_non_finite_and_out_of_range(client, raw) -> None:
    r = client.post(
        "/api/pose", content=raw, headers={"content-type": "application/json"}
    )
    assert r.status_code == 422


def test_pose_at_the_slider_ends_works(client) -> None:
    for body in (
        {"plane": -90, "elev": 180, "axial": 90, "elbow": 145, "payload_kg": 20},
        {"plane": 140, "elev": 0, "axial": -90, "elbow": 0, "payload_kg": 0},
    ):
        r = client.post("/api/pose", json=dict(body, model="exo_full"))
        assert r.status_code == 200, r.text


def test_a_missing_profile_is_404_everywhere(client) -> None:
    assert client.get("/api/profiles/typo_name").status_code == 404
    assert client.get("/api/derive/exo_full?profile=typo_name").status_code == 404
    r = client.post("/api/profiles/typo_name/copy", json={"to": "made_from_nothing"})
    assert r.status_code == 404
    assert "made_from_nothing" not in client.get("/api/profiles").json()["profiles"]
    body = {"model": "exo_full", "test": "shoulder_hold", "profile": "typo_name"}
    assert client.post("/api/run", json=body).status_code == 404


def test_non_object_knobs_over_http(client) -> None:
    prof = {"name": "baseline", "knobs": [1]}
    r = client.post(
        "/api/run", json={"model": "exo_full", "test": "shoulder_hold", "profile": prof}
    )
    assert r.status_code == 200 and "knobs must be an object" in r.json()["warnings"]
    assert client.put("/api/profiles/crit1", json={"knobs": "x"}).status_code == 400


def test_unknown_motion_is_404_and_quotes_survive(client) -> None:
    body = {"model": "exo_full", "test": "shoulder_motions", "only": "nope"}
    r = client.post("/api/run", json=body)
    assert (
        r.status_code == 404
        and r.json()["detail"] == "no motion named 'nope' in this test"
    )
    r = client.post("/api/run", json={"model": "nope", "test": "shoulder_hold"})
    assert r.status_code == 404 and r.json()["detail"] == "no models item named 'nope'"


def test_profile_names_over_http(client) -> None:
    assert client.put("/api/profiles/abc%0A", json={}).status_code == 400
    assert client.put("/api/profiles/Baseline", json={}).status_code == 400


def test_an_edited_working_copy_is_named_as_such(client) -> None:
    edits = {"knobs": {"materials": {"pa12": {"stiffness": 2}}}}
    for name, prof, want in (
        ("baseline", {}, "baseline"),
        ("baseline", edits, "baseline (unsaved edits)"),
        ("baseline", {"knobs": {"materials": {"pa12": {"stiffness": 1}}}}, "baseline"),
    ):
        body = {
            "model": "exo_full",
            "test": "shoulder_hold",
            "profile": dict(prof, name=name),
        }
        assert client.post("/api/run", json=body).json()["profile"] == want
    client.put("/api/profiles/named copy", json=edits)
    body = {"model": "exo_full", "test": "shoulder_hold"}
    same = dict(edits, name="named copy")
    assert client.post("/api/run", json=dict(body, profile=same)).json()["profile"] == (
        "named copy"
    )
    assert client.post("/api/run", json=dict(body, profile="named copy")).json()[
        "profile"
    ] == ("named copy")


def test_registry_sends_the_limits(client) -> None:
    lim = client.get("/api/registry").json()["limits"]
    assert lim["models"]["cuffs.*.width_mm"] == [10, 300]


# Second critic (docs/2026-10-08-critic-2.md).


def test_motion_edits_reach_the_motions_bench(reg) -> None:
    """N1: a payload typed on a motion changes that motion's result."""

    def throw(p: dict | None) -> dict:
        test = copy.deepcopy(reg.effective("tests", "shoulder_motions", p))
        test["params"]["only"] = "throw"
        res = benches.run(arm.build(reg, "exo_full", p), test, reg)
        return next(c for c in res["cards"] if c["title"] == "Overarm throw")

    heavy = {
        "name": "t",
        "knobs": {},
        "overrides": {"motions": {"throw": {"payload_kg": 8}}},
    }
    assert throw(heavy)["value"] != throw(None)["value"]


def test_range_steps_have_a_floor_and_a_cell_cap(reg) -> None:
    """N2: a step under 5 is refused, and a sweep past the cell cap is too."""
    _, errors = reg.check_overrides(
        {"tests": {"shoulder_rom": {"params.plane_step": 2}}}
    )
    assert errors
    tiny = copy.deepcopy(reg.get("tests", "shoulder_rom"))
    tiny["params"].update(plane_step=1, elev_step=1)
    with pytest.raises(ValueError, match="cells"):
        benches.run(arm.build(reg, "exo_full", None), tiny, reg)


@pytest.mark.parametrize("end, fps", [(1e-300, 30), (0.0, 30), (20.0, 120)])
def test_sample_refuses_vanishing_or_huge_motions(end, fps) -> None:
    """N2, N5: a motion of ~0 s divided by ~0; one of 2401 frames took 10 s."""
    k = {"plane": 0.0, "elev": 20.0, "axial": 0.0, "elbow": 30.0}
    with pytest.raises(ValueError):
        benches.sample([dict(k, t=0.0), dict(k, t=end)], fps)


def test_squeezed_lift_keys_give_a_400(client) -> None:
    """N5: key times squeezed to 1e-300 gave NaN cards; now a clear 400."""
    o = {f"params.keys.{i}.t": 1e-300 for i in (1, 2, 3)}
    prof = {"name": "t", "knobs": {}, "overrides": {"tests": {"lift_cycle": o}}}
    r = client.post(
        "/api/run", json={"model": "exo_full", "test": "lift_cycle", "profile": prof}
    )
    assert r.status_code == 400 and "at least" in r.json()["detail"]


# The rest of the second critic: N3, N4, N6, N7 and L-a to L-e.

HUGE = 10**400


def test_huge_integers_are_not_numbers(reg) -> None:
    clean, errors = reg.check_knobs({"materials": {"pa12": {"stiffness": HUGE}}})
    assert clean == {} and errors == ["materials/pa12 stiffness: must be a number"]
    over = {"models": {"exo_full": {"cuffs.0.width_mm": HUGE}}}
    clean, errors = reg.check_overrides(over)
    assert clean == {} and errors == [
        "models/exo_full cuffs.0.width_mm: must be a number"
    ]


@pytest.mark.parametrize(
    "route", ["/api/run", "/api/model", "/api/pose", "/api/derive", "/api/report"]
)
@pytest.mark.parametrize("digits", [401, 5000])
def test_huge_integers_over_http_are_never_a_500(client, route, digits) -> None:
    big = "1" + "0" * digits
    raw = (
        '{"model": "exo_full", "test": "shoulder_hold", "profile": {"knobs":'
        ' {"materials": {"pa12": {"stiffness": %s}}}, "overrides": {"models":'
        ' {"exo_full": {"cuffs.0.width_mm": %s}}}}}' % (big, big)
    )
    r = client.post(route, content=raw, headers={"content-type": "application/json"})
    assert r.status_code < 500, r.text[:300]


def _auto_links(reg, model: str) -> list[int]:
    links = reg.items["models"][model]["links"]
    return [
        i for i, ln in enumerate(links) if "length_m" in ln and ln["length_m"] is None
    ]


@pytest.mark.parametrize("value", ["-5", " 2 ", "nan", "inf", "1e300", "x", True])
def test_auto_lengths_take_a_number_or_nothing(reg, value) -> None:
    i = _auto_links(reg, "exo_full")[-1]
    clean, errors = reg.check_overrides(
        {"models": {"exo_full": {f"links.{i}.length_m": value}}}
    )
    assert clean == {} and errors[0].endswith("must be a number")


def test_auto_lengths_are_bounded_numbers(reg) -> None:
    i = _auto_links(reg, "exo_lite")[0]
    path = f"links.{i}.length_m"
    for value, ok in ((0.3, True), (None, True), (2.0, False), (-5, False)):
        clean, errors = reg.check_overrides({"models": {"exo_lite": {path: value}}})
        assert (errors == []) is ok, (value, errors)


def test_model_route_turns_a_pose_error_into_a_400(client, monkeypatch) -> None:
    def broken(*_a, **_k):
        raise ValueError("this pose breaks the physics")

    monkeypatch.setattr(web_app, "_pose_frame", broken)
    r = client.post("/api/model", json={"model": "exo_full"})
    assert r.status_code == 400 and "breaks" in r.json()["detail"]


ODD_FILES = ["[1, 2]", "null", "5", '"x"', "{not json"]


@pytest.mark.parametrize("raw", ODD_FILES)
def test_odd_profile_files_give_a_400(client, raw) -> None:
    registry.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    path = registry.PROFILE_DIR / "odd.json"
    path.write_text(raw)
    try:
        assert client.get("/api/profiles/odd").status_code == 400
        body = {"model": "exo_full", "test": "shoulder_hold"}
        assert (
            client.post("/api/run", json=dict(body, profile="odd")).status_code == 400
        )
        r = client.post("/api/profiles/odd/copy", json={"to": "odd copy"})
        assert r.status_code == 400
        # The page sends the profile inline once loaded: that must still run.
        inline = {"name": "odd", "knobs": {}, "overrides": {}}
        assert (
            client.post("/api/run", json=dict(body, profile=inline)).status_code == 200
        )
    finally:
        path.unlink()


@pytest.mark.parametrize(
    "raw",
    [
        '{"knobs": "x"}',
        '{"knobs": {"materials": 5}}',
        '{"knobs": {"materials": {"pa12": 5}}}',
    ],
)
def test_inline_twin_of_an_odd_file_runs(client, raw) -> None:
    registry.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    path = registry.PROFILE_DIR / "oddknobs.json"
    path.write_text(raw)
    try:
        body = {"model": "exo_full", "test": "shoulder_hold"}
        assert (
            client.post("/api/run", json=dict(body, profile="oddknobs")).status_code
            == 200
        )
        inline = dict(json.loads(raw), name="oddknobs")
        r = client.post("/api/run", json=dict(body, profile=inline))
        assert r.status_code == 200 and r.json()["profile"] == "oddknobs"
    finally:
        path.unlink()


def test_an_unchanged_run_of_a_hand_edited_file_keeps_its_name(client) -> None:
    registry.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    edits = {"overrides": {"models": {"exo_full": {"cuffs.0.width_mm": 0}}}}
    path = registry.PROFILE_DIR / "handbad.json"
    path.write_text(json.dumps(edits))
    try:
        body = {"model": "exo_full", "test": "shoulder_hold"}
        r = client.post(
            "/api/run", json=dict(body, profile=dict(edits, name="handbad"))
        )
        assert r.status_code == 200 and r.json()["profile"] == "handbad"
    finally:
        path.unlink()


def test_a_zero_gearbox_limit_stops_the_drive(reg) -> None:
    from exolab import parts

    prof = {"overrides": {"actuators": {"harmonic_m": {"torque_limit_nm": 0}}}}
    j = parts.joint(reg, "harmonic_m", "J1", "J1", [-90, 90], prof, "exo_full")
    assert j.torque_peak == 0 and j.torque_cont == 0
    j = parts.joint(reg, "harmonic_m", "J1", "J1", [-90, 90], None, "exo_full")
    assert j.torque_peak > 0


FIXED_TEXT = [
    ("models", "exo_full", "links.1.section.shape", "rect"),
    ("models", "exo_full", "links.0.role", "upper_arm"),
    ("models", "exo_full", "id", "exo_lite"),
    ("models", "exo_full", "suit_asset", "exo_lite"),
    ("models", "spider_mech", "status", "ready"),
    ("tests", "shoulder_hold", "kind", "shoulder_rom"),
    ("tests", "lift_cycle", "kind", "hold"),
    ("mechanisms", "girdle_tracking", "kind", "cable"),
    ("actuators", "harmonic_m", "kind", "passive"),
]


@pytest.mark.parametrize("kind,item,path,value", FIXED_TEXT)
def test_text_that_builds_the_model_is_fixed(reg, kind, item, path, value) -> None:
    clean, errors = reg.check_overrides({kind: {item: {path: value}}})
    assert clean == {} and len(errors) == 1 and "fixed" in errors[0], errors


def test_text_with_choices(reg) -> None:
    for value, ok in (("male", True), ("female", True), ("x", False)):
        clean, errors = reg.check_overrides({"human": {"subject": {"sex": value}}})
        assert (errors == []) is ok, errors
    assert "must be one of female, male" in errors[0]


def test_describing_text_still_edits(reg) -> None:
    over = {
        "models": {"exo_full": {"name": "My suit"}},
        "mechanisms": {"girdle_tracking": {"design_note": "mine"}},
    }
    clean, errors = reg.check_overrides(over)
    assert errors == [] and clean == over


def test_the_text_rule_names_real_kinds_and_fields(reg) -> None:
    text = reg.limits["text"]
    assert set(text["refs"]) <= set(reg.items)
    for field, choices in text["choices"].items():
        held = [
            it[field]
            for items in reg.items.values()
            for it in items.values()
            if field in it
        ]
        assert held and all(v in choices for v in held), field


def test_id_fields_only_point_at_parts_kinds(reg) -> None:
    assert reg.id_kind("al_7075_t6") == "materials"
    assert reg.id_kind("overhead_reach") == "motions"
    assert reg.id_kind("girdle") is None  # a link role, not the human item


def test_key_errors_inside_the_physics_are_400(reg) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        web_app._call(lambda: {}["w_mm"])
    assert e.value.status_code == 400 and "w_mm" in e.value.detail
    with pytest.raises(HTTPException) as e:
        web_app._call(lambda: reg.get("models", "nope"))
    assert e.value.status_code == 404


def test_fixed_text_is_refused_on_save(client) -> None:
    body = {"overrides": {"tests": {"lift_cycle": {"kind": "hold"}}}}
    assert client.put("/api/profiles/fixedtext", json=body).status_code == 400


@pytest.mark.parametrize(
    "key", ["exo_full/NOPE", "exo_full", "exo_full/J1/x", "nope/J1", "exo_full/J9"]
)
def test_part_knobs_name_a_real_part(reg, key) -> None:
    clean, errors = reg.check_knobs({"parts": {key: {"power": 2}}})
    assert clean == {} and len(errors) == 1, errors


def test_every_part_resolve_reads_has_a_knob_name(reg) -> None:
    from exolab import parts

    for model in ("exo_full", "exo_lite"):
        seen: set[str] = set()
        real = parts.part_knobs

        def spy(profile, model_id, part, _seen=seen, _real=real):
            _seen.add(part)
            return _real(profile, model_id, part)

        parts.part_knobs = spy
        try:
            arm.build(reg, model, None)
        finally:
            parts.part_knobs = real
        assert seen == reg.part_ids(model, None), model
        knobs = {"parts": {f"{model}/{p}": {"weight": 2} for p in seen}}
        clean, errors = reg.check_knobs(knobs)
        assert errors == [] and len(clean["parts"]) == len(seen)


def test_bad_part_knobs_are_refused_on_save(client) -> None:
    body = {"knobs": {"parts": {"exo_full/NOPE": {"power": 2}}}}
    assert client.put("/api/profiles/badpart", json=body).status_code == 400


def test_character_edits_are_checked_and_used(reg) -> None:
    for kind, item in (("human", "subject"), ("models", "exo_full")):
        clean, errors = reg.check_overrides(
            {kind: {item: {"character": "no_such_character"}}}
        )
        assert clean == {} and "must be one of" in errors[0], errors
    raw = {"overrides": {"models": {"exo_full": {"character": "no_such_character"}}}}
    with pytest.raises(FileNotFoundError):
        arm.build(reg, "exo_full", raw)


@pytest.mark.parametrize(
    "name", ["baseIine", "base1ine", "baseline-", "baseline_", "Base line", "BASE.LINE"]
)
def test_names_that_read_as_baseline_are_refused(reg, name) -> None:
    with pytest.raises(ValueError):
        registry.save_profile(name, {}, reg)


def test_names_near_baseline_are_fine(reg) -> None:
    for name in ("baseline 2", "my baseline", "baselines"):
        assert registry.save_profile(name, {}, reg)["name"] == name


def test_the_page_name_check_mirrors_the_registry() -> None:
    import re
    from pathlib import Path

    js = (Path(web_app.__file__).parent / "static/js/editor.js").read_text()
    m = re.search(r"const NAME_RE = /\^(.*)\$/;", js)
    assert m and m.group(1) == registry.NAME_RE.pattern
