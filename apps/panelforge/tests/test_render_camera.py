"""Camera rules: keys stay inside the panel, dwell timing, 180-degree rule, lead room."""

import random

from panelforge.camera import (
    CameraSettings,
    Character,
    DirectionState,
    Line,
    PanelInfo,
    key_inside,
    plan_shot,
    sample,
)
from panelforge.camera import keys as K


def _random_panel(rng: random.Random, i: int) -> PanelInfo:
    w = rng.randint(200, 1600)
    h = rng.choice([rng.randint(150, 900), rng.randint(900, 5000)])
    lines = []
    for j in range(rng.randint(0, 4)):
        bw, bh = rng.randint(30, max(31, w // 2)), rng.randint(20, max(21, h // 3))
        lines.append(
            Line(
                f"l{j}",
                f"b{j}",
                [rng.uniform(0, w - bw), rng.uniform(0, h - bh), bw, bh],
                text=" ".join(["word"] * rng.randint(1, 20)),
                speaker=rng.choice([None, "c1", "c2"]),
                dur=rng.choice([None, rng.uniform(0.5, 5.0)]),
            )
        )
    chars = []
    for c in range(rng.randint(0, 3)):
        cw, ch = rng.randint(20, w), rng.randint(20, h)
        x, y = rng.uniform(0, w - cw), rng.uniform(0, h - ch)
        chars.append(
            Character(
                [x, y, cw, ch],
                face=rng.choice([None, [x, y, cw / 3, ch / 4]]),
                facing=rng.choice([None, "left", "right", "front"]),
                cast_id=rng.choice([None, "c1", "c2", "c3"]),
            )
        )
    return PanelInfo(
        id=f"p{i}",
        w=w,
        h=h,
        kind=rng.choice(["panel", "panel", "splash", "caption-only"]),
        lines=lines,
        characters=chars,
        saliency=(
            [[rng.uniform(0, w), rng.uniform(0, h), 1.0]] if rng.random() < 0.5 else []
        ),
        mood=rng.choice([None, "calm", "action", "tense", "sad", "mystery", "comic"]),
        action=rng.random(),
        scene_id=rng.choice(["s1", "s2"]),
        has_text=bool(lines),
    )


def test_sweep_keys_inside_panel_and_ordered():
    rng = random.Random(7)
    failures = []
    for aspect_out in ((1920, 1080), (1080, 1920)):
        state = DirectionState()
        for i in range(1500):
            p = _random_panel(rng, i)
            s = CameraSettings(
                out=aspect_out,
                pace=rng.uniform(0.5, 2.0),
                motion_strength=rng.uniform(0, 1.5),
                allow_flip=rng.random() < 0.5,
                text_kept=rng.random() < 0.5,
            )
            plan = plan_shot(p, s, state)
            ts = [k["t"] for k in plan.keys]
            zmax = K.max_zoom_for((p.w, p.h), s.out, s.motion_strength)
            if not plan.keys or ts != sorted(ts) or ts[-1] > plan.dur + 1e-6:
                failures.append((i, "order", ts, plan.dur))
            # a wide strip in a portrait frame is deliberately shown a little
            # smaller than the frame ("with air"): centred, zoom 0.94
            air = any("with air" in n for n in plan.notes)
            for k in plan.keys:
                if air:
                    if not (k["zoom"] == 0.94 and k["cx"] == 0.5 and k["cy"] == 0.5):
                        failures.append((i, "air", k, p.w, p.h))
                    continue
                if (
                    not key_inside(k, (p.w, p.h), s.out)
                    or not 1.0 <= k["zoom"] <= zmax + 1e-3
                ):
                    failures.append((i, "outside", k, p.w, p.h))
            for j in range(12):
                c = sample(plan.keys, plan.dur * j / 11, (p.w, p.h), s.out, zmax)
                if not air and not key_inside(c, (p.w, p.h), s.out):
                    failures.append((i, "sample", c))
    assert not failures, failures[:5]


def _talk_panel():
    lines = [
        Line("l1", "b1", [50, 40, 200, 80], text="first line here", dur=2.0),
        Line("l2", "b2", [1300, 700, 200, 80], text="second", dur=1.5, pause_after=0.3),
    ]
    return PanelInfo(id="p1", w=1600, h=900, lines=lines)


def test_dwell_timing_follows_line_durations():
    s = CameraSettings(out=(1920, 1080))
    plan = plan_shot(_talk_panel(), s)
    l1, l2 = plan.lines
    assert l1["dur"] == 2.0 and l2["dur"] == 1.5
    assert abs(l2["at"] - (l1["at"] + 2.0 + 0.25)) < 1e-6
    assert plan.dur >= l2["at"] + 1.5
    zmax = K.max_zoom_for((1600, 900), s.out, 1.0)
    # during each line the camera looks at that line's bubble
    for ln, (bx, by) in ((l1, (150, 80)), (l2, (1400, 740))):
        for u in (0.3, 0.6, 0.85):
            k = sample(plan.keys, ln["at"] + ln["dur"] * u, (1600, 900), s.out, zmax)
            vw, vh = K.view_size(k["zoom"], (1600, 900), s.out)
            assert (
                abs(k["cx"] * 1600 - bx) <= vw / 2 and abs(k["cy"] * 900 - by) <= vh / 2
            ), (ln, u, k)


def test_words_per_second_fallback():
    p = PanelInfo(
        id="p1",
        w=800,
        h=600,
        lines=[Line("l1", "b1", [0, 0, 100, 50], text=" ".join(["w"] * 26))],
    )
    plan = plan_shot(p, CameraSettings())
    assert abs(plan.lines[0]["dur"] - (26 / 2.6 + 0.35)) < 1e-6


def _two_shot(pid, a_x, b_x, text=False):
    return PanelInfo(
        id=pid,
        w=1000,
        h=600,
        scene_id="s1",
        has_text=text,
        characters=[
            Character(
                [a_x, 100, 200, 400],
                face=[a_x + 50, 100, 100, 100],
                facing="right",
                cast_id="A",
            ),
            Character(
                [b_x, 100, 200, 400],
                face=[b_x + 50, 100, 100, 100],
                facing="left",
                cast_id="B",
            ),
        ],
    )


def test_180_rule_mirrors_when_allowed():
    s = CameraSettings(allow_flip=True, text_kept=False)
    st = DirectionState()
    assert not plan_shot(_two_shot("p1", 100, 700), s, st).flip
    plan = plan_shot(_two_shot("p2", 700, 100, text=True), s, st)
    assert plan.flip and "mirrored" in " ".join(plan.notes)
    # after mirroring, A is back on the left for the next shot's memory
    assert st.sides["A"] < st.sides["B"]


def test_180_rule_opens_single_when_text_kept():
    s = CameraSettings(allow_flip=True, text_kept=True)
    st = DirectionState()
    plan_shot(_two_shot("p1", 100, 700), s, st)
    plan = plan_shot(_two_shot("p2", 700, 100, text=True), s, st)
    assert not plan.flip
    first = plan.keys[0]
    vw, _ = K.view_size(first["zoom"], (1000, 600), s.out)
    assert vw < 700, "opens on one character, not the crossed two-shot"
    # a new scene resets the memory: no correction
    other = _two_shot("p3", 100, 700, text=True)
    other.scene_id = "s2"
    assert "swapped" not in " ".join(plan_shot(other, s, st).notes)


def test_lead_room_toward_facing():
    for facing, sign in (("right", 1), ("left", -1)):
        p = PanelInfo(
            id="p1",
            w=1600,
            h=900,
            lines=[
                Line("l1", "b1", [700, 350, 120, 60], text="hey", speaker="A", dur=1.5)
            ],
            characters=[
                Character(
                    [650, 300, 300, 500],
                    face=[700, 320, 150, 150],
                    facing=facing,
                    cast_id="A",
                )
            ],
        )
        plan = plan_shot(p, CameraSettings(motion_strength=0.6))
        framed = [k for k in plan.keys if k["zoom"] > 1.2]
        assert framed
        region_cx = (700 + 830) / 2 / 1600  # centre of bubble+face union
        assert all((k["cx"] - region_cx) * sign > 0 for k in framed), (facing, framed)


def test_action_punch_and_tall_tilt():
    p = PanelInfo(id="p1", w=800, h=600, action=0.9, mood="action")
    plan = plan_shot(p, CameraSettings())
    assert plan.shake > 0 and plan.impacts and max(k["zoom"] for k in plan.keys) > 1.1
    tall = PanelInfo(id="p2", w=800, h=4000)
    plan = plan_shot(tall, CameraSettings(out=(1920, 1080)))
    cys = [k["cy"] for k in plan.keys]
    _, vh = K.view_size(plan.keys[0]["zoom"], (800, 4000), (1920, 1080))
    assert cys == sorted(cys)
    assert abs(cys[0] * 4000 - vh / 2) < 1 and abs(cys[-1] * 4000 + vh / 2 - 4000) < 1


def _view_rect(key, src, out):
    vw, vh = K.view_size(key["zoom"], src, out)
    cx, cy = key["cx"] * src[0], key["cy"] * src[1]
    return cx - vw / 2, cy - vh / 2, cx + vw / 2, cy + vh / 2


def test_text_is_never_sliced_by_the_frame_edge():
    """A caption at the bottom of a tall panel is shown whole or not at all,
    and it is whole for the whole time it is being read."""
    line = Line(
        "l1", "b1", [60, 1500, 600, 180], text="humanity left the planet", dur=3.0
    )
    p = PanelInfo(
        id="p1",
        w=800,
        h=1700,
        lines=[line],
        has_text=True,
        characters=[Character(box=[100, 100, 400, 700], face=[200, 150, 120, 120])],
    )
    settings = CameraSettings(out=(1920, 1080))
    plan = plan_shot(p, settings)
    src = (p.w, p.h)
    x, y, w, h = line.box
    read = plan.lines[0]
    for k in plan.keys:
        x0, y0, x1, y1 = _view_rect(k, src, settings.out)
        inside = (
            x0 <= x + 0.5 and x1 >= x + w - 0.5 and y0 <= y + 0.5 and y1 >= y + h - 0.5
        )
        outside = x1 <= x or x0 >= x + w or y1 <= y or y0 >= y + h
        assert inside or outside, (k, "the caption is cut by the frame edge")
        if read["at"] <= k["t"] <= read["at"] + read["dur"]:
            assert inside, (k, "the caption is not in frame while it is read")


def test_text_safe_is_off_when_bubbles_are_erased():
    """With bubbles erased and subtitles burned in, the camera may push in."""
    line = Line("l1", "b1", [60, 1500, 600, 180], text="hello", dur=3.0)
    p = PanelInfo(id="p1", w=800, h=1700, lines=[line], has_text=True)
    kept = plan_shot(p, CameraSettings(out=(1920, 1080), text_kept=True))
    erased = plan_shot(p, CameraSettings(out=(1920, 1080), text_kept=False))
    assert max(k["zoom"] for k in erased.keys) >= max(k["zoom"] for k in kept.keys)


def test_shaky_shots_leave_more_room_around_the_text():
    """The renderer draws a shaking shot larger than the planned frame, so the
    camera has to leave that much more air around a caption."""
    from panelforge.camera.rules import _safe_margin, ShotPlan, TEXT_SAFE_MARGIN

    assert _safe_margin(ShotPlan()) == TEXT_SAFE_MARGIN
    shaky = _safe_margin(ShotPlan(shake=0.7))
    assert shaky > TEXT_SAFE_MARGIN * 1.06
    assert _safe_margin(ShotPlan(shake=0.7, impacts=[0.4])) > shaky


def test_a_wide_strip_panel_is_held_whole():
    """A title or credit strip spans the frame already: no push-in, no shake,
    even with lettering the OCR could not read (so there is no text box)."""
    strip = PanelInfo(id="p1", w=732, h=268, mood="tense", action=0.9)
    plan = plan_shot(strip, CameraSettings(out=(1920, 1080), text_kept=True))
    assert plan.keys and all(k["zoom"] == 1.0 for k in plan.keys), plan.keys
    assert all((k["cx"], k["cy"]) == (0.5, 0.5) for k in plan.keys), plan.keys
    assert plan.shake == 0.0 and not plan.impacts
    assert "wide strip: held whole" in plan.notes
    # an ordinary panel with the same mood still moves
    normal = PanelInfo(id="p2", w=800, h=600, mood="tense", action=0.9)
    moving = plan_shot(normal, CameraSettings(out=(1920, 1080), text_kept=True))
    assert max(k["zoom"] for k in moving.keys) > 1.0 or moving.shake > 0


def test_silent_and_music_films_dwell_by_reading_pace():
    """With no voices in the film, a line's voice-clip length must not set
    the dwell: the panel holds for as long as the words take to read."""
    long_clip = Line("l1", "b1", [60, 100, 600, 180], text="Hi there.", dur=9.0)
    p = PanelInfo(id="p1", w=800, h=600, lines=[long_clip], has_text=True)
    voiced = plan_shot(p, CameraSettings(out=(1920, 1080), voiced=True))
    silent = plan_shot(p, CameraSettings(out=(1920, 1080), voiced=False))
    assert voiced.dur >= 9.0
    assert 1.5 <= silent.dur <= 4.0, silent.dur


def test_a_wide_strip_gets_air_in_a_portrait_frame():
    strip = PanelInfo(id="p1", w=732, h=268)
    landscape = plan_shot(strip, CameraSettings(out=(1920, 1080)))
    portrait = plan_shot(strip, CameraSettings(out=(1080, 1920)))
    assert all(k["zoom"] == 1.0 for k in landscape.keys)
    assert all(k["zoom"] == 0.94 for k in portrait.keys), portrait.keys
    assert "wide strip: held whole with air" in portrait.notes
    assert not any("_air" in k for k in portrait.keys)
    # an ordinary panel never zooms out past itself
    normal = plan_shot(
        PanelInfo(id="p2", w=800, h=600), CameraSettings(out=(1080, 1920))
    )
    assert all(k["zoom"] >= 1.0 for k in normal.keys)
