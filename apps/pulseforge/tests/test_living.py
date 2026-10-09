"""
The living-still pipeline.

The test that matters most here is loop-exactness. A shot is rendered once as a
short bed and then repeated under a long song, so if any effect or emitter is
not in exactly the same state at t=0 and t=loop_seconds, every repeat shows a
visible jump. That guarantee is checked generically off the registries, so an
effect added later is covered the moment it is registered rather than whenever
someone remembers to write a test for it.
"""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from pulseforge import imageops, masks, presets, sequence
from pulseforge.emitters import registry as emitter_registry
from pulseforge.looping import LoopClock, snapped_period
from pulseforge.motion import registry as motion_registry

H, W, FPS = 180, 320, 30
LOOP = 8.0


class FakeCtx:
    """The bits of SceneContext an effect or emitter actually touches."""

    fast = False
    art_pack = None
    w, h, fps = W, H, FPS

    def p(self, key, default=None):
        return default


@pytest.fixture
def frame():
    rng = np.random.default_rng(7)
    return (rng.random((H, W, 3)) * 140 + 50).astype(np.float32)


@pytest.fixture
def region_mask():
    region = {
        "kind": "polygon",
        "points": [[0.2, 0.25], [0.8, 0.25], [0.8, 0.7], [0.2, 0.7]],
        "feather": 0.03,
    }
    return masks.build(region, H, W)


# --------------------------------------------------------------------------
# the primitives
# --------------------------------------------------------------------------
def test_polygon_mask_covers_the_shape_it_was_given():
    region = {"kind": "polygon", "points": [[0, 0], [1, 0], [1, 0.5], [0, 0.5]]}
    m = masks.build(region, 200, 100)
    assert m[:99].mean() > 0.98, "the top half should be fully inside"
    assert m[105:].mean() < 0.02, "the bottom half should be fully outside"


def test_feather_softens_the_edge_without_moving_it():
    pts = [[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75]]
    hard = masks.build({"kind": "polygon", "points": pts, "feather": 0.0}, 200, 200)
    soft = masks.build({"kind": "polygon", "points": pts, "feather": 0.06}, 200, 200)
    assert hard[100, 100] == pytest.approx(1.0)
    assert soft[100, 100] == pytest.approx(1.0, abs=0.02)
    edge = soft[100, 45:55]
    assert 0.0 < edge.mean() < 1.0, "the edge should ramp, not step"
    assert abs(float(hard.mean() - soft.mean())) < 0.05


def test_brush_mask_loads_from_a_png(tmp_path):
    arr = np.zeros((60, 80), dtype=np.uint8)
    arr[10:30, 20:60] = 255
    Image.fromarray(arr).save(tmp_path / "m.png")
    m = masks.build({"kind": "brush", "brush": "m.png"}, 60, 80, tmp_path)
    assert m[20, 40] == pytest.approx(1.0)
    assert m[50, 10] == pytest.approx(0.0)


def test_missing_brush_is_empty_not_an_error(tmp_path):
    m = masks.build({"kind": "brush", "brush": "nope.png"}, 40, 40, tmp_path)
    assert m.max() == 0.0


def test_bbox_finds_the_region_and_nothing_else(region_mask):
    y0, y1, x0, x1 = masks.bbox(region_mask)
    assert 0 < y0 < H * 0.3 and H * 0.6 < y1 <= H
    assert 0 < x0 < W * 0.3 and W * 0.7 < x1 <= W


def test_displace_moves_pixels_only_inside_the_mask():
    f = np.zeros((40, 60, 3), dtype=np.float32)
    f[:, 30] = 200.0
    m = np.zeros((40, 60), dtype=np.float32)
    m[10:30, :] = 1.0
    before = f.copy()
    imageops.displace(f, dx=-4.0, dy=0.0, mask=m, box=(0, 40, 0, 60))
    assert np.abs(f[0:9] - before[0:9]).max() == 0.0, "outside the mask must not move"
    assert f[20, 34, 0] > 150, "inside the mask the line should have shifted"


def test_periodic_noise_meets_itself_at_the_wrap():
    n = imageops.periodic_noise(120, 160, cells=3, seed=5)
    across = float(np.abs(n[:, 0] - n[:, -1]).mean())
    neighbours = float(np.abs(n[:, 1] - n[:, 0]).mean())
    assert across < neighbours * 3, "the wrap should be no harsher than a normal step"


def test_box_blur_conserves_brightness():
    a = np.zeros((21, 21), dtype=np.float32)
    a[10, 10] = 1.0
    assert float(imageops.box_blur(a, 3).sum()) == pytest.approx(1.0, abs=1e-4)


