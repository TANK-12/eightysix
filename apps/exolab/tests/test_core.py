"""The engine-free core: vector maths, knobs, overrides, profiles, parts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from conftest import SCRATCH, every, prof

from exolab import arm, registry, vec


def test_cross_matches_numpy() -> None:
    rng = np.random.default_rng(7)
    for _ in range(200):
        a, b = rng.normal(size=3), rng.normal(size=3)
        assert np.allclose(vec.cross(a, b), np.cross(a, b))
    assert np.allclose(vec.cross(vec.v(1, 0, 0), vec.v(0, 1, 0)), [0, 0, 1])


def test_norm_and_unit() -> None:
    assert vec.norm(vec.v(3, 4, 0)) == pytest.approx(5)
    assert np.allclose(vec.unit(vec.v(0, 0, 2)), [0, 0, 1])
    assert np.allclose(vec.unit(vec.v(0, 0, 0)), [1, 0, 0])
    assert np.allclose(vec.unit(vec.v(0, 0, 0), vec.v(0, 1, 0)), [0, 1, 0])


def test_knob_scales_only_its_mapped_fields(reg) -> None:
    base = reg.get("materials", "al_7075_t6")
    eff = reg.effective(
        "materials",
        "al_7075_t6",
        prof({"materials": {"al_7075_t6": {"stiffness": 2, "strength": 0.5}}}),
    )
    assert eff["youngs_modulus_gpa"] == pytest.approx(2 * base["youngs_modulus_gpa"])
    assert eff["yield_strength_mpa"] == pytest.approx(0.5 * base["yield_strength_mpa"])
    assert eff["density_kg_m3"] == base["density_kg_m3"]
    assert reg.get("materials", "al_7075_t6") == base  # the baseline is untouched


def test_override_beats_knob(reg) -> None:
    eff = reg.effective(
        "materials",
        "al_7075_t6",
        prof(
            {"materials": {"al_7075_t6": {"stiffness": 3}}},
            {"materials": {"al_7075_t6": {"youngs_modulus_gpa": 100}}},
        ),
    )
    assert eff["youngs_modulus_gpa"] == 100


def test_derived_limit_follows_an_overridden_source(reg) -> None:
    assert "torque_limit_nm" not in reg.get("actuators", "harmonic_m")
    over = {"actuators": {"harmonic_m": {"torque_peak_nm": 100}}}
    eff = reg.effective("actuators", "harmonic_m", prof(overrides=over))
    assert eff["torque_limit_nm"] == pytest.approx(150)


@pytest.mark.parametrize(
    "raw,want",
    [
        (100, 20.0),
        (0, 0.05),
        (-3, 0.05),
        ("x", 1.0),
        (None, 1.0),
        (float("nan"), 1.0),
        ("2.5", 2.5),
    ],
)
def test_clamp_knob(raw, want) -> None:
    assert registry.clamp_knob(raw) == want


def test_check_overrides_keeps_good_and_says_why_bad(reg) -> None:
    clean, errors = reg.check_overrides(
        {
            "materials": {
                "al_7075_t6": {
                    "youngs_modulus_gpa": 80,
                    "nope": 1,
                    "name": 5,
                    "density_kg_m3": float("nan"),
                    "yield_strength_mpa": True,
                }
            },
            "mechanisms": {
                "girdle_tracking": {
                    "joints.0.actuator": "harmonic_s",
                    "joints.1.actuator": "warp_drive",
                    "joints": [],
                }
            },
            "planets": {"x": {}},
            "models": {"no_such_model": {"a": 1}},
        }
    )
    assert clean == {
        "materials": {"al_7075_t6": {"youngs_modulus_gpa": 80}},
        "mechanisms": {"girdle_tracking": {"joints.0.actuator": "harmonic_s"}},
    }
    text = " | ".join(errors)
    assert len(errors) == 8, text
    for why in (
        "nope: no such field",
        "name: must be text",
        "density_kg_m3: must be a number",
        "yield_strength_mpa: must be a number",
        "no actuators item 'warp_drive'",
        "joints: only single values",
        "no kind 'planets'",
        "no models item 'no_such_model'",
    ):
        assert why in text


def test_profiles_live_in_the_scratch_folder() -> None:
    assert registry.PROFILE_DIR.is_relative_to(SCRATCH)


def test_profile_round_trip(reg) -> None:
    raw = {
        "knobs": {"materials": {"al_7075_t6": {"stiffness": 50}}},
        "overrides": {"materials": {"al_7075_t6": {"youngs_modulus_gpa": 75}}},
        "notes": "stiffer frame",
    }
    saved = registry.save_profile("core round trip", raw, reg)
    assert saved["knobs"] == {"materials": {"al_7075_t6": {"stiffness": 20.0}}}
    assert registry.load_profile("core round trip") == saved
    names = registry.list_profiles()
    assert names[0] == "baseline" and "core round trip" in names
    assert registry.load_profile(None) == registry.empty_profile("baseline")
    with pytest.raises(KeyError):
        registry.load_profile("never saved")


@pytest.mark.parametrize("name", ["../evil", "", ".hidden", "a/b", "x" * 49])
def test_bad_profile_names_are_refused(reg, name) -> None:
    with pytest.raises(ValueError):
        registry.save_profile(name, {}, reg)


def test_baseline_is_read_only(reg) -> None:
    with pytest.raises(ValueError, match="read-only"):
        registry.save_profile("baseline", {}, reg)


def test_save_refuses_bad_overrides(reg) -> None:
    bad = {"overrides": {"materials": {"al_7075_t6": {"nope": 1}}}}
    with pytest.raises(ValueError, match="no such field"):
        registry.save_profile("core bad", bad, reg)
    assert not registry.profile_path("core bad").exists()


def test_every_mechanism_builds_on_the_light_suit(reg) -> None:
    for mech in reg.ids("mechanisms"):
        over = {"models": {"exo_lite": {"shoulder.mechanism": mech}}}
        rig = arm.build(reg, "exo_lite", prof(overrides=over))
        assert rig.suit.mech["id"] == mech
        assert rig.kind == reg.get("mechanisms", mech)["kind"]
        assert len(rig.suit.joints) == len(reg.get("mechanisms", mech)["joints"])


def test_profile_swaps_a_shoulder_drive(reg) -> None:
    assert (
        arm.build(reg, "exo_lite", None).suit.joints[0].actuator_id == "qdd_planetary"
    )
    over = {"mechanisms": {"girdle_tracking": {"joints.0.actuator": "harmonic_m"}}}
    rig = arm.build(reg, "exo_lite", prof(overrides=over))
    assert rig.suit.joints[0].actuator_id == "harmonic_m"


def test_part_knob_scales_one_drive(reg) -> None:
    base = arm.build(reg, "exo_full", None).suit.joints[0]
    j = arm.build(
        reg, "exo_full", prof({"parts": {"exo_full/J1": {"power": 2}}})
    ).suit.joints[0]
    assert j.torque_cont == pytest.approx(2**0.5 * base.torque_cont)
    assert j.speed_max == pytest.approx(2**0.5 * base.speed_max)
    other = arm.build(
        reg, "exo_lite", prof({"parts": {"exo_full/J1": {"power": 2}}})
    ).suit.joints[0]
    assert (
        other.torque_cont == arm.build(reg, "exo_lite", None).suit.joints[0].torque_cont
    )


def test_heavier_alloy_makes_a_heavier_suit(reg) -> None:
    for model in ("exo_full", "exo_lite"):
        base = arm.build(reg, model, None).suit.mass
        heavy = arm.build(
            reg, model, prof({"materials": {"al_7075_t6": {"weight": 2}}})
        )
        assert heavy.suit.mass > base + 0.5


def test_planned_models_refuse_to_build(reg) -> None:
    for model in reg.ids("models"):
        if reg.get("models", model).get("status") != "ready":
            with pytest.raises(ValueError, match="planned"):
                arm.build(reg, model, None)


def test_power_knob_makes_a_heavier_drive(reg) -> None:
    """A bigger motor all round weighs more: power x2 doubles a drive's
    mass and remote mass, as a knob on the actuator or on the part."""
    base = arm.build(reg, "exo_full", None).suit.joints[0]
    assert base.mass > 0
    j = arm.build(reg, "exo_full", every(reg, "actuators", "power", 2)).suit.joints[0]
    assert j.mass == pytest.approx(2 * base.mass)
    assert j.remote_mass == pytest.approx(2 * base.remote_mass)
    part = arm.build(
        reg, "exo_full", prof({"parts": {"exo_full/J1": {"power": 2}}})
    ).suit.joints[0]
    assert part.mass == pytest.approx(2 * base.mass)


def test_power_is_not_free(reg) -> None:
    """Power x20 on every drive costs real weight (the Emerson-view review
    found a 20x motor that weighed nothing)."""
    for model in ("exo_full", "exo_lite"):
        base = arm.build(reg, model, None).suit.mass
        heavy = arm.build(reg, model, every(reg, "actuators", "power", 20)).suit.mass
        assert heavy > base + 5.0


def test_suit_skin_is_declared() -> None:
    """The page dresses the skin from the sidecar's skin field: the full
    suit over a black undersuit, the light one over dark shorts (a height
    band round the hips bone), so no underwear shows and the arms and legs
    stay bare."""
    suits = Path(__file__).resolve().parents[1] / "static" / "assets" / "suits"
    full = json.loads((suits / "exo_full.json").read_text())["skin"]
    lite = json.loads((suits / "exo_lite.json").read_text())["skin"]
    assert full["undersuit"] is True
    assert lite["undersuit"] is False
    cover = lite["cover"]
    assert cover["bone"] == "hips"
    # hem on the upper thigh, top above the hips bone (under the bodice)
    assert -0.3 < cover["from_m"] < -0.1 < 0 < cover["to_m"] < 0.15


def test_shorts_hem_hides_under_the_thigh_cuffs() -> None:
    """The shorts take whole skin faces, so their hem is as ragged as the
    faces are tall (about 43 mm on the thigh). The light suit puts it where
    the mesh has a ring of vertices inside the thigh cuffs, so the cuffs
    cover what is left of the edge: the faces suit.js puts in the shorts
    (centre at rest in the band) and the bare ones meet inside the cuff."""
    import numpy as np

    from exolab import body, registry

    suits = Path(__file__).resolve().parents[1] / "static" / "assets" / "suits"
    cover = json.loads((suits / "exo_lite.json").read_text())["skin"]["cover"]
    vrm = next((registry.CHAR_DIR / "hairsample_female").glob("*.vrm"))
    b = body.load_body(str(vrm))
    hips = b.rest[b.index(cover["bone"])][1]
    cuff = [s for s in body.load_suit("exo_lite", str(vrm)) if s.name == "thigh_cuff_L"]
    top, bottom = (cuff[0].verts[:, 1].max() - hips, cuff[0].verts[:, 1].min() - hips)
    ys = b.verts[b.tris][:, :, 1] - hips
    legs = ys.max(1) < -0.1
    shorts = legs & (ys.mean(1) >= cover["from_m"])
    bare = legs & (ys.mean(1) < cover["from_m"])
    lowest_dark, highest_bare = ys[shorts].min(), ys[bare].max()
    assert bottom < lowest_dark and highest_bare < top
    assert np.isfinite([lowest_dark, highest_bare]).all()
