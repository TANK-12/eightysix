"""Transition choice rules, timeline auto build, edit preservation and PUT checks."""

import copy

import pytest

from panelforge import transitions
from panelforge.camera import Character, PanelInfo
from panelforge.render import timeline as TL
from panelforge.render.fixture import make_chapter
from panelforge.render.inputs import ChapterInputs


def _p(pid, scene="s1", loc="hall", action=0.0, kind="panel", chars=None, mood=None):
    return PanelInfo(
        id=pid,
        w=800,
        h=600,
        scene_id=scene,
        location=loc,
        action=action,
        kind=kind,
        characters=chars or [],
        mood=mood,
    )


def test_transition_rules():
    face = lambda: [
        Character([100, 100, 300, 400], face=[150, 100, 120, 120], cast_id="c1")
    ]  # noqa: E731
    assert transitions.choose_auto(None, _p("a"))[0] == "fade"
    assert transitions.choose_auto(_p("a"), _p("b", scene="s2"))[0] == "fade"
    assert transitions.choose_auto(_p("a"), _p("b", loc="street"))[0] == "fade"
    assert (
        transitions.choose_auto(_p("a", chars=face()), _p("b", chars=face()))[0]
        == "match"
    )
    assert transitions.choose_auto(_p("a"), _p("b", action=0.9))[0] == "whip"
    assert transitions.choose_auto(_p("a"), _p("b", kind="splash"))[0] == "zoom-through"
    assert transitions.choose_auto(_p("a"), _p("b"), reading="ttb")[0] == "slide"
    assert transitions.choose_auto(_p("a"), _p("b"), reading="rtl")[0] == "cut"
    assert transitions.choose_auto(_p("a"), _p("b"), style_pref="fade")[0] == "fade"
    assert transitions.reading_direction("ttb") == (0.0, 1.0)


def test_every_transition_blends_to_endpoints():
    import numpy as np

    a = np.zeros((90, 160, 4), np.uint8)
    b = np.full((90, 160, 4), 200, np.uint8)
    for kind in transitions.REGISTRY:
        for u in (0.0, 0.3, 0.7, 1.0):
            out = transitions.blend(kind, a, b, u)
            assert out.shape == a.shape and out.dtype == np.uint8, kind
        assert (
            np.abs(transitions.blend(kind, a, b, 1.0).astype(int) - b).mean() < 30
        ), kind


@pytest.fixture()
def chapter(tmp_path):
    return make_chapter(tmp_path, n_panels=4)


def test_auto_builds_shots_with_lines_and_contiguous_starts(chapter):
    tl = TL.build(ChapterInputs(chapter))
    shots = tl["shots"]
    assert [s["panel_id"] for s in shots] == ["p0001", "p0002", "p0003", "p0004"]
    assert shots[0]["transition_in"]["kind"] == "fade"
    assert shots[2]["camera"]["shake"] > 0  # the action panel
    t = 0.0
    for s in shots:
        assert abs(s["start"] - t) < 1e-3
        t += s["dur"]
        assert s["lines"] and s["lines"][0]["line_id"].startswith("l")
        assert abs(s["dur"] * 30 - round(s["dur"] * 30)) < 0.01
    assert abs(tl["duration"] - t) < 1e-3


def test_auto_preserves_edited_shots_and_settings(chapter):
    inp = ChapterInputs(chapter)
    tl = TL.build(inp, overrides={"pace": 1.4, "aspect": "9:16"})
    edited = copy.deepcopy(tl)
    s = edited["shots"][1]
    s["camera"]["keys"] = [{"t": 0, "cx": 0.3, "cy": 0.4, "zoom": 1.7, "rot": 0}]
    s["dur"] = 7.0
    s["style"] = "slideshow"
    saved = TL.apply_put(tl, edited)
    assert (
        saved["shots"][1]["edited"] is True
        and saved["shots"][1]["camera"]["auto"] is False
    )
    assert saved["shots"][0]["edited"] is False
    rebuilt = TL.build(
        ChapterInputs(chapter), existing=saved, overrides={"motion_strength": 0.5}
    )
    keep = rebuilt["shots"][1]
    assert (
        keep["dur"] == 7.0
        and keep["style"] == "slideshow"
        and keep["camera"]["keys"][0]["zoom"] == 1.7
    )
    assert (
        rebuilt["settings"]["pace"] == 1.4 and rebuilt["settings"]["aspect"] == "9:16"
    )
    assert rebuilt["settings"]["motion_strength"] == 0.5
    assert (
        abs(rebuilt["shots"][2]["start"] - (rebuilt["shots"][1]["start"] + 7.0)) < 1e-3
    )


def test_put_rejects_bad_input_and_clamps(chapter):
    tl = TL.build(ChapterInputs(chapter))
    bad = copy.deepcopy(tl)
    bad["shots"][0]["transition_in"]["kind"] = "explode"
    with pytest.raises(TL.TimelineError):
        TL.apply_put(tl, bad)
    bad = copy.deepcopy(tl)
    bad["shots"][0]["style"] = "nope"
    with pytest.raises(TL.TimelineError):
        TL.apply_put(tl, bad)
    ok = copy.deepcopy(tl)
    ok["shots"][0]["lines"][0]["at"] = 99.0
    ok["shots"][0]["camera"]["keys"].append({"t": -3, "cx": 4, "cy": -1, "zoom": 0.1})
    out = TL.apply_put(tl, ok)
    s0 = out["shots"][0]
    assert s0["lines"][0]["at"] == s0["dur"] and s0["edited"]
    k = next(k for k in s0["camera"]["keys"] if k["cx"] == 1.0)
    assert k["t"] == 0 and k["cx"] == 1.0 and k["cy"] == 0.0 and k["zoom"] == 1.0


def test_page_reveal_mode_adds_reveal_shots(chapter):
    tl = TL.build(ChapterInputs(chapter), overrides={"mode": "page-reveal"})
    kinds = [s["kind"] for s in tl["shots"]]
    assert kinds[0] == "reveal" and kinds.count("panel") == 4
    first_panel = tl["shots"][1]
    assert first_panel["transition_in"]["kind"] == "cut"


def test_fixture_cutter_when_panels_missing(tmp_path):
    ch = make_chapter(tmp_path, n_panels=3)
    (ch / "panels.json").unlink()
    inp = ChapterInputs(ch)
    assert inp.panel_source == "fixture" and len(inp.panels) == 3
    assert (ch / "work" / "render" / "fixture_panels.json").exists()
