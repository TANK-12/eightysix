"""
The third batch: video backgrounds, ambience, the analogue look, overlays,
cards, repeat-to-length, bulk shots and the thumbnail maker.

The ones worth writing carefully are the ambience beds -- where "sounds like
rain" has to become a measurement rather than a hope -- and the video loop,
where the seam is a cross-dissolve rather than an identity and so needs a
different assertion from every other loop test in this suite.
"""

import numpy as np
import pytest
from PIL import Image

from pulseforge import ambience, overlays, sequence, tracklist, videosource

SR = ambience.SR


# --------------------------------------------------------------------------
# ambience
# --------------------------------------------------------------------------
def _bands(mono, n=2**15):
    spec = np.abs(np.fft.rfft(mono[:n])) ** 2
    fr = np.fft.rfftfreq(n, 1.0 / SR)
    total = max(float(spec.sum()), 1e-12)
    edges = [(0, 200), (200, 1000), (1000, 4000), (4000, 12000), (12000, 24000)]
    return [100 * float(spec[(fr >= lo) & (fr < hi)].sum()) / total for lo, hi in edges]


def test_every_bed_is_registered_with_a_description():
    listed = ambience.beds_as_list()
    assert {b["id"] for b in listed} == set(ambience.BY_ID)
    for b in listed:
        assert b["label"] and b["description"]
        assert "fn" not in b, "the generator function should not go over the API"


@pytest.mark.parametrize("bed", sorted(ambience.BY_ID))
def test_beds_are_the_right_shape_and_level(bed):
    audio = ambience.generate(bed, seconds=3.0, seed=2)
    assert audio.shape == (int(3.0 * SR), 2)
    assert np.abs(audio).max() <= 1.0, "must not clip"
    mono = audio.mean(axis=1)
    rms = float(np.sqrt((mono**2).mean()))
    assert 0.08 < rms < 0.35, f"level is off: {rms}"
    assert float(np.abs(mono).max()) / rms < 8.0, "too peaky to sit under music"


@pytest.mark.parametrize(
    "bed,band,minimum",
    [
        # each bed has to actually live where its name says it does; this is
        # what stops "rain" quietly becoming thin hiss or sub-bass rumble
        ("rain", 2, 35.0),  # 1-4 kHz
        ("fire", 1, 40.0),  # 200 Hz - 1 kHz
        ("vinyl", 2, 30.0),  # 1-4 kHz
        ("wind", 1, 40.0),  # 200 Hz - 1 kHz
        ("waves", 1, 35.0),  # 200 Hz - 1 kHz
    ],
)
def test_each_bed_sits_in_the_right_part_of_the_spectrum(bed, band, minimum):
    mono = ambience.generate(bed, seconds=3.0, seed=2).mean(axis=1)
    got = _bands(mono)
    assert got[band] >= minimum, f"{bed} energy by band: {[round(v, 1) for v in got]}"


def test_nothing_is_mostly_sub_bass():
    """A tilt with no high-pass piles everything under 200 Hz. It did once."""
    for bed in ambience.BY_ID:
        mono = ambience.generate(bed, seconds=3.0, seed=2).mean(axis=1)
        assert _bands(mono)[0] < 40.0, f"{bed} is mostly rumble"


def test_a_bed_is_generated_deterministically():
    a = ambience.generate("rain", seconds=1.0, seed=5)
    b = ambience.generate("rain", seconds=1.0, seed=5)
    assert np.array_equal(a, b)


def test_the_ends_are_dissolved_so_it_can_repeat():
    mono = ambience.generate("rain", seconds=2.0, seed=1).mean(axis=1)
    # the wrap should be no more of a jump than any other pair of samples
    step = float(np.abs(np.diff(mono)).mean())
    assert abs(float(mono[0] - mono[-1])) < step * 12


def test_writing_a_wav_gives_a_real_file(tmp_path):
    import wave

    path = ambience.write_wav("fire", tmp_path / "a.wav", seconds=1.0)
    with wave.open(str(path)) as w:
        assert w.getnchannels() == 2 and w.getframerate() == SR
        assert w.getnframes() == int(1.0 * SR)


