"""depth3d: layered parallax render, focus, bubbles keep/erase, fallback, cache, mp4."""

import time

import numpy as np
import pytest

from panelforge import styles
from panelforge.render import encode
from panelforge.render import timeline as TL
from panelforge.render.context import RenderContext
from panelforge.render.fixture import add_scene_layers, make_chapter
from panelforge.render.inputs import ChapterInputs
from panelforge.render.renderer import Renderer, render_timeline
from panelforge.styles import depth3d as D

ORANGE = np.array([40, 90, 200])  # the fixture's first character body colour (BGR)


@pytest.fixture()
def layered(tmp_path):
    ch = make_chapter(tmp_path, n_panels=3)
    add_scene_layers(ch)
    return ch


def _ctx(ch, **over):
    inp = ChapterInputs(ch)
    tl = TL.build(inp, overrides={"height": 360, "style": "depth3d", **over})
    ctx = RenderContext(inp, tl["settings"])
    return ctx, Renderer(ctx, tl)


def _body_centroid(frame):
    d = np.abs(frame[..., :3].astype(int) - ORANGE).sum(axis=2)
    ys, xs = np.nonzero(d < 60)
    assert len(xs) > 50, "the orange character body should be visible"
    return xs.mean(), ys.mean()


def test_registry_lists_depth3d_with_settings():
    st = styles.REGISTRY["depth3d"]
    assert st.enabled and "depth3d" in styles.enabled()
    desc = st.describe()
    for key in ("parallax_strength", "dof", "atmosphere", "feather", "sway", "dolly"):
        assert desc["settings"][key]["type"] == "number"
        assert "default" in desc["settings"][key]
    assert not any(w.isupper() and len(w) > 1 for w in desc["description"].split())


def test_layered_scene_is_built_from_scene_files(layered):
    ctx, r = _ctx(layered)
    shot = r.shots[0]
    sc = D.STYLE.scene(ctx, shot)
    assert sc["layered"] is True
    assert len(sc["chars"]) == 2 and sc["bubbles"] is not None
    assert (
        sc["depth"].dtype == np.float32
        and 0 <= sc["depth"].min() <= sc["depth"].max() <= 1
    )
    for c in sc["chars"]:
        assert c["img"].shape[2] == 4 and 0.0 < c["depth"] <= 1.0
    # characters stand in front of the background: nearer than its median
    assert min(c["depth"] for c in sc["chars"]) > float(np.median(sc["depth"]))
    # built once per shot, reused across frames
    n = sum(1 for k in ctx.cache if isinstance(k, tuple) and k[0] == "d3d")
    r.body(0, 0.4)
    r.body(0, 0.8)
    assert sum(1 for k in ctx.cache if isinstance(k, tuple) and k[0] == "d3d") == n


def test_every_frame_of_every_shot_is_sane(layered):
    ctx, r = _ctx(layered)
    for i, shot in enumerate(r.shots):
        for u in (0.0, 0.25, 0.5, 0.75, 1.0):
            f = r.body(i, shot["dur"] * u)
            assert f.shape == (360, 640, 4) and f.dtype == np.uint8
            assert f[..., 3].min() == 255
            mean = f[..., :3].mean()
            assert 20 < mean < 235, f"shot {i} at {u}: mean {mean}"


def test_character_layer_parallaxes_more_than_a_rigid_render(layered):
    ctx, r = _ctx(layered)
    shot = r.shots[0]
    t = shot["dur"] * 0.8
    off = {
        "parallax_strength": 0.0,
        "sway": 0.0,
        "dolly": 0.0,
        "dof": 0.0,
        "atmosphere": 0.0,
    }
    rigid = dict(shot, style_settings=off)
    moving = dict(shot, style_settings={**off, "parallax_strength": 2.0, "sway": 2.0})
    ctx.cache.clear()
    a = D.STYLE.render(ctx, rigid, t)
    ctx.cache.clear()
    b = D.STYLE.render(ctx, moving, t)
    ax, ay = _body_centroid(a)
    bx, by = _body_centroid(b)
    assert (
        abs(bx - ax) + abs(by - ay) > 2.0
    ), "the character layer should shift under parallax and sway"
    # sway alone moves the layers between frames even on a still camera
    still = dict(
        shot,
        style_settings={**off, "sway": 2.0},
        camera={"keys": [{"t": 0, "cx": 0.5, "cy": 0.5, "zoom": 1.2}]},
    )
    ctx.cache.clear()
    f0 = D.STYLE.render(ctx, still, 0.0)
    f1 = D.STYLE.render(ctx, still, 2.5)
    assert abs(_body_centroid(f0)[0] - _body_centroid(f1)[0]) > 1.0