# --------------------------------------------------------------------------
# loop-exactness
# --------------------------------------------------------------------------
def test_periods_snap_to_whole_cycles():
    assert snapped_period(3.7, 12.0) == pytest.approx(4.0)
    assert snapped_period(5.0, 12.0) == pytest.approx(6.0)
    assert snapped_period(100.0, 12.0) == pytest.approx(
        12.0
    ), "never slower than one cycle"


@pytest.mark.parametrize("period", [1.3, 3.7, 5.0, 11.0])
def test_the_clock_returns_to_where_it_started(period):
    a = LoopClock(0.0, 0, LOOP, FPS)
    b = LoopClock(LOOP, int(LOOP * FPS), LOOP, FPS)
    assert a.wave(period) == pytest.approx(b.wave(period), abs=1e-9)
    assert a.saw(period) == pytest.approx(b.saw(period), abs=1e-9)


EFFECT_IDS = sorted(motion_registry.EFFECTS)
EMITTER_IDS = sorted(emitter_registry.EMITTERS)


def test_the_registries_are_populated():
    assert len(EFFECT_IDS) >= 9
    assert len(EMITTER_IDS) >= 11


@pytest.mark.parametrize("effect_id", EFFECT_IDS)
def test_every_effect_is_loop_exact(effect_id, frame, region_mask):
    """Identical at t=0 and t=loop -- the seam has to be invisible."""
    box = masks.bbox(region_mask, pad=2)
    a, b = frame.copy(), frame.copy()
    motion_registry.apply_effect(
        effect_id,
        a,
        region_mask,
        box,
        LoopClock(0.0, 0, LOOP, FPS, seed=3),
        {},
        FakeCtx(),
    )
    motion_registry.apply_effect(
        effect_id,
        b,
        region_mask,
        box,
        LoopClock(LOOP, int(LOOP * FPS), LOOP, FPS, seed=3),
        {},
        FakeCtx(),
    )
    assert np.abs(a - b).max() == pytest.approx(0.0, abs=1e-4)


@pytest.mark.parametrize("effect_id", EFFECT_IDS)
def test_every_effect_stays_inside_its_region(effect_id, frame, region_mask):
    if effect_id == "glow_pulse":
        pytest.skip("glow deliberately spills past the region -- that is the bloom")
    box = masks.bbox(region_mask, pad=2)
    before = frame.copy()
    motion_registry.apply_effect(
        effect_id,
        frame,
        region_mask,
        box,
        LoopClock(LOOP * 0.37, 88, LOOP, FPS, seed=3),
        {},
        FakeCtx(),
    )
    outside = region_mask < 0.001
    assert np.abs(frame - before)[outside].max() < 0.5


@pytest.mark.parametrize("effect_id", [e for e in EFFECT_IDS if e != "frames"])
def test_every_effect_actually_does_something(effect_id, frame, region_mask):
    """`frames` is excluded: with no artwork configured it correctly does nothing."""
    box = masks.bbox(region_mask, pad=2)
    before = frame.copy()
    motion_registry.apply_effect(
        effect_id,
        frame,
        region_mask,
        box,
        LoopClock(LOOP * 0.37, 88, LOOP, FPS, seed=3),
        {},
        FakeCtx(),
    )
    assert np.abs(frame - before).max() > 1.0


@pytest.mark.parametrize("emitter_id", EMITTER_IDS)
def test_every_emitter_is_loop_exact(emitter_id, frame):
    a, b = frame.copy(), frame.copy()
    emitter_registry.draw_emitter(
        emitter_id, a, LoopClock(0.0, 0, LOOP, FPS, seed=5), {}, FakeCtx()
    )
    emitter_registry.draw_emitter(
        emitter_id,
        b,
        LoopClock(LOOP, int(LOOP * FPS), LOOP, FPS, seed=5),
        {},
        FakeCtx(),
    )
    assert np.abs(a - b).max() == pytest.approx(0.0, abs=1e-4)


@pytest.mark.parametrize("emitter_id", EMITTER_IDS)
def test_every_emitter_is_deterministic(emitter_id, frame):
    """Same clock, same picture -- particles are a function of time, not state."""
    a, b = frame.copy(), frame.copy()
    for target in (a, b):
        emitter_registry.draw_emitter(
            emitter_id, target, LoopClock(2.5, 75, LOOP, FPS, seed=5), {}, FakeCtx()
        )
    assert np.abs(a - b).max() == 0.0


@pytest.mark.parametrize("emitter_id", [e for e in EMITTER_IDS if e != "sprites"])
def test_every_emitter_draws_something(emitter_id, frame):
    """`sprites` is excluded: with no artwork configured it correctly draws nothing."""
    before = frame.copy()
    emitter_registry.draw_emitter(
        emitter_id, frame, LoopClock(2.5, 75, LOOP, FPS, seed=5), {}, FakeCtx()
    )
    assert np.abs(frame - before).max() > 1.0


