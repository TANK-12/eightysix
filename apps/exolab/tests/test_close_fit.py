"""Close fit: the suit shells against the moving skin and each other.

Rest pose numbers must match the fit gaps the suits were built to, a shell
pushed into the skin or into another shell must fail, and a whole run must
stay quick enough to re-run live.
"""

from __future__ import annotations

import dataclasses
import json
import math
import time

import numpy as np
import pytest

from exolab import arm, benches, vec
from exolab import body as B
from exolab.benches import close_fit as C

READY = ("exo_full", "exo_lite")
REACH = 0.010


def paths(reg, model: str) -> tuple[str, str]:
    rig = arm.build(reg, model, None)
    return (
        str(arm.character_path(rig.character)),
        reg.get("models", model)["suit_asset"],
    )


def rules(reg) -> dict:
    return C.rules_of(reg.get("tests", "close_fit")["params"])


@pytest.fixture(scope="module")
def fits(reg) -> dict:
    return {m: C.fit_for(*paths(reg, m), ("_SKIN",), REACH) for m in READY}


def shells_with(reg, model: str, name: str, move) -> list[B.Shell]:
    """The suit's shells with one of them moved (``move`` maps its rest
    vertices to new ones); the cached originals stay untouched."""
    out = []
    for s in B.load_suit(paths(reg, model)[1], paths(reg, model)[0], ("_SKIN",)):
        out.append(dataclasses.replace(s, verts=move(s.verts)) if s.name == name else s)
    assert any(s.name == name for s in out), name
    return out


# Fitted over shoes or hair, which the skin-only clearance does not see: their
# rest gap to the skin is not the gap they were built to.
OVER_CLOTHES = {"boot_L", "boot_R", "foot_stirrup_L", "foot_stirrup_R", "helmet"}


def test_rest_pose_matches_the_fit_gaps(fits) -> None:
    for model, fit in fits.items():
        strict = 0
        for s, r in zip(fit.shells, fit.rest):
            if r["min_mm"] is None:
                continue  # fitted over the dress: the skin is beyond reach
            assert r["min_mm"] >= 0, (model, s.name, r)
            if s.name in OVER_CLOTHES:
                continue
            assert r["min_mm"] <= s.gap_mm + 0.5, (model, s.name, r)
            assert r["median_inner_mm"] is not None, (model, s.name, r)
            assert abs(r["median_inner_mm"] - s.gap_mm) < 0.6, (model, s.name, r)
            strict += 1
        assert strict >= 9, model
        # Every shell on the moving arm sits on skin and matches its gap.
        assert all(r["median_inner_mm"] for r, m in zip(fit.rest, fit.moves) if m)


def test_rest_pose_frame_is_clean(reg, fits) -> None:
    for model, fit in fits.items():
        got = fit.frame({}, rules(reg))
        assert not [i for i in got["issues"] if i["level"] == "fail"], model
        assert all(x["mm"] >= 0 for x in got["skin"].values()), model
        assert got["body"] is None and got["pairs"] == {}


def pushed_in(reg, fit, model: str, name: str, mm: float):
    """The suit with one shell pushed toward the skin under its closest
    vertex: by its gap there plus ``mm``."""
    s = fit.shells[[x.name for x in fit.shells].index(name)]
    d, t = B.nearest(s.verts, [B.TriGrid(fit.body.verts, fit.body.tris, REACH)])
    k = int(np.nanargmin(np.where(np.isfinite(d), d, np.nan)))
    tri = fit.body.tris[t[k]]
    v = fit.body.verts
    on = B.closest_on_tris(s.verts[k], v[tri[0]], v[tri[1]], v[tri[2]])
    step = (on - s.verts[k]) / np.linalg.norm(on - s.verts[k]) * (d[k] + mm / 1000)
    return C.Fit(
        *paths(reg, model),
        ("_SKIN",),
        REACH,
        shells=shells_with(reg, model, name, lambda x: x + step),
    )


def test_shell_pushed_into_the_skin_fails(reg, fits) -> None:
    model, name = "exo_lite", "forearm_cuff_R"
    got = pushed_in(reg, fits[model], model, name, 5).frame({}, rules(reg))
    fails = [x for x in got["issues"] if x["part"] == name and x["level"] == "fail"]
    assert fails and fails[0]["value"] <= -4.0, got["issues"]
    assert got["skin"][name]["mm"] <= -4.0
    assert any(m["part"] == name and m["level"] == "fail" for m in got["marks"])


def test_a_shell_deeper_than_the_reach_says_so(reg, fits) -> None:
    # 40 mm in, the cuff's points in reach are about 9 mm deep and the rest
    # are further in: the depth reads as the reach, "or more".
    model, name = "exo_lite", "forearm_cuff_R"
    got = pushed_in(reg, fits[model], model, name, 40).frame({}, rules(reg))
    assert got["skin"][name]["mm"] == -REACH * 1000.0, got["skin"][name]
    fails = [x for x in got["issues"] if x["part"] == name and x["level"] == "fail"]
    assert fails and "10 mm or more" in fails[0]["text"], fails


