"""
The second batch of features: modulation, the wand, depth of field, the
tracklist, saved presets, parallel rendering, and the direction convention.

The two that matter most are the loop-exactness of a modulated parameter -- it
would be easy to add a feature that quietly breaks the seam every other test
protects -- and the determinism of the parallel bed path, since "faster" is only
worth having if the output is the same.
"""

import json
import os

import numpy as np
import pytest
from PIL import Image, ImageDraw

from pulseforge import imageops, masks, modulation, presets, sequence, tracklist, wand
from pulseforge.emitters import common as emitter_common
from pulseforge.looping import LoopClock
from pulseforge.motion import registry as motion_registry

H, W, FPS, LOOP = 120, 200, 30, 8.0
SPEC = {"key": "strength", "type": "range", "min": 0.0, "max": 1.0, "step": 0.01}


class FakeCtx:
    fast = False
    art_pack = None

    def p(self, key, default=None):
        return default


# --------------------------------------------------------------------------
# modulation
# --------------------------------------------------------------------------
def test_a_plain_number_passes_straight_through():
    assert modulation.resolve(0.42, LoopClock(1.0, 30, LOOP, FPS), SPEC) == 0.42
    assert not modulation.is_modulated(0.42)


def test_an_lfo_swings_around_its_base():
    v = {"base": 0.5, "mod": "lfo", "amount": 0.3, "period": 4.0}
    seen = [
        modulation.resolve(v, LoopClock(t, int(t * FPS), LOOP, FPS), SPEC)
        for t in (0.0, 1.0, 2.0, 3.0)
    ]
    assert seen[0] == pytest.approx(0.5)
    assert max(seen) == pytest.approx(0.8, abs=1e-6)
    assert min(seen) == pytest.approx(0.2, abs=1e-6)


def test_modulation_returns_to_its_start_at_the_loop():
    v = {"base": 0.5, "mod": "lfo", "amount": 0.4, "period": 3.0}
    a = modulation.resolve(v, LoopClock(0.0, 0, LOOP, FPS), SPEC)
    b = modulation.resolve(v, LoopClock(LOOP, int(LOOP * FPS), LOOP, FPS), SPEC)
    assert a == pytest.approx(b, abs=1e-9)


def test_modulation_is_clamped_to_the_parameter_range():
    v = {"base": 0.95, "mod": "lfo", "amount": 0.5, "period": 4.0}
    seen = [
        modulation.resolve(v, LoopClock(t, 0, LOOP, FPS), SPEC)
        for t in np.arange(0, 8, 0.25)
    ]
    assert max(seen) <= 1.0 and min(seen) >= 0.0


def test_without_a_clock_the_base_value_is_used():
    assert modulation.resolve({"base": 0.3, "mod": "lfo", "amount": 0.5}) == 0.3
    assert modulation.strip({"a": {"base": 7, "mod": "lfo"}, "b": 2}) == {
        "a": 7,
        "b": 2,
    }


def test_audio_sources_are_flagged_as_needing_live_mode():
    assert modulation.needs_live({"base": 1, "mod": "sub", "amount": 0.2})
    assert not modulation.needs_live({"base": 1, "mod": "lfo", "amount": 0.2})
    assert "Bass" in modulation.describe({"base": 1, "mod": "sub", "amount": 0.25})


def test_an_unknown_source_falls_back_to_the_base():
    v = {"base": 0.4, "mod": "telepathy", "amount": 0.9}
    assert modulation.resolve(v, LoopClock(2.0, 60, LOOP, FPS), SPEC) == 0.4


def test_a_modulated_effect_still_loops_seamlessly():
    """The guarantee everything else rests on, with a moving parameter."""
    frame = np.full((H, W, 3), 100.0, dtype=np.float32)
    m = masks.build({"kind": "all"}, H, W)
    box = masks.bbox(m)
    params = {"strength": {"base": 0.4, "mod": "lfo", "amount": 0.35, "period": 4.0}}
    a, b = frame.copy(), frame.copy()
    motion_registry.apply_effect(
        "water", a, m, box, LoopClock(0.0, 0, LOOP, FPS, seed=1), params, FakeCtx()
    )
    motion_registry.apply_effect(
        "water",
        b,
        m,
        box,
        LoopClock(LOOP, int(LOOP * FPS), LOOP, FPS, seed=1),
        params,
        FakeCtx(),
    )
    assert np.abs(a - b).max() == pytest.approx(0.0, abs=1e-4)