def test_every_registered_thing_declares_a_usable_schema():
    for meta in list(motion_registry.EFFECTS.values()) + list(
        emitter_registry.EMITTERS.values()
    ):
        assert meta.get("label") and meta.get("description") and meta.get("family")
        for spec in meta.get("params", []):
            assert spec.get("key") and spec.get("label") and spec.get("type")
            assert spec.get("default") is not None, f"{meta['id']}.{spec['key']}"
            if spec["type"] in ("range", "int"):
                assert spec["min"] <= spec["default"] <= spec["max"]


# --------------------------------------------------------------------------
# the timeline
# --------------------------------------------------------------------------
def test_crossfade_shortens_the_timeline_by_the_overlap():
    spans, total = sequence.audio_spans([120.0, 90.0, 150.0], crossfade=2.0)
    assert total == pytest.approx(360.0 - 4.0)
    assert [s["start"] for s in spans] == pytest.approx([0.0, 118.0, 206.0])


def test_a_gap_lengthens_it():
    _spans, total = sequence.audio_spans([120.0, 90.0], gap=3.0)
    assert total == pytest.approx(213.0)


def test_shots_cycle_to_cover_the_whole_timeline():
    spans, total = sequence.audio_spans([100.0, 60.0, 80.0])
    plan = sequence.plan_shots([{"image": "a"}, {"image": "b"}], spans, total)
    assert [s["image"] for s in plan] == ["a", "b", "a"]
    assert plan[-1]["start"] + plan[-1]["duration"] == pytest.approx(total)
    assert plan[0]["duration"] == pytest.approx(100.0), "hold=song follows its song"


def test_a_fixed_hold_is_honoured():
    spans, total = sequence.audio_spans([200.0])
    plan = sequence.plan_shots([{"image": "a", "hold": 30}], spans, total)
    assert len(plan) > 1
    assert plan[0]["duration"] == pytest.approx(30.0)
    assert plan[-1]["start"] + plan[-1]["duration"] == pytest.approx(total)


def test_no_shots_still_produces_one():
    spans, total = sequence.audio_spans([45.0])
    assert len(sequence.plan_shots([], spans, total)) == 1


def test_captions_are_windowed_to_their_own_song():
    spans, _total = sequence.audio_spans([60.0, 60.0])
    vf = sequence.text_filter(
        [{"title": "One"}, {"title": "Two", "subtitle": "b"}], spans, 1920, 1080
    )
    assert vf.count("drawtext=") == 3
    assert "between(t,0.00," in vf and "between(t,60.00," in vf


def test_caption_text_is_escaped_for_ffmpeg():
    spans, _ = sequence.audio_spans([30.0])
    vf = sequence.text_filter([{"title": "a:b'c"}], spans, 640, 360)
    assert "\\:" in vf and "'c" not in vf


# --------------------------------------------------------------------------
# presets and detection
# --------------------------------------------------------------------------
def test_a_preset_brings_its_look_and_leaves_the_image_alone():
    shot = presets.apply_to("lofi_lake", {"image": "bg.png"})
    assert shot["image"] == "bg.png"
    assert shot["look"]["warmth"] > 0
    assert [e["id"] for e in shot["emitters"]] == ["birds", "dust"]
    assert shot["preset"] == "lofi_lake"


def test_a_preset_only_uses_regions_it_asked_for():
    found = [
        {"name": "sky", "region": {"kind": "brush", "brush": "s.png"}},
        {"name": "lights", "region": {"kind": "brush", "brush": "l.png"}},
    ]
    shot = presets.apply_to("lofi_lake", {}, found)
    names = [layer["name"] for layer in shot["layers"]]
    assert "sky" in names, "lofi_lake wants the sky"
    assert "lights" not in names, "it does not ask for lights"


def test_every_preset_applies_without_regions():
    for meta in presets.presets_as_list():
        shot = presets.apply_to(meta["id"], {"image": "x.png"})
        assert "look" in shot and "camera" in shot


def test_unknown_preset_raises():
    with pytest.raises(KeyError):
        presets.apply_to("nope", {})