def test_an_unknown_bed_raises():
    with pytest.raises(KeyError):
        ambience.generate("bagpipes")


# --------------------------------------------------------------------------
# repeat to length
# --------------------------------------------------------------------------
def test_repeat_reaches_the_target_without_new_files():
    paths, passes = sequence.expand_for_target(
        ["a.mp3", "b.mp3"], [120.0, 100.0], 0.0, 0.0, 3600
    )
    assert passes == 17 and len(paths) == 34
    assert passes * 220 >= 3600


def test_no_target_means_one_pass():
    assert sequence.expand_for_target(["a"], [60.0], 0, 0, 0)[1] == 1
    assert sequence.expand_for_target([], [], 0, 0, 3600)[1] == 1


def test_repeat_is_capped_so_a_typo_cannot_explode():
    _paths, passes = sequence.expand_for_target(["a"], [1.0], 0, 0, 10_000_000)
    assert passes <= 400


def test_repeated_spans_line_up_end_to_end():
    spans, total = sequence.audio_spans([60.0, 40.0])
    out = sequence.repeat_spans(spans, 3, total)
    assert len(out) == 6
    assert [round(s["start"], 1) for s in out] == [
        0.0,
        60.0,
        100.0,
        160.0,
        200.0,
        260.0,
    ]
    assert out[-1]["end"] == pytest.approx(300.0)


def test_captions_survive_a_repeated_playlist():
    """Cards are per song, spans are per play -- they have to wrap, not run out."""
    spans, total = sequence.audio_spans([60.0, 40.0])
    repeated = sequence.repeat_spans(spans, 3, total)
    vf = sequence.text_filter(
        [{"title": "One"}, {"title": "Two"}], repeated, 1920, 1080
    )
    assert vf.count("drawtext=") == 6


# --------------------------------------------------------------------------
# overlays
# --------------------------------------------------------------------------
def test_the_progress_groove_is_a_static_filter():
    vf = overlays.progress_track(1080)
    assert vf.count("drawbox") == 1 and "iw" in vf


def test_the_progress_fill_slides_with_time():
    """It has to be an overlay: `drawbox` has no time variable -- its `t` is the
    border thickness, so a `t`-based width reads a constant and sits full width.
    That shipped once and was only caught by measuring the rendered frames."""
    f = overlays.progress_overlay(210.0, 1920, "vin", 3, "vout", 0.8)
    assert "overlay=" in f and "t/210.000" in f
    assert "drawbox" not in f
    assert "[3:v]" in f and "[vout]" in f


def test_the_progress_input_is_a_bar_the_width_of_the_frame():
    args = overlays.progress_input(1920, 1080)
    assert args[:3] == ["-f", "lavfi", "-i"]
    assert "1920x" in args[3] and args[3].startswith("color=")


def test_wants_progress_reads_the_project_setting():
    assert overlays.wants_progress({"progress": True})
    assert not overlays.wants_progress({}) and not overlays.wants_progress(None)


def test_now_playing_covers_each_song_for_its_whole_span():
    spans, _ = sequence.audio_spans([60.0, 40.0])
    vf = overlays.now_playing(spans, [{"title": "One"}, {"title": "Two"}])
    assert vf.count("drawtext=") == 2
    assert "between(t,0.00,60.00)" in vf and "between(t,60.00,100.00)" in vf


def test_now_playing_wraps_its_titles_over_repeats():
    spans, total = sequence.audio_spans([60.0, 40.0])
    repeated = sequence.repeat_spans(spans, 2, total)
    vf = overlays.now_playing(repeated, [{"title": "One"}, {"title": "Two"}])
    assert vf.count("One") == 2 and vf.count("Two") == 2


def test_a_huge_playlist_does_not_build_a_huge_filter_graph():
    spans, total = sequence.audio_spans([30.0])
    many = sequence.repeat_spans(spans, 400, total)
    vf = overlays.now_playing(many, [{"title": "x"}])
    assert vf.count("drawtext=") <= overlays.MAX_ENTRIES