def test_modulation_reaches_emitters_too():
    from pulseforge.emitters import registry as emitter_registry

    params = {"count": {"base": 40, "mod": "lfo", "amount": 20, "period": 4.0}}
    spec = {"key": "count", "type": "int", "min": 1, "max": 800}
    merged = emitter_registry.merge_params(
        "particles", params, LoopClock(1.0, 30, LOOP, FPS)
    )
    assert isinstance(merged["count"], int) and merged["count"] > 40


# --------------------------------------------------------------------------
# direction -- the regression that made rain fall upward
# --------------------------------------------------------------------------
def test_the_compass_matches_what_people_expect():
    for deg, want in [(0, (1, 0)), (90, (0, -1)), (180, (-1, 0)), (270, (0, 1))]:
        ux, uy = imageops.direction_vector(deg)
        assert (round(ux), round(uy)) == want


def _vertical_drift(angle, n=40, dt=0.1):
    """Net vertical movement of a crowd of particles over a short step.

    Looked at over a long window a particle wraps back to the start, so this
    takes a short step and ignores the few that crossed the boundary during it.
    """

    def at(t):
        _x, y, _p, _tr = emitter_common.crossing_path(
            LoopClock(t, int(t * FPS), LOOP, FPS, seed=1), n, 1, LOOP, angle
        )
        return y

    before, after = at(1.0), at(1.0 + dt)
    step = after - before
    step = step[np.abs(step) < 0.4]  # drop the ones that wrapped round
    return float(np.mean(step))


def test_rain_falls_downward():
    """285 is down and a little to the right. This was wrong once, and nothing
    visible caught it -- rain rose gently up the frame."""
    assert _vertical_drift(285) > 0.001


def test_bubbles_rise():
    assert _vertical_drift(90) < -0.001


# --------------------------------------------------------------------------
# the wand
# --------------------------------------------------------------------------
@pytest.fixture
def two_tone(tmp_path):
    im = Image.new("RGB", (240, 160))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 240, 80], fill=(60, 120, 220))  # sky
    d.rectangle([0, 80, 240, 160], fill=(40, 90, 60))  # ground
    path = tmp_path / "two.png"
    im.save(path)
    return str(path)


def test_more_tolerance_selects_more(two_tone):
    small = wand.select(two_tone, 0.5, 0.2, tolerance=0.02).mean()
    large = wand.select(two_tone, 0.5, 0.2, tolerance=0.35).mean()
    assert 0.0 < small <= large
    assert small == pytest.approx(0.5, abs=0.08), "the sky is half the picture"


def test_contiguous_stops_at_the_edge(tmp_path):
    im = Image.new("RGB", (240, 160), (20, 20, 20))
    d = ImageDraw.Draw(im)
    d.rectangle([10, 10, 70, 70], fill=(230, 60, 60))
    d.rectangle([160, 90, 220, 150], fill=(230, 60, 60))  # a second, separate patch
    path = tmp_path / "two-patches.png"
    im.save(path)
    one = wand.select(str(path), 0.16, 0.25, tolerance=0.1, contiguous=True).sum()
    both = wand.select(str(path), 0.16, 0.25, tolerance=0.1, contiguous=False).sum()
    assert both > one * 1.6, "'everything similar' should find the second patch"