def test_focus_follows_the_speaker_then_the_saliency(layered):
    ctx, r = _ctx(layered)
    shot = r.shots[0]
    sc = D.STYLE.scene(ctx, shot)
    line = shot["lines"][0]
    speaker_depth = next(c["depth"] for c in sc["chars"] if c["cast_id"] == "c01")
    assert D.STYLE._focus_target(ctx, shot, sc, line["at"] + 0.2) == pytest.approx(
        speaker_depth
    )
    late = shot["dur"] - 0.01
    if not any(ev["at"] <= late < ev["end"] for ev in sc["focus_events"]):
        assert 0.0 <= D.STYLE._focus_target(ctx, shot, sc, late) <= 1.0
    # the eased focus never leaves the depth range
    for t in np.linspace(0, shot["dur"], 12):
        assert 0.0 <= D.STYLE.focus_at(ctx, shot, sc, float(t)) <= 1.0


def test_bubbles_kept_or_erased(layered):
    ctx_keep, r_keep = _ctx(layered, bubbles="keep")
    ctx_erase, r_erase = _ctx(layered, bubbles="erase", subtitles=False)
    shot = r_keep.shots[0]
    b = ctx_keep.inp.panel_bubbles(shot["panel_id"])[0]
    bx, by, bw, bh = ctx_keep.inp.local_box(shot["panel_id"], b["box"])
    t = 0.05
    m = ctx_keep.matrix(shot, t)
    f = ctx_keep.source_factor(shot)
    cx, cy = m @ np.array([(bx + bw / 2) * f, (by + bh / 2) * f, 1.0])
    win = slice(int(cy) - 10, int(cy) + 10), slice(int(cx) - 40, int(cx) + 40)
    kept = D.STYLE.render(ctx_keep, shot, t)[win]
    gone = D.STYLE.render(ctx_erase, shot, t)[win]
    white_kept = (kept[..., :3].min(axis=2) > 200).sum()
    white_gone = (gone[..., :3].min(axis=2) > 200).sum()
    assert white_kept > 200 and white_gone < white_kept * 0.2


def test_fallback_without_scene_data_still_renders(tmp_path):
    ch = make_chapter(tmp_path, n_panels=2, scene=False)
    ctx, r = _ctx(ch)
    shot = r.shots[0]
    sc = D.STYLE.scene(ctx, shot)
    assert sc["layered"] is False and not sc["chars"] and sc["bubbles"] is None
    assert sc["strength_scale"] < 1.0
    # heuristic depth: the bottom of the panel is nearer than the top
    assert sc["depth"][-5:].mean() > sc["depth"][:5].mean()
    f0 = r.body(0, 0.2)
    f1 = r.body(0, shot["dur"] * 0.9)
    assert f0.shape == (360, 640, 4) and 20 < f0[..., :3].mean() < 235
    assert np.abs(f0.astype(int) - f1.astype(int)).mean() > 0.5


def test_missing_cutout_falls_back_to_the_whole_panel(layered):
    inp = ChapterInputs(layered)
    inp.scene["panels"]["p0001"]["characters"][0]["cutout"] = "work/scene/nowhere.png"
    tl = TL.build(inp, overrides={"height": 360, "style": "depth3d"})
    ctx = RenderContext(inp, tl["settings"])
    sc = D.STYLE.scene(ctx, tl["shots"][0])
    assert sc["layered"] is False and sc["strength_scale"] == pytest.approx(
        0.6
    )  # real depth, one layer
    assert D.STYLE.render(ctx, tl["shots"][0], 0.3).shape == (360, 640, 4)


