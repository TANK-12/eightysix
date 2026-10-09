"""The scroll reader: the strip as drawn, read top to bottom, nothing cut."""

import numpy as np

from panelforge import styles
from panelforge.render import timeline as TL
from panelforge.render.context import RenderContext
from panelforge.render.fixture import make_chapter
from panelforge.render.renderer import render_timeline
from panelforge.styles import scroll as SC


def _timeline(chapter, aspect="16:9"):
    from panelforge.render.inputs import ChapterInputs

    inp = ChapterInputs(chapter)
    return inp, TL.build(
        inp, overrides={"mode": "scroll", "aspect": aspect, "height": 180}
    )


def test_scroll_mode_plans_a_continuous_scroll_with_cuts_only(tmp_path):
    inp, tl = _timeline(make_chapter(tmp_path, n_panels=4))
    shots = [s for s in tl["shots"] if s["kind"] == "panel"]
    assert all(
        s["style"] == "scroll" and s["transition_in"]["kind"] == "cut" for s in shots
    )
    plans = [s["scroll"] for s in shots]
    # continuity: every shot starts where the previous one stopped
    for a, b in zip(plans, plans[1:]):
        assert b["y0"] == a["y_b"]
    # the window shows the whole strip width and moves down the strip
    assert plans[0]["strip_w"] == inp.strip["width"]
    assert plans[-1]["y_a"] > plans[0]["y_a"]
    # a panel that fits is centred in the window: fully inside it
    H = plans[0]["window_h"]
    for s, p in zip(shots, plans):
        x, y, w, h = inp.by_id[s["panel_id"]]["box"]
        if h <= H:
            assert p["y_a"] <= y and y + h <= p["y_a"] + H, (s["panel_id"], p)


def test_scroll_y_moves_then_holds():
    plan = {"y0": 0.0, "y_a": 100.0, "y_b": 100.0, "move": 1.0, "dur": 3.0}
    assert SC.scroll_y(plan, 0.0) == 0.0
    assert 40 < SC.scroll_y(plan, 0.5) < 60
    assert SC.scroll_y(plan, 1.0) == 100.0 and SC.scroll_y(plan, 2.9) == 100.0
    tall = {"y0": 100.0, "y_a": 100.0, "y_b": 400.0, "move": 0.0, "dur": 3.0}
    assert SC.scroll_y(tall, 1.5) == 250.0 and SC.scroll_y(tall, 3.0) == 400.0


def test_scroll_frames_show_the_strip_whole_and_move_down(tmp_path):
    inp, tl = _timeline(make_chapter(tmp_path, n_panels=3))
    ctx = RenderContext(inp, tl["settings"])
    shot = tl["shots"][1]
    f0 = styles.render_shot(ctx, shot, 0.0)
    f1 = styles.render_shot(ctx, shot, shot["scroll"]["move"])
    assert f0.shape == (180, 320, 4)
    # the strip band sits centred at the planned width; the sides are dark
    dw = int(round(shot["scroll"]["strip_w"] * shot["scroll"]["scale"]))
    x0 = (320 - dw) // 2
    assert f0[:, x0 + 2 : x0 + dw - 2, :3].mean() > f0[:, : x0 - 2, :3].mean()
    # the picture changed as the window moved
    assert np.abs(f0.astype(int) - f1.astype(int)).mean() > 1.0


def test_scroll_render_is_a_valid_film(tmp_path):
    chapter = make_chapter(tmp_path, n_panels=2)
    inp, tl = _timeline(chapter, aspect="9:16")
    for s in tl["shots"]:
        s["dur"] = 1.0
        s["scroll"]["dur"] = 1.0
        s["lines"] = []
    out = chapter / "renders" / "scroll.mp4"
    res = render_timeline(chapter, tl, out, audio=False, inputs=inp)
    assert res["rendered"] == 2 and out.exists() and out.stat().st_size > 1000


def test_a_respoken_line_marks_the_film_for_replanning(tmp_path):
    """After a line is spoken again (another voice, other words) its length
    changes; the shots were planned around the old length, so the render
    route asks `lines_respoken` and plans again. Edited shots keep the
    person's timing."""
    from panelforge import store

    ch = make_chapter(tmp_path, n_panels=4)
    inp, tl = _timeline(ch)
    assert TL.lines_respoken(ch, tl) == []
    script = store.read(ch / "script.json", {})
    line = script["lines"][0]
    line["audio"], line["dur"] = "audio/x.wav", line["dur"] + 2.0
    store.write(ch / "script.json", script)
    assert TL.lines_respoken(ch, tl) == [line["id"]]
    for shot in tl["shots"]:
        if any(l["line_id"] == line["id"] for l in shot["lines"]):
            shot["edited"] = True
    assert TL.lines_respoken(ch, tl) == []
    # a line handed to nobody (no sound any more) also needs a new plan
    for shot in tl["shots"]:
        shot["edited"] = False
    other = script["lines"][1]
    other["speaker"], other["audio"], other["dur"] = None, None, None
    store.write(ch / "script.json", script)
    assert other["id"] in TL.lines_respoken(ch, tl)