def test_the_wand_takes_what_you_clicked_and_not_the_rest(two_tone):
    sky = wand.select(two_tone, 0.5, 0.2, tolerance=0.05)
    ground = wand.select(two_tone, 0.5, 0.8, tolerance=0.05)
    h = sky.shape[0]
    assert sky[: h // 3].mean() > 0.9 and sky[2 * h // 3 :].mean() < 0.1
    assert ground[2 * h // 3 :].mean() > 0.9 and ground[: h // 3].mean() < 0.1


def test_the_wand_saves_a_usable_brush_mask(two_tone, tmp_path):
    m = wand.select(two_tone, 0.5, 0.2, tolerance=0.2)
    out = tmp_path / "m.png"
    wand.to_png(m, out, 240, 160, feather=0.02)
    built = masks.build({"kind": "brush", "brush": "m.png"}, 160, 240, tmp_path)
    assert built[20, 120] > 0.8 and built[140, 120] < 0.2


# --------------------------------------------------------------------------
# depth of field
# --------------------------------------------------------------------------
def _dof_shot(tmp_path):
    im = Image.new("RGB", (320, 180))
    d = ImageDraw.Draw(im)
    for x in range(0, 320, 16):  # hard stripes: blur is unmistakable
        d.rectangle([x, 0, x + 8, 180], fill=(240, 240, 240))
    im.save(tmp_path / "stripes.png")
    return {"image": "stripes.png", "loop_seconds": 2.0, "layers": [], "emitters": []}


def _detail(a):
    f = a.astype(float)
    return float(np.abs(np.diff(f, axis=1)).mean())


def test_focus_decides_what_is_sharp(tmp_path):
    from pulseforge.scenes import living
    from pulseforge.scenes.registry import SceneContext

    shot = _dof_shot(tmp_path)

    def ctx(look):
        s = dict(shot)
        s["look"] = look
        return SceneContext(
            W,
            H,
            FPS,
            4,
            2.0,
            {},
            {"_shot": s, "_base_dir": str(tmp_path), "_mask_dir": str(tmp_path)},
            [],
            None,
            str(tmp_path),
            fast=True,
        )

    sharp = _detail(living.still(ctx({"aperture": 0.0}), 0.0))
    blurred = _detail(living.still(ctx({"focus": 1.0, "aperture": 1.0}), 0.0))
    in_focus = _detail(living.still(ctx({"focus": 0.0, "aperture": 1.0}), 0.0))
    assert blurred < sharp * 0.7, "the background should soften when focus is elsewhere"
    assert in_focus == pytest.approx(sharp, rel=0.02), "focused on it, it stays sharp"


def test_haze_fades_the_distance(tmp_path):
    from pulseforge.scenes import living
    from pulseforge.scenes.registry import SceneContext

    shot = _dof_shot(tmp_path)

    def ctx(look):
        s = dict(shot)
        s["look"] = look
        return SceneContext(
            W,
            H,
            FPS,
            4,
            2.0,
            {},
            {"_shot": s, "_base_dir": str(tmp_path), "_mask_dir": str(tmp_path)},
            [],
            None,
            str(tmp_path),
            fast=True,
        )

    plain = living.still(ctx({"haze": 0.0}), 0.0).astype(int)
    hazed = living.still(ctx({"haze": 0.6, "haze_color": "#ff0000"}), 0.0).astype(int)
    assert hazed[..., 0].mean() > plain[..., 0].mean() + 10


def test_blur_buckets_keep_the_variants_few():
    from pulseforge.layers import blur_bucket

    assert blur_bucket(0.4) == 0
    assert blur_bucket(4) == blur_bucket(4.4)
    assert blur_bucket(1000) <= 48


# --------------------------------------------------------------------------
# the tracklist
# --------------------------------------------------------------------------
def test_timestamps_read_the_way_youtube_wants():
    assert tracklist.timestamp(0) == "0:00"
    assert tracklist.timestamp(7) == "0:07"
    assert tracklist.timestamp(605) == "10:05"
    assert tracklist.timestamp(3723) == "1:02:03"


def test_the_tracklist_lines_up_with_the_timeline():
    spans, total = sequence.audio_spans([120.0, 90.0], crossfade=2.0)
    built = tracklist.build(spans, [{"title": "One"}, {"title": "Two"}], None, total)
    assert built["description"].startswith("0:00 One")
    assert "1:58 Two" in built["description"]


def test_a_missing_title_falls_back_to_the_filename():
    spans, total = sequence.audio_spans([60.0])
    built = tracklist.build(spans, [{}], ["my_first-track.mp3"], total)
    assert "my first track" in built["description"]


def test_youtube_rules_are_reported_not_assumed():
    spans, total = sequence.audio_spans([60.0, 5.0, 60.0])
    built = tracklist.build(
        spans, [{"title": "a"}, {"title": "b"}, {"title": "c"}], None, total
    )
    assert any("ten seconds" in w for w in built["warnings"])
    spans2, total2 = sequence.audio_spans([60.0])
    assert any(
        "at least 3" in w
        for w in tracklist.build(spans2, [{"title": "x"}], None, total2)["warnings"]
    )


def test_chapter_metadata_is_well_formed_and_escaped():
    spans, total = sequence.audio_spans([60.0, 60.0])
    meta = tracklist.build(spans, [{"title": "a=b;c"}, {"title": "Two"}], None, total)[
        "ffmetadata"
    ]
    assert meta.startswith(";FFMETADATA1")
    assert meta.count("[CHAPTER]") == 2
    assert "START=0" in meta and "END=60000" in meta
    assert r"a\=b\;c" in meta


# --------------------------------------------------------------------------
# saved presets
# --------------------------------------------------------------------------
def test_a_saved_look_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(presets.config, "PRESETS_DIR", tmp_path / "presets")
    shot = {
        "layers": [],
        "emitters": [{"id": "stars", "params": {"count": 30}}],
        "look": {"warmth": -0.4},
        "camera": {"push": 0.2},
    }
    pid = presets.save_user_preset("Cold Night", shot)
    assert pid.startswith("user:")
    listed = {p["id"]: p for p in presets.presets_as_list()}
    assert pid in listed and listed[pid]["user"] is True

    applied = presets.apply_to(pid, {"image": "keep-me.png"})
    assert applied["image"] == "keep-me.png", "a preset must not touch the picture"
    assert applied["look"]["warmth"] == -0.4
    assert [e["id"] for e in applied["emitters"]] == ["stars"]

    assert presets.delete_user_preset(pid) is True
    assert pid not in {p["id"] for p in presets.presets_as_list()}


def test_a_saved_look_brings_its_regions_with_it(tmp_path, monkeypatch):
    monkeypatch.setattr(presets.config, "PRESETS_DIR", tmp_path / "presets")
    src_masks = tmp_path / "src"
    src_masks.mkdir()
    Image.fromarray(np.full((20, 20), 255, np.uint8)).save(src_masks / "painted.png")
    shot = {
        "layers": [
            {
                "name": "sky",
                "effect": "sky_clouds",
                "params": {},
                "region": {"kind": "brush", "brush": "painted.png"},
            }
        ]
    }
    pid = presets.save_user_preset("With Regions", shot, mask_dir=str(src_masks))

    dst = tmp_path / "otherproject"
    applied = presets.apply_to(pid, {}, mask_dir=str(dst))
    brush = applied["layers"][0]["region"]["brush"]
    assert (dst / brush).exists(), "the painted region should have come along"
    assert brush != "painted.png", "and been renamed so it cannot collide"


def test_builtin_presets_cannot_be_deleted():
    with pytest.raises(KeyError):
        presets.delete_user_preset("lofi_lake")


# --------------------------------------------------------------------------
# parallel rendering
# --------------------------------------------------------------------------
@pytest.mark.slow
def test_parallel_and_sequential_beds_are_identical(tmp_path):
    """Faster is only worth having if the output is the same."""
    import hashlib

    from pulseforge import config, formats, render
    from pulseforge.bedworker import run_job

    Image.new("RGB", (200, 120), (60, 90, 150)).save(tmp_path / "bg.png")
    fmt = dict(formats.get("long_1080p"))
    fmt.update({"w": 160, "h": 90, "fps": 10, "_quality": "draft"})
    settings = dict(config.load_settings())
    settings["threads"] = 2  # identical on both sides: x264 varies with this

    shots = [
        {
            "image": "bg.png",
            "loop_seconds": 0.6,
            "layers": [],
            "look": {},
            "emitters": [{"id": "birds", "params": {"count": 3}}],
        },
        {
            "image": "bg.png",
            "loop_seconds": 0.6,
            "emitters": [],
            "look": {},
            "layers": [
                {"name": "a", "effect": "rays", "region": {"kind": "all"}, "params": {}}
            ],
        },
    ]

    def jobs(tag):
        d = tmp_path / tag
        d.mkdir()
        return [
            {
                "shot": s,
                "path": str(d / f"b{i}.mp4"),
                "scene_id": "living",
                "params": {},
                "fmt": fmt,
                "art_pack": None,
                "settings": settings,
                "tmpdir": str(d),
                "base_dir": str(tmp_path),
                "mask_dir": str(tmp_path),
            }
            for i, s in enumerate(shots)
        ]

    seq = jobs("seq")
    for j in seq:
        run_job(j)
    par = jobs("par")
    ok = render._render_beds_in_parallel(
        par, 2, str(tmp_path / "par"), lambda s: None, lambda f: None, lambda: False
    )
    assert ok, "the parallel path bailed out"

    digest = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    assert [digest(j["path"]) for j in seq] == [digest(j["path"]) for j in par]


def test_a_bed_job_serialises_to_json():
    """Jobs cross a process boundary as JSON, so they have to survive the trip."""
    job = {
        "shot": {"image": "a.png", "layers": [], "emitters": [], "look": {}},
        "path": "/tmp/x.mp4",
        "scene_id": "living",
        "params": {},
        "fmt": {"w": 1920, "h": 1080, "fps": 30},
        "art_pack": None,
        "settings": {"crf": 18},
        "tmpdir": "/tmp",
        "base_dir": "/tmp",
        "mask_dir": "/tmp",
    }
    assert json.loads(json.dumps(job)) == job