def test_detection_finds_sky_above_and_water_below(tmp_path):
    from pulseforge import autoregions

    im = Image.new("RGB", (400, 300))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 400, 150], fill=(120, 160, 235))  # sky
    d.rectangle([0, 150, 400, 300], fill=(30, 60, 110))  # water
    path = tmp_path / "scene.png"
    im.save(path)

    found = {r["name"]: r for r in autoregions.suggest(str(path))}
    assert "sky" in found and found["sky"]["effect"] == "sky_clouds"
    assert "water" in found and found["water"]["effect"] == "water"
    sky, water = found["sky"]["mask"], found["water"]["mask"]
    h = sky.shape[0]
    assert sky[: h // 3].mean() > sky[2 * h // 3 :].mean(), "sky belongs at the top"
    assert water[2 * h // 3 :].mean() > water[: h // 3].mean(), "water at the bottom"


# --------------------------------------------------------------------------
# the scene itself
# --------------------------------------------------------------------------
def _shot_with_everything(tmp_path):
    im = Image.new("RGB", (640, 360))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 640, 200], fill=(110, 140, 210))
    d.rectangle([0, 200, 640, 360], fill=(30, 70, 110))
    im.save(tmp_path / "bg.png")
    return {
        "image": "bg.png",
        "loop_seconds": 4.0,
        "layers": [
            {
                "name": "sky",
                "effect": "sky_clouds",
                "region": {
                    "kind": "polygon",
                    "points": [[0, 0], [1, 0], [1, 0.5], [0, 0.5]],
                },
                "params": {"amount": 0.5},
            },
            {
                "name": "lake",
                "effect": "water",
                "depth": 0.2,
                "region": {
                    "kind": "polygon",
                    "points": [[0, 0.55], [1, 0.55], [1, 1], [0, 1]],
                },
                "params": {"strength": 0.4},
            },
        ],
        "emitters": [{"id": "birds", "depth": 0.4, "params": {"count": 5}}],
        "look": {"vignette": 0.3, "grain": 0.05, "bloom": 0.2},
    }


def _living_ctx(tmp_path, shot, n_frames):
    from pulseforge.scenes.registry import SceneContext

    return SceneContext(
        W,
        H,
        FPS,
        n_frames,
        shot["loop_seconds"],
        {},
        {"_shot": shot, "_base_dir": str(tmp_path), "_mask_dir": str(tmp_path)},
        [],
        None,
        str(tmp_path),
        fast=True,
    )


def test_the_living_scene_renders_frames_that_are_not_blank(tmp_path):
    from pulseforge.scenes import living

    shot = _shot_with_everything(tmp_path)
    out = list(living.frames(_living_ctx(tmp_path, shot, 5)))
    assert len(out) == 5
    for fr in out:
        assert fr.shape == (H, W, 3) and fr.dtype == np.uint8
        assert fr.mean() > 5


def test_a_whole_shot_loops_seamlessly(tmp_path):
    """The guarantee the bed-and-repeat render depends on, end to end."""
    from pulseforge.scenes import living

    shot = _shot_with_everything(tmp_path)
    n = int(shot["loop_seconds"] * FPS)
    frames = list(living.frames(_living_ctx(tmp_path, shot, n + 1)))
    seam = np.abs(frames[0].astype(int) - frames[n].astype(int))
    # bit-identical, not merely close: anything else accumulates into a visible
    # pulse when the bed is repeated dozens of times under a long song
    assert seam.max() == 0, f"the loop seam is not clean (max {seam.max()})"


def test_the_picture_actually_moves_during_the_loop(tmp_path):
    from pulseforge.scenes import living

    shot = _shot_with_everything(tmp_path)
    frames = list(living.frames(_living_ctx(tmp_path, shot, 40)))
    assert np.abs(frames[0].astype(int) - frames[39].astype(int)).mean() > 0.5


def test_a_shot_with_no_image_still_renders(tmp_path):
    from pulseforge.scenes import living

    shot = {"image": "", "loop_seconds": 3.0, "layers": [], "emitters": [], "look": {}}
    out = list(living.frames(_living_ctx(tmp_path, shot, 3)))
    assert len(out) == 3 and out[0].shape == (H, W, 3)


def test_a_broken_layer_does_not_take_the_render_down(tmp_path):
    """One bad layer should cost that layer, not the whole video."""
    from pulseforge.scenes import living

    shot = _shot_with_everything(tmp_path)
    shot["layers"].append(
        {"name": "bad", "effect": "no_such_effect", "region": {"kind": "all"}}
    )
    shot["emitters"].append({"id": "no_such_emitter", "params": {}})
    out = list(living.frames(_living_ctx(tmp_path, shot, 3)))
    assert len(out) == 3 and out[0].mean() > 5


def test_still_matches_the_frame_at_the_same_time(tmp_path):
    """The editor's scrubber and the renderer must agree, or tuning is a lie."""
    from pulseforge.scenes import living

    shot = _shot_with_everything(tmp_path)
    n = 12
    frames = list(living.frames(_living_ctx(tmp_path, shot, n)))
    one = living.still(_living_ctx(tmp_path, shot, n), 6 / FPS)
    assert np.abs(one.astype(int) - frames[6].astype(int)).max() <= 1