def test_overlay_text_is_escaped():
    assert overlays.escape("a:b'c%d") == "a\\:b’c\\%d"


def test_build_returns_nothing_when_both_are_off():
    spans, total = sequence.audio_spans([60.0])
    assert overlays.build({}, spans, [{"title": "a"}], None, total, 1080) == ""


# --------------------------------------------------------------------------
# video backgrounds
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """A clip that deliberately does not loop: a bar sweeping across."""
    import subprocess

    from pulseforge.config import ffmpeg_caps

    path = tmp_path_factory.mktemp("clip") / "sweep.mp4"
    subprocess.run(
        [
            ffmpeg_caps()["ffmpeg"],
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=30:duration=5",
            "-vf",
            "drawbox=x='iw*t/5':y=0:w=20:h=ih:color=white@0.9:t=fill",
            "-c:v",
            "libx264",
            "-crf",
            "20",
            str(path),
        ],
        check=True,
    )
    return str(path)


def test_a_clip_is_recognised_as_video():
    assert videosource.is_video("a.MP4") and videosource.is_video("b.webm")
    assert not videosource.is_video("c.png")


def test_a_video_source_delivers_exactly_the_frames_asked_for(clip):
    src = videosource.VideoSource(clip, 96, 54, 30, 20, blend=0.0)
    frames = list(src.frames())
    assert len(frames) == 20
    assert frames[0].shape == (54, 96, 3)
    assert frames[0].max() > 5, "not a blank decode"


def test_a_short_clip_is_looped_rather_than_running_dry(clip):
    """Asking for more than the clip holds must still fill the bed."""
    src = videosource.VideoSource(clip, 64, 36, 30, 200, blend=0.0)
    frames = list(src.frames())
    assert len(frames) == 200
    assert frames[-1].max() > 5, "the tail should be picture, not padding"


def test_blending_the_ends_makes_the_wrap_less_of_a_jump(clip):
    """A cross-dissolve, not an identity -- so this measures the size of the
    step at the wrap against a normal frame step, rather than asserting zero."""

    def wrap_ratio(blend):
        frames = list(
            videosource.VideoSource(clip, 96, 54, 30, 60, blend=blend).frames()
        )
        step = np.mean(
            [np.abs(frames[i + 1] - frames[i]).mean() for i in range(25, 40)]
        )
        wrap = float(np.abs(frames[0] - frames[-1]).mean())
        return wrap / max(step, 1e-9)

    assert wrap_ratio(0.5) < wrap_ratio(0.0) * 0.8


def test_a_missing_clip_yields_blank_frames_rather_than_crashing(tmp_path):
    src = videosource.VideoSource(str(tmp_path / "nope.mp4"), 32, 18, 30, 5, blend=0.0)
    frames = list(src.frames())
    assert len(frames) == 5 and all(f.max() == 0 for f in frames)


# --------------------------------------------------------------------------
# the analogue look and card shots
# --------------------------------------------------------------------------
def _shot(tmp_path, **look):
    im = Image.new("RGB", (320, 180))
    for x in range(0, 320, 16):
        for y in range(180):
            for xx in range(x, min(320, x + 8)):
                im.putpixel((xx, y), (240, 240, 240))
    im.save(tmp_path / "stripes.png")
    return {
        "image": "stripes.png",
        "loop_seconds": 2.0,
        "layers": [],
        "emitters": [],
        "look": look,
    }


def _still(tmp_path, shot, t=0.0, width=200):
    from pulseforge.scenes import living
    from pulseforge.scenes.registry import SceneContext

    ctx = SceneContext(
        width,
        int(width * 0.5625) // 2 * 2,
        30,
        4,
        2.0,
        {},
        {"_shot": shot, "_base_dir": str(tmp_path), "_mask_dir": str(tmp_path)},
        [],
        None,
        str(tmp_path),
        fast=True,
    )
    return living.still(ctx, t)