def test_mood_grades_are_valid_luts():
    for mood in D.MOOD_GRADES:
        for atm in (0.0, 0.5, 1.5):
            lut = D.STYLE.grade_lut(mood, atm)
            assert lut.shape == (256, 1, 3) and lut.dtype == np.uint8
            assert lut[0].max() < 40 and lut[255].min() > 215
            assert (
                np.diff(lut[:, 0, :].astype(int), axis=0) >= 0
            ).all(), f"{mood} lut not monotone"
    ident = D.STYLE.grade_lut("tense", 0.0)
    assert (ident[:, 0, 0] == np.arange(256)).all()


def test_layer_matrix_scales_about_centre():
    m = np.array([[2.0, 0.0, 10.0], [0.0, 2.0, 20.0]])
    mc = D._layer_matrix(m, 5, 7, 1.0, (0.0, 0.0), (100.0, 100.0))
    assert np.allclose(mc[:, 2], [20.0, 34.0])
    mc2 = D._layer_matrix(m, 0, 0, 1.5, (3.0, -2.0), (100.0, 100.0))
    assert np.allclose(mc2[:, :2], [[3.0, 0.0], [0.0, 3.0]])
    # the centre point (100,100) stays put under the scale, then shifts by (3,-2)
    p = np.array([45.0, 40.0, 1.0])  # maps to (100,100) through m
    assert np.allclose(mc2 @ p, [103.0, 98.0])


def test_tiny_depth3d_mp4(layered):
    inp = ChapterInputs(layered)
    tl = TL.build(inp, overrides={"height": 180, "fps": 12, "style": "depth3d"})
    for s in tl["shots"]:
        s["dur"] = 1.0
    tl = TL.retime(tl)
    out = layered / "renders" / "d3d.mp4"
    res = render_timeline(layered, tl, out, audio=False, inputs=inp)
    info = encode.probe(out)
    assert (info["width"], info["height"]) == (320, 180)
    assert abs(info["duration"] - 3.0) < 0.15 and res["rendered"] == 3


def test_frame_cost_at_preview_scale_is_bounded(layered):
    ctx, r = _ctx(layered)
    r.body(0, 0.1)
    t0 = time.time()
    for i in range(10):
        r.body(0, 0.2 + i / 30)
    per = (time.time() - t0) / 10
    assert per < 0.25, f"{per * 1000:.0f} ms per 640x360 frame"


def test_rejected_detections_stay_in_the_background(layered):
    """A box the person filter rejected (a gun, a hand) is not a floating
    layer: it is pasted back into the background where it was, so it never
    vanishes behind a thin mask."""
    from panelforge import store, styles

    import time

    scene = store.read(layered / "scene.json")
    pid = next(iter(scene["panels"]))

    def build(placement):
        scene["panels"][pid]["characters"][1]["placement"] = placement
        store.write(layered / "scene.json", scene)
        time.sleep(0.02)  # a new mtime, so the scene cache is not reused
        ctx, r = _ctx(layered)
        shot = next(s for s in r.shots if s["panel_id"] == pid)
        st = styles.style_for(ctx, shot)
        sc = st.scene(ctx, shot)
        c = scene["panels"][pid]["characters"][1]
        f = ctx.source_factor(shot)
        x, y, w, h = [int(v * f) for v in c["box"]]
        return sc, sc["bg"][y : y + h, x : x + w, :3].copy()

    floating, patch_floating = build("cast")
    pasted, patch_pasted = build("rejected")
    assert len(floating["chars"]) == 2 and len(pasted["chars"]) == 1
    # with the detection pasted back, its box in the background is drawn
    # over (no longer the plain inpainted gradient)
    assert patch_pasted.shape == patch_floating.shape
    assert np.abs(patch_pasted.astype(int) - patch_floating.astype(int)).sum() > 0
