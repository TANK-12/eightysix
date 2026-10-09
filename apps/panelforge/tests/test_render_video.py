"""Tiny real renders: mp4 validity (ffprobe), per-shot cache reuse, subtitles, erase."""

import numpy as np
import pytest

from panelforge.render import encode, timeline as TL
from panelforge.render.context import RenderContext
from panelforge.render.fixture import make_chapter
from panelforge.render.inputs import ChapterInputs
from panelforge.render.renderer import Renderer, render_timeline


@pytest.fixture()
def chapter(tmp_path):
    return make_chapter(tmp_path, n_panels=2)


def _short(tl):
    for s in tl["shots"]:
        s["dur"] = 1.0
        for ln in s["lines"]:
            ln["at"], ln["dur"] = 0.1, 0.8
    return TL.retime(tl)


@pytest.mark.parametrize("aspect,size", [("16:9", (320, 180)), ("9:16", (180, 320))])
def test_tiny_render_two_shots_is_valid_mp4(chapter, aspect, size):
    inp = ChapterInputs(chapter)
    tl = _short(TL.build(inp, overrides={"aspect": aspect, "height": 180, "fps": 24}))
    out = chapter / "renders" / f"tiny-{aspect.replace(':', 'x')}.mp4"
    res = render_timeline(chapter, tl, out, audio=False, inputs=inp)
    info = encode.probe(out)
    assert (info["width"], info["height"]) == size
    assert info["fps"] == 24
    assert abs(info["duration"] - 2.0) < 0.1
    assert res["rendered"] == 2 and res["reused"] == 0
    again = render_timeline(
        chapter, tl, out, audio=False, inputs=ChapterInputs(chapter)
    )
    assert again["rendered"] == 0 and again["reused"] == 2
    tl["shots"][1]["camera"]["keys"][0]["zoom"] = 1.5
    third = render_timeline(
        chapter, tl, out, audio=False, inputs=ChapterInputs(chapter)
    )
    assert third["rendered"] == 1 and third["reused"] == 1


def test_frames_move_and_subtitles_draw_when_erased(chapter):
    inp = ChapterInputs(chapter)
    tl = TL.build(inp, overrides={"height": 180, "bubbles": "erase", "subtitles": True})
    ctx = RenderContext(inp, tl["settings"])
    r = Renderer(ctx, tl)
    f0 = r.frame(0, 0.6).copy()
    f1 = r.frame(0, r.shots[0]["dur"] * 0.9)
    assert f0.shape == (180, 320, 4)
    assert np.abs(f0.astype(int) - f1.astype(int)).mean() > 1.0, "camera should move"
    ctx2 = RenderContext(ChapterInputs(chapter), {**tl["settings"], "subtitles": False})
    r2 = Renderer(ctx2, tl)
    at = r.shots[0]["lines"][0]["at"] + 0.3
    with_sub, without = r.frame(0, at), r2.frame(0, at)
    lower = slice(int(180 * 0.6), 180)
    assert np.abs(with_sub[lower].astype(int) - without[lower].astype(int)).sum() > 0


def test_bubble_erase_removes_text(chapter):
    from panelforge.render import bubbles

    inp = ChapterInputs(chapter)
    img = inp.panel_image("p0001")
    b = inp.panel_bubbles("p0001")[0]
    box = [int(v) for v in inp.local_box("p0001", b["box"])]
    out = bubbles.erase(img, [(box, "speech")])
    x, y, w, h = box
    region_before = img[y + 30 : y + h - 30, x + 40 : x + w - 40, :3]
    region_after = out[y + 30 : y + h - 30, x + 40 : x + w - 40, :3]
    ink_before = (region_before.max(axis=2) < 40).sum()
    ink_after = (region_after.max(axis=2) < 40).sum()
    assert ink_before > 50  # the lettering was there
    assert ink_after < ink_before * 0.1


def test_tidy_text_sentence_case():
    from panelforge.render.bubbles import tidy_text

    assert (
        tidy_text("ALL OF THIS IS FOR THE EMPIRE. I WILL GO!")
        == "All of this is for the empire. I will go!"
    )
    assert tidy_text("Already fine.") == "Already fine."