OFF = {"grain": 0.0, "vignette": 0.0, "bloom": 0.0}


def test_letterbox_blacks_out_the_bars(tmp_path):
    out = _still(tmp_path, _shot(tmp_path, letterbox=0.1, **OFF))
    bar = int(0.1 * out.shape[0])
    assert out[:bar].max() == 0 and out[-bar:].max() == 0
    assert out[bar + 5 : -bar - 5].mean() > 5


def test_scanlines_darken_alternate_rows(tmp_path):
    plain = _still(tmp_path, _shot(tmp_path, **OFF)).astype(float)
    lined = _still(tmp_path, _shot(tmp_path, scanlines=1.0, **OFF)).astype(float)
    rows = lambda a: np.abs(np.diff(a.mean(axis=(1, 2))))[20:80].mean()
    assert rows(lined) > rows(plain) * 3


def test_fringing_bites_at_the_edges_not_the_centre(tmp_path):
    # rendered wide on purpose: the shift is a fraction of the frame width, so
    # at thumbnail sizes it is genuinely sub-pixel and does nothing
    plain = _still(tmp_path, _shot(tmp_path, **OFF), width=640).astype(int)
    fr = _still(tmp_path, _shot(tmp_path, fringing=1.0, **OFF), width=640).astype(int)
    d = np.abs(fr - plain).mean(axis=2)
    h, w = d.shape
    centre = d[h // 2 - 8 : h // 2 + 8, w // 2 - 12 : w // 2 + 12].mean()
    edges = np.concatenate([d[:, :20].ravel(), d[:, -20:].ravel()]).mean()
    assert edges > centre


def test_a_light_leak_brightens_one_side(tmp_path):
    plain = _still(tmp_path, _shot(tmp_path, **OFF)).astype(int)
    leaked = _still(tmp_path, _shot(tmp_path, leak=1.0, **OFF)).astype(int)
    assert leaked[:, :30].mean() > plain[:, :30].mean() + 5


def test_the_analogue_pack_does_not_break_the_loop(tmp_path):
    """Everything else in this app is loop-exact; the new grade has to be too."""
    from pulseforge.scenes import living
    from pulseforge.scenes.registry import SceneContext

    shot = _shot(
        tmp_path, scanlines=0.6, fringing=0.5, letterbox=0.06, leak=0.6, grain=0.05
    )
    n = int(shot["loop_seconds"] * 30)
    ctx = SceneContext(
        200,
        112,
        30,
        n + 1,
        shot["loop_seconds"],
        {},
        {"_shot": shot, "_base_dir": str(tmp_path), "_mask_dir": str(tmp_path)},
        [],
        None,
        str(tmp_path),
        fast=True,
    )
    frames = list(living.frames(ctx))
    assert np.abs(frames[0].astype(int) - frames[n].astype(int)).max() == 0


def test_a_card_shot_renders_without_an_image(tmp_path):
    shot = {
        "kind": "card",
        "image": "",
        "loop_seconds": 2.0,
        "card_title": "Late Night",
        "layers": [],
        "emitters": [],
        "look": {"grade_top": "#203050", "grade_bottom": "#050810"},
    }
    out = _still(tmp_path, shot)
    assert out.shape == (112, 200, 3) and out.mean() > 3


def test_card_titles_become_timed_filters():
    from pulseforge import render

    plan = [
        {
            "kind": "card",
            "card_title": "Hello",
            "card_subtitle": "world",
            "start": 0.0,
            "duration": 5.0,
        },
        {"kind": "scene", "start": 5.0, "duration": 60.0},
    ]
    vf = render._card_text(plan, 1080)
    assert vf.count("drawtext=") == 2
    assert "between(t,0.00,5.00)" in vf
    assert "Hello" in vf and "world" in vf


def test_a_card_with_no_text_produces_nothing():
    from pulseforge import render

    assert (
        render._card_text([{"kind": "card", "start": 0.0, "duration": 3.0}], 1080) == ""
    )