def test_the_balloon_being_spoken_gets_a_glow_in_scroll_frames(tmp_path):
    """While a line plays, its balloon can wear an amber ring (the style's
    `highlight` setting, off unless asked for -- Emerson did not want
    "yellow boxes around the text"); the frame is untouched otherwise."""
    inp, tl = _timeline(make_chapter(tmp_path, n_panels=3))
    ctx = RenderContext(inp, tl["settings"])
    shot = next(s for s in tl["shots"] if s.get("lines"))
    shot["style_settings"] = {"highlight": True}
    ln = shot["lines"][0]
    ln["at"], ln["dur"] = 0.0, 2.0
    speaking = styles.render_shot(ctx, shot, 1.0)
    silent = (
        styles.render_shot(ctx, shot, shot["dur"] - 0.01) if shot["dur"] > 2.5 else None
    )
    shot["style_settings"] = {}
    plain = styles.render_shot(ctx, shot, 1.0)
    diff = np.abs(speaking.astype(int) - plain.astype(int))[:, :, :3]
    assert diff.max() > 60, "no ring drawn"
    # amber: the changed pixels lean red/green over blue (BGR)
    ys, xs = np.nonzero(diff.sum(axis=2) > 60)
    px = speaking[ys, xs, :3].astype(int)
    assert px[:, 2].mean() > px[:, 0].mean()
    if silent is not None:
        shot["style_settings"] = {"highlight": True}
        assert np.array_equal(silent, styles.render_shot(ctx, shot, shot["dur"] - 0.01))


def test_scroll_width_knob_changes_the_plan(tmp_path):
    inp, tl = _timeline(make_chapter(tmp_path, n_panels=3))
    wide = TL.build(
        inp,
        overrides={
            "mode": "scroll",
            "aspect": "16:9",
            "height": 180,
            "style_settings": {"scroll": {"width": 0.9}},
        },
    )
    a = tl["shots"][0]["scroll"]["scale"]
    b = wide["shots"][0]["scroll"]["scale"]
    assert b > a * 1.3, (a, b)


def test_a_tall_panel_rests_on_each_balloon_while_its_line_plays(tmp_path):
    """Chapter 1 showed words half out of view: a panel taller than the
    window drifted top to bottom at one speed. Now the window moves to each
    balloon in turn and holds there for the line."""

    chapter = make_chapter(tmp_path, n_panels=2)
    inp, tl = _timeline(chapter)
    shot = tl["shots"][0]
    H = shot["scroll"]["window_h"]
    x, y, w, h = inp.by_id[shot["panel_id"]]["box"]
    # make the panel three windows tall with two balloons, top and bottom
    tall_h = int(3 * H)
    inp.by_id[shot["panel_id"]]["box"] = [x, y, w, tall_h]
    inp.strip["height"] = max(int(inp.strip["height"]), y + tall_h + 10)
    inp.bubbles[shot["panel_id"]] = [
        {"id": "top", "panel_id": shot["panel_id"], "box": [x + 10, y + 20, 200, 60]},
        {
            "id": "low",
            "panel_id": shot["panel_id"],
            "box": [x + 10, y + tall_h - 80, 200, 60],
        },
    ]
    shot["lines"] = [
        {"line_id": "l1", "bubble_id": "top", "at": 0.5, "dur": 2.0},
        {"line_id": "l2", "bubble_id": "low", "at": 3.5, "dur": 2.0},
    ]
    shot["dur"] = 6.0
    TL.plan_scroll(inp, [shot], tl["settings"])
    plan = shot["scroll"]
    assert plan["keys"], plan
    # between the lines the window keeps resting on the first balloon and
    # glides over only in the last SCROLL_MOVE_LEAD seconds
    y_top = SC.scroll_y(plan, 1.5)
    assert abs(SC.scroll_y(plan, 3.5 - TL.SCROLL_MOVE_LEAD - 0.01) - y_top) < 1
    for at, bid in ((1.5, "top"), (4.0, "low")):
        win_top = SC.scroll_y(plan, at)
        bx, by, bw, bh = inp.bubbles[shot["panel_id"]][0 if bid == "top" else 1]["box"]
        assert win_top <= by and by + bh <= win_top + H, (bid, win_top, by, H)
    # and it still ends at the panel's bottom
    assert abs(SC.scroll_y(plan, 6.0) - plan["y_b"]) < 1
    # a balloon drawn below the panel's bottom edge is still shown whole
    inp.bubbles[shot["panel_id"]][1]["box"] = [x + 10, y + tall_h + 40, 200, 60]
    inp.strip["height"] = y + tall_h + 400
    TL.plan_scroll(inp, [shot], tl["settings"])
    win_top = SC.scroll_y(shot["scroll"], 4.0)
    assert win_top + H >= y + tall_h + 100, (win_top, H, y + tall_h)