def test_backdrop_modes_and_auto_choice(chapter):
    """Three fills, all darker than the art, and `auto` reaches for the
    stretched one only when the panel is much narrower than the frame."""
    import numpy as np

    from panelforge.render.context import RenderContext, backdrop_mode

    assert backdrop_mode("auto", (600, 1600), (1920, 1080)) == "stretch"
    assert backdrop_mode("auto", (1600, 900), (1920, 1080)) == "blur"
    assert backdrop_mode("black", (600, 1600), (1920, 1080)) == "black"

    inp = ChapterInputs(chapter)
    tl = TL.build(inp, overrides={"aspect": "16:9", "height": 180, "fps": 24})
    shot = tl["shots"][0]
    fills = {
        mode: RenderContext(inp, {**tl["settings"], "backdrop": mode}).backdrop(shot)
        for mode in ("blur", "stretch", "black")
    }
    assert fills["blur"].shape == fills["stretch"].shape == fills["black"].shape
    assert fills["black"][..., :3].max() == 0
    diff = np.abs(
        fills["stretch"][..., :3].astype(int) - fills["blur"][..., :3].astype(int)
    ).mean()
    assert diff > 1.0  # the stretched fill really is a different picture
    art = RenderContext(inp, tl["settings"]).base_image(shot)
    for mode in ("blur", "stretch"):
        assert fills[mode][..., :3].mean() < art[..., :3].mean()


def test_sound_setting_drops_voices_or_the_whole_track(chapter):
    from panelforge.render import timeline as TL
    from panelforge.render.inputs import ChapterInputs
    from panelforge.audio import mix

    inp = ChapterInputs(chapter)
    tl = TL.build(inp, {"style": "slideshow", "height": 90, "fps": 4})
    assert tl["settings"]["sound"] == "full" and tl["settings"]["layers"] == 1.0
    music = {**tl, "settings": {**tl["settings"], "sound": "music"}}
    out = chapter / "work" / "mix-test.wav"
    got = mix.mix_timeline(chapter, music, out)
    assert got and out.exists()  # music-only still produces a track
    from panelforge.render.renderer import render_timeline

    silent = {**tl, "settings": {**tl["settings"], "sound": "silent"}}
    silent["shots"] = silent["shots"][:1]
    res = render_timeline(
        chapter, silent, chapter / "work" / "silent.mp4", preview=True
    )
    assert res["audio"] is False and (chapter / "work" / "silent.mp4").exists()


def test_a_mostly_text_panel_keeps_its_lettering_in_erase_mode(chapter):
    """A caption slab is its lettering: erasing left a blank white panel on
    screen for seconds, so such panels keep their words and get no subtitle."""
    import numpy as np

    from panelforge import store
    from panelforge.render import bubbles as B
    from panelforge.render import timeline as TL
    from panelforge.render.context import RenderContext
    from panelforge.render.inputs import ChapterInputs

    panels = store.read(chapter / "panels.json")
    pid = panels["panels"][0]["id"]
    inp = ChapterInputs(chapter)
    tl = TL.build(
        inp, {"style": "slideshow", "height": 90, "fps": 4, "bubbles": "erase"}
    )
    ctx = RenderContext(inp, tl["settings"])
    assert B.keeps_its_lettering(ctx, pid) is False  # the fixture's balloon is small
    img = ctx.base_image(next(s for s in tl["shots"] if s["panel_id"] == pid))
    # now make the panel a caption slab: its one bubble covers most of it
    bubbles = store.read(chapter / "bubbles.json")
    box = panels["panels"][0]["box"]
    for b in bubbles["bubbles"]:
        if b["panel_id"] == pid:
            b["box"] = [box[0], box[1], int(box[2] * 0.9), int(box[3] * 0.8)]
    store.write(chapter / "bubbles.json", bubbles)
    inp2 = ChapterInputs(chapter)
    ctx2 = RenderContext(inp2, tl["settings"])
    assert B.keeps_its_lettering(ctx2, pid) is True
    kept = B.erased_panel(ctx2, pid, img)
    assert np.array_equal(kept, img)  # nothing erased