def test_shells_pushed_into_each_other_fail(reg, fits) -> None:
    model = "exo_lite"
    fit = fits[model]
    names = [s.name for s in fit.shells]
    up = fit.shells[names.index("upper_arm_cuff_R")]
    low = fit.shells[names.index("forearm_cuff_R")]
    bd = fit.body
    # Slide the forearm cuff up the arm until it runs 15 mm into the upper
    # arm cuff, then bend the elbow a little so the two bones part from
    # their rest relation and the pair is measured.
    axis = bd.rest[low.bone] - bd.rest[up.bone]
    axis /= np.linalg.norm(axis)
    gap = (low.verts @ axis).min() - (up.verts @ axis).max()
    step = -axis * (gap + 0.015)
    moved = C.Fit(
        *paths(reg, model),
        ("_SKIN",),
        REACH,
        shells=shells_with(reg, model, "forearm_cuff_R", lambda x: x + step),
    )
    pose = {"rightLowerArm": list(vec.quat(vec.ry(math.radians(10))))}
    got = moved.frame(pose, rules(reg))
    pair = "forearm_cuff_R+upper_arm_cuff_R"
    assert pair in got["pairs"] and got["pairs"][pair]["mm"] <= 0, got["pairs"]
    assert any(
        x["part"] == pair and x["level"] == "fail" and x["code"] == "overlap"
        for x in got["issues"]
    )
    assert any(m["part"] == pair for m in got["marks"])
    # The same bend with the suit as built: no clash between the two.
    clean = fit.frame(pose, rules(reg))
    assert clean["pairs"].get(pair, {"mm": 99})["mm"] > 0


def test_run_reports_shells_pairs_and_marks(reg) -> None:
    rig = arm.build(reg, "exo_lite", None)
    test = reg.effective("tests", "close_fit", None)
    t0 = time.process_time()
    res = benches.run(rig, test, reg)
    spent = time.process_time() - t0
    json.dumps(res, allow_nan=False)
    assert res["verdict"] in benches.LEVELS
    assert {s["name"] for s in res["shells"]} >= {"forearm_cuff_R", "upper_arm_cuff_R"}
    assert all(m["frames"] for m in res["motions"])
    frames = [f for m in res["motions"] for f in m["frames"]]
    assert all("clash" in f and "fit" in f for f in frames)
    for f in frames:
        for c in f["clash"]:
            assert c["level"] in ("fail", "warn", "body") and len(c["at"]) == 3
    # A live re-run stays quick: about 2 s on an idle laptop; the bound
    # leaves room for other work on the machine.
    assert spent < 15, spent


def test_built_suits_keep_their_shells_apart_at_rest(fits) -> None:
    for model, fit in fits.items():
        near = [
            (fit.shells[a].name, fit.shells[b].name, g * 1000)
            for a, b, g in fit.pairs
            if g * 1000 < 0.5
        ]
        assert not near, (model, near)


def test_shells_built_into_each_other_fail_at_rest(reg, fits, monkeypatch) -> None:
    # Two shells whose bones keep their rest relation in a frame are not
    # measured there: one built into the other shows as an "at rest" pair.
    model = "exo_lite"
    fit = fits[model]
    names = [s.name for s in fit.shells]
    up = fit.shells[names.index("upper_arm_cuff_R")]
    low = fit.shells[names.index("forearm_cuff_R")]
    axis = fit.body.rest[low.bone] - fit.body.rest[up.bone]
    axis /= np.linalg.norm(axis)
    gap = (low.verts @ axis).min() - (up.verts @ axis).max()
    moved = C.Fit(
        *paths(reg, model),
        ("_SKIN",),
        REACH,
        shells=shells_with(
            reg, model, "forearm_cuff_R", lambda x: x - axis * (gap + 0.015)
        ),
    )
    monkeypatch.setattr(C, "fit_for", lambda *a: moved)
    test = reg.effective("tests", "close_fit", None)
    test["params"]["only"] = "side_raise"
    res = benches.run(arm.build(reg, model, None), test, reg)
    pair = [p for p in res["pairs"] if p["name"] == "forearm_cuff_R+upper_arm_cuff_R"]
    assert pair and pair[0]["level"] == "fail", res["pairs"]
    assert res["verdict"] == "fail"


def test_profile_motion_edits_reach_the_test(reg) -> None:
    prof = {
        "overrides": {"motions": {"side_raise": {"keys.1.elev": 30, "keys.2.elev": 30}}}
    }
    test = reg.effective("tests", "close_fit", prof)
    test["params"]["only"] = "side_raise"
    res = benches.run(arm.build(reg, "exo_lite", prof), test, reg)
    elev = [f["pose"]["elev"] for m in res["motions"] for f in m["frames"]]
    assert max(elev) <= 30.5, max(elev)


@pytest.mark.parametrize(
    "params, words",
    [
        ({"reach_mm": 0}, "reach_mm"),
        ({"reach_mm": 100}, "reach_mm"),
        ({"reach_mm": 5, "warn_mm": 6}, "warn"),
        ({"fps": 120}, "frames"),
    ],
)
def test_settings_that_break_the_run_are_refused(reg, params, words) -> None:
    test = reg.effective("tests", "close_fit", None)
    test["params"].update(params)
    with pytest.raises(ValueError, match=words):
        benches.run(arm.build(reg, "exo_lite", None), test, reg)


def test_typed_settings_stay_in_their_limits(reg) -> None:
    lo, hi = reg.limit("tests", "params.reach_mm", 10)
    assert (lo, hi) == (5, 20)
    clean, errors = reg.check_overrides(
        {"tests": {"close_fit": {"params.reach_mm": 100}}}
    )
    assert errors or clean["tests"]["close_fit"]["params.reach_mm"] <= 20


def test_full_suit_run_time(reg) -> None:
    # The slower suit: about 4.5 s on an idle laptop; the bound leaves room
    # for other work on the machine.
    rig = arm.build(reg, "exo_full", None)
    test = reg.effective("tests", "close_fit", None)
    t0 = time.process_time()
    res = benches.run(rig, test, reg)
    spent = time.process_time() - t0
    assert res["verdict"] in benches.LEVELS
    assert spent < 20, spent
