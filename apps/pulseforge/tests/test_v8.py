"""
v8 -- the AMV studio: music structure, clip analysis, editing styles, beat
effects and the planner.

The tests that matter here are the ones about *timing*, because timing is the
whole product. A cut half a frame off the beat is not a cosmetic problem, and
neither is a video that ends before its music does -- both shipped in earlier
passes and both are asserted against now.

The synthetic song is built with a known tempo, meter and section layout, so the
analysis can be checked against ground truth rather than against itself.
"""

import os
import subprocess
import wave

import numpy as np
import pytest

from pulseforge import (
    amvplan,
    analyze,
    beatfx,
    editstyles,
    musicmap,
    palette,
    shotdna,
)
from pulseforge.scenes import registry as scene_registry

# ---- ground truth for the synthetic song ---------------------------------
BPM = 128.0
BEAT = 60.0 / BPM
BAR = BEAT * 4
PLAN = [
    ("intro", 8, 0.25, 0.0),
    ("verse", 8, 0.55, 0.35),
    ("chorus", 8, 1.0, 1.0),
    ("verse", 8, 0.55, 0.35),
    ("chorus", 8, 1.0, 1.0),
    ("outro", 4, 0.2, 0.0),
]
SR = 44100


def _write_song(path):
    def env(n, a=0.002, d=0.12):
        t = np.arange(n) / SR
        return np.minimum(t / a, 1.0) * np.exp(-t / d)

    def kick(n):
        t = np.arange(n) / SR
        f = 120 * np.exp(-t / 0.03) + 45
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, 0.10)

    def snare(n):
        return np.random.default_rng(3).standard_normal(n) * env(n, 0.001, 0.07) * 0.7

    def hat(n):
        x = np.random.default_rng(9).standard_normal(n) * env(n, 0.0005, 0.02)
        return np.diff(np.concatenate([[0.0], x])) * 3.0

    total_bars = sum(p[1] for p in PLAN)
    dur = total_bars * BAR
    out = np.zeros(int(dur * SR) + SR)
    bar_i = 0
    for name, bars, level, bright in PLAN:
        for b in range(bars):
            t0 = (bar_i + b) * BAR
            for beat in range(4):
                tb = t0 + beat * BEAT
                i = int(tb * SR)
                k = kick(int(0.25 * SR))
                out[i : i + len(k)] += k * level * (1.25 if beat == 0 else 1.0)
                if beat in (1, 3):
                    sn = snare(int(0.2 * SR))
                    out[i : i + len(sn)] += sn * level * 0.8
                if bright > 0:
                    for half in (0, 1):
                        j = int((tb + half * BEAT / 2) * SR)
                        h = hat(int(0.05 * SR))
                        out[j : j + len(h)] += h * level * bright * 0.5
            n = int(BAR * SR)
            t = np.arange(n) / SR
            base = 220.0 if name in ("verse", "intro") else 330.0
            pad = sum(np.sin(2 * np.pi * base * hh * t) / (hh + 1) for hh in (1, 2, 3))
            i0 = int(t0 * SR)
            out[i0 : i0 + n] += pad[: len(out) - i0] * level * 0.22
        bar_i += bars
    out = out[: int(dur * SR)]
    out = out / (np.abs(out).max() + 1e-9) * 0.85
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((out * 32767).astype(np.int16).tobytes())
    return dur


def _write_clip(path, kind, secs=6, w=320, h=180, fps=24):
    """A short clip with a deliberately known character."""
    rng = np.random.default_rng(7)
    frames = []
    yy, xx = np.mgrid[0:h, 0:w]
    if kind == "pan":
        tex = rng.random((h, w * 3)).astype(np.float32) * 255
        tex = np.repeat(np.repeat(tex[::4, ::4], 4, 0), 4, 1)[:h, : w * 3]
        for i in range(fps * secs):
            off = int(i * 3)
            frames.append(np.stack([tex[:, off : off + w]] * 3, axis=2))
    elif kind == "close":
        d = ((xx - w / 2) / (w * 0.22)) ** 2 + ((yy - h / 2) / (h * 0.42)) ** 2
        m = np.clip(1.4 - d, 0, 1)
        f = np.zeros((h, w, 3), np.float32) + np.array([30, 28, 42])
        f[..., 0] += m * 200
        f[..., 1] += m * 150
        f[..., 2] += m * 120
        frames = [f] * (fps * secs)
    elif kind == "letterbox":
        base = rng.random((h, w)).astype(np.float32) * 255
        f = np.zeros((h, w, 3), np.float32)
        band = slice(int(h * 0.125), int(h * 0.875))
        f[band] = np.stack([base[band]] * 3, axis=2)
        frames = [f] * (fps * secs)
    else:  # "wide": fine detail everywhere, cool, still
        base = rng.random((h, w)).astype(np.float32) * 255
        f = np.stack([base * 0.5, base * 0.7, base], axis=2)
        frames = [np.clip(f, 0, 255)] * (fps * secs)

    pr = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{w}x{h}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        stdin=subprocess.PIPE,
    )
    for f in frames:
        pr.stdin.write(np.clip(f, 0, 255).astype(np.uint8).tobytes())
    pr.stdin.close()
    pr.wait()
    return path


@pytest.fixture(scope="module")
def song(tmp_path_factory):
    d = tmp_path_factory.mktemp("v8song")
    p = d / "song.wav"
    dur = _write_song(p)
    feat = analyze.analyze(str(p), 30.0)
    return {
        "path": str(p),
        "duration": dur,
        "feat": feat,
        "map": musicmap.map_music(feat),
    }


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("v8clips")
    out = {}
    for kind, name in (
        ("pan", "pan"),
        ("close", "close"),
        ("wide", "wide"),
        ("letterbox", "bars"),
    ):
        p = d / f"{name}.mp4"
        _write_clip(p, kind)
        out[str(p)] = shotdna.analyse_clip(str(p), use_cache=False)
    return {"dir": str(d), "dna": out}


# --------------------------------------------------------------------------
# musicmap
# --------------------------------------------------------------------------
def test_tempo_is_found_within_one_percent(song):
    assert abs(song["map"]["bpm"] - BPM) / BPM < 0.01


def test_meter_is_four_four(song):
    assert song["map"]["beats_per_bar"] == 4


def test_downbeats_land_on_the_real_bar_lines(song):
    db = np.array(song["map"]["downbeats"])
    assert len(db) > 20
    # distance to the nearest true bar line, which fall every BAR seconds from 0
    off = np.abs(((db + BAR / 2) % BAR) - BAR / 2)
    assert off.mean() < 0.08, f"mean downbeat error {off.mean():.3f}s"


def test_every_section_boundary_is_found(song):
    truth = [0.0, 15.0, 30.0, 45.0, 60.0, 75.0]
    found = [s["start"] for s in song["map"]["sections"]]
    assert len(found) == len(truth), f"expected {len(truth)} sections, got {found}"
    for t, f in zip(truth, found):
        assert abs(t - f) < 0.6, f"boundary {t} came out at {f}"


def test_the_loud_repeating_sections_are_called_choruses(song):
    kinds = [s["kind"] for s in song["map"]["sections"]]
    assert kinds[0] == "intro"
    assert kinds[-1] == "outro"
    assert kinds[2] == "chorus" and kinds[4] == "chorus"


def test_drops_land_where_the_choruses_start(song):
    drops = song["map"]["drops"]
    assert len(drops) >= 2
    for want in (30.0, 60.0):
        assert min(abs(d - want) for d in drops) < 1.0


def test_a_song_too_short_to_have_a_structure_degrades_rather_than_raises():
    feat = {
        "fps": 30.0,
        "onset": np.zeros(10),
        "energy": np.zeros(10),
        "sub": np.zeros(10),
        "bands": np.zeros((10, 12)),
        "duration": 0.33,
    }
    m = musicmap.map_music(feat)
    assert m["ok"] is False
    assert m["beats"] == []
    assert len(m["sections"]) == 1


def test_the_beat_grid_keeps_going_through_a_quiet_stretch(song):
    """The point of the dynamic-programming tracker over peak-picking."""
    beats = np.array(song["map"]["beats"])
    gaps = np.diff(beats)
    assert gaps.max() < BEAT * 1.6, "the grid dropped out somewhere"
    assert abs(np.median(gaps) - BEAT) < 0.02


# --------------------------------------------------------------------------
# shotdna
# --------------------------------------------------------------------------
def test_a_panning_clip_reports_the_direction_it_pans(clips):
    path = [p for p in clips["dna"] if "pan" in p][0]
    st = shotdna.window_stats(clips["dna"][path], 1.0, 3.0)
    assert st["flow_dx"] < -0.05, "a leftward pan should have a negative dx"
    assert "panning left" in shotdna.describe(st)


def test_a_close_up_is_not_filed_as_a_wide_shot(clips):
    path = [p for p in clips["dna"] if "close" in p][0]
    st = shotdna.window_stats(clips["dna"][path], 1.0, 3.0)
    assert st["shot_scale"] == "close"


def test_a_detailed_still_is_a_wide_shot(clips):
    path = [p for p in clips["dna"] if "wide" in p][0]
    st = shotdna.window_stats(clips["dna"][path], 1.0, 3.0)
    assert st["shot_scale"] == "wide"


def test_letterbox_bars_are_measured(clips):
    path = [p for p in clips["dna"] if "bars" in p][0]
    lb = clips["dna"][path]["letterbox"]
    assert abs(lb["top"] - 0.125) < 0.03
    assert abs(lb["bottom"] - 0.125) < 0.03


def test_warmth_has_the_right_sign(clips):
    close = [p for p in clips["dna"] if "close" in p][0]
    wide = [p for p in clips["dna"] if "wide" in p][0]
    assert shotdna.window_stats(clips["dna"][close], 1.0, 3.0)["warmth"] > 0
    assert shotdna.window_stats(clips["dna"][wide], 1.0, 3.0)["warmth"] < 0


# --------------------------------------------------------------------------
# beat effects
# --------------------------------------------------------------------------
def test_every_beat_effect_builds_a_filter():
    ctx = {"w": 640, "h": 360, "fps": 30, "dur": 2.0}
    for fid in beatfx.FX:
        assert beatfx.build(fid, [0.0, 1.0], None, ctx), f"{fid} built nothing"


def test_an_unknown_effect_costs_that_effect_and_not_the_render():
    ctx = {"w": 640, "h": 360, "fps": 30, "dur": 2.0}
    assert beatfx.build("no_such_effect", [0.0], None, ctx) == ""


def test_effect_parameters_are_clamped_to_their_own_range():
    p = beatfx.merge_params("zoom_punch", {"amount": 99.0})
    spec = [x for x in beatfx.FX["zoom_punch"]["params"] if x["key"] == "amount"][0]
    assert p["amount"] == spec["max"]


def test_every_effect_declares_a_schema_whose_defaults_are_in_range():
    for fid, meta in beatfx.FX.items():
        assert meta.get("description"), f"{fid} has no description"
        assert meta.get("family") in ("camera", "colour", "glitch"), fid
        for spec in meta["params"]:
            if spec["type"] in ("float", "int"):
                assert (
                    spec["min"] <= spec["default"] <= spec["max"]
                ), f"{fid}.{spec['key']}"


def test_two_close_events_give_one_pulse_not_a_double_height_one():
    """`max` rather than a sum: a doubled zoom leaves the frame."""
    expr = beatfx.pulse([0.0, 0.01], decay=8.0)
    assert expr.startswith("max(") and "+" not in expr


# --------------------------------------------------------------------------
# editing styles
# --------------------------------------------------------------------------
def test_every_style_is_complete_and_names_real_effects_and_transitions():
    for sid, st in editstyles.STYLES.items():
        assert st.get("description"), f"{sid} has no description"
        assert st.get("pace"), f"{sid} has no pace"
        for f in st.get("fx") or []:
            assert f["id"] in beatfx.FX, f"{sid} uses unknown effect {f['id']}"
            assert f.get("on") in (
                "beat",
                "downbeat",
                "bar2",
                "hit",
                "drop",
                "shot_start",
                "section_start",
                "none",
            ), f"{sid}.{f['id']} has an unknown trigger {f.get('on')}"
        tr = st.get("transition") or {}
        for key in ("default", "on_section", "on_drop"):
            name = tr.get(key)
            if name and name != "whip":
                assert name in editstyles.TRANSITIONS, f"{sid}.{key} = {name}"


def test_every_transition_names_a_real_xfade_or_is_a_cut():
    for tid, t in editstyles.TRANSITIONS.items():
        assert t["xfade"] or tid == "cut", f"{tid} has no xfade and is not a cut"


# --------------------------------------------------------------------------
# the planner
# --------------------------------------------------------------------------
def test_every_cut_lands_on_the_beat_grid(song, clips):
    beats = np.array(song["map"]["beats"])
    for sid in editstyles.STYLES:
        plan = amvplan.plan(
            song["map"], clips["dna"], editstyles.get_style(sid), song["duration"]
        )
        assert plan["shots"], sid
        for sh in plan["shots"][1:]:
            off = np.abs(beats - sh["at"]).min()
            assert (
                off < 0.02
            ), f"{sid}: a cut at {sh['at']}s is {off * 1000:.0f}ms off the beat"


def test_the_chorus_is_cut_faster_than_the_verse(song, clips):
    plan = amvplan.plan(
        song["map"], clips["dna"], editstyles.get_style("classic"), song["duration"]
    )
    by = {}
    for sh in plan["shots"]:
        by.setdefault(sh["section"], []).append(sh["dur"])
    assert np.mean(by["chorus"]) < np.mean(by["verse"])


def test_no_style_repeats_the_same_clip_back_to_back(song, clips):
    for sid in editstyles.STYLES:
        plan = amvplan.plan(
            song["map"], clips["dna"], editstyles.get_style(sid), song["duration"]
        )
        assert plan["summary"]["repeats_back_to_back"] == 0, sid


def test_turning_the_intensity_up_shortens_every_shot(song, clips):
    style = editstyles.get_style("classic")
    calm = amvplan.plan(
        song["map"], clips["dna"], style, song["duration"], {"intensity": 0.5}
    )
    busy = amvplan.plan(
        song["map"], clips["dna"], style, song["duration"], {"intensity": 2.0}
    )
    assert busy["summary"]["shots"] > calm["summary"]["shots"] * 2


def test_the_shots_tile_the_whole_song_with_no_gaps_or_overlaps(song, clips):
    plan = amvplan.plan(
        song["map"], clips["dna"], editstyles.get_style("hype"), song["duration"]
    )
    shots = plan["shots"]
    assert abs(shots[0]["at"]) < 1e-6
    # `at` and `dur` are stored rounded to a millisecond, so the sum of two of
    # them can legitimately disagree with the next start by one. Anything
    # larger would be a real gap or overlap in the timeline.
    for a, b in zip(shots, shots[1:]):
        assert abs((a["at"] + a["dur"]) - b["at"]) <= 1.5e-3
    last = shots[-1]
    assert abs((last["at"] + last["dur"]) - song["duration"]) < 1e-2


def test_a_slot_longer_than_the_footage_is_reported_not_hidden(song, clips):
    """The bug that made a 28-shot edit render six seconds long."""
    plan = amvplan.plan(
        song["map"], clips["dna"], editstyles.get_style("emotional"), song["duration"]
    )
    s = plan["summary"]
    assert "shots_short_of_footage" in s
    # the clips are 6s and this style asks for shots up to 11s, so some must be
    assert s["shots_short_of_footage"] >= 1
    assert all("short_by" in sh for sh in plan["shots"])


def test_an_empty_clip_folder_gives_an_empty_plan_rather_than_an_exception(song):
    plan = amvplan.plan(
        song["map"], {}, editstyles.get_style("classic"), song["duration"]
    )
    assert plan["shots"] == []


def test_the_assignment_is_solved_globally(song, clips):
    plan = amvplan.plan(
        song["map"], clips["dna"], editstyles.get_style("classic"), song["duration"]
    )
    assert plan["summary"]["solver"] == "hungarian"


def test_effects_only_fire_in_the_sections_their_style_names(song, clips):
    style = editstyles.get_style("classic")  # zoom_punch in chorus and build only
    plan = amvplan.plan(song["map"], clips["dna"], style, song["duration"])
    for sh in plan["shots"]:
        if any(f["id"] == "zoom_punch" for f in sh["fx"]):
            assert sh["section"] in ("chorus", "build"), sh["section"]


# --------------------------------------------------------------------------
# the scene, and the look taken from a picture
# --------------------------------------------------------------------------
def test_the_amv_scene_is_registered_and_is_an_edl_scene():
    assert "amv" in scene_registry.SCENES
    assert scene_registry.SCENES["amv"]["family"] == "amv"
    assert (
        "montage" in scene_registry.SCENES
    ), "the older montage scene must not be lost"


def test_the_amv_scene_offers_every_style():
    spec = [p for p in scene_registry.SCENES["amv"]["params"] if p["key"] == "style"][0]
    assert set(spec["options"]) == set(editstyles.STYLES)


@pytest.mark.parametrize(
    "maker,expect",
    [
        ("night", "night"),
        ("golden", "golden hour"),
        ("overcast", "overcast"),
    ],
)
def test_a_picture_is_read_for_the_look_it_wants(tmp_path, maker, expect):
    from PIL import Image

    h, w = 240, 400
    yy, xx = np.mgrid[0:h, 0:w]
    a = np.zeros((h, w, 3), np.float32)
    if maker == "night":
        a[..., 2] = 40 - 20 * (yy / h)
        a[..., 0] = 10
        a[..., 1] = 14
        d = np.hypot(xx - 320, yy - 200)
        a += (np.clip(1 - d / 40, 0, 1) ** 2)[..., None] * np.array([255, 200, 120])
    elif maker == "golden":
        a[..., 0] = 210 - 60 * (yy / h)
        a[..., 1] = 150 - 70 * (yy / h)
        a[..., 2] = 90 - 50 * (yy / h)
    else:
        a += np.array([168, 172, 176])
    p = tmp_path / f"{maker}.png"
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(p)
    look = palette.look_from_image(str(p))
    assert look["mood"] == expect
    for key in ("vignette", "grain", "bloom", "saturation", "warmth", "grade"):
        assert key in look["params"]
    assert look["why"]


def test_the_look_only_adds_a_light_leak_when_the_light_has_a_direction(tmp_path):
    from PIL import Image

    flat = np.zeros((200, 300, 3), np.float32) + np.array([190, 150, 110])
    p = tmp_path / "flat.png"
    Image.fromarray(flat.astype(np.uint8)).save(p)
    look = palette.look_from_image(str(p))
    assert look["light"]["where"] == "flat"
    assert look["params"]["leak"] < 0.12


def test_every_look_parameter_is_one_the_living_scene_understands():
    from pulseforge.scenes.living import SCENE

    known = {p["key"] for p in SCENE["params"]}
    for mood in palette.MOODS:
        assert mood  # the table is keyed by mood name
    sample = {
        "grade",
        "grade_amount",
        "vignette",
        "grain",
        "bloom",
        "saturation",
        "warmth",
        "haze",
        "haze_color",
        "push",
        "drift",
        "leak",
        "leak_color",
        "sky_clouds",
    }
    assert sample <= known, sample - known


def test_a_generated_look_is_written_where_the_renderer_reads_it():
    """The bug this guards: `auto-look` wrote the whole look into
    `shot["params"]`, which nothing reads, so applying a look changed the saved
    project and not one pixel of the render."""
    from pulseforge.scenes.living import _camera, _look

    look_keys, camera_keys, extra = palette.split_for_shot(
        {k: 1 for k in palette.LOOK_KEYS}
        | {k: 1 for k in palette.CAMERA_KEYS}
        | {"sky_clouds": 0.3}
    )
    assert set(look_keys) == set(palette.LOOK_KEYS)
    assert set(camera_keys) == set(palette.CAMERA_KEYS)
    assert extra == {"sky_clouds": 0.3}, "a scene parameter must not be dropped"

    # and every one of those keys must survive into what the renderer builds
    class Ctx:
        def p(self, key, default=None):
            return None

    shot = {"look": dict(look_keys), "camera": dict(camera_keys)}
    built = _look(Ctx(), shot)
    for k in ("vignette", "grain", "bloom", "saturation", "warmth", "haze"):
        assert built[k] == 1, f"{k} did not reach the renderer"
    cam = _camera(Ctx(), shot, live=False)
    assert cam is not None


def test_every_key_a_look_produces_lands_somewhere_real():
    """No parameter `palette.py` invents may fall between the three homes."""
    from pulseforge.scenes.living import SCENE

    known = {p["key"] for p in SCENE["params"]}
    for mood in palette.MOODS:
        sample = dict(palette.MOODS[mood])
        for junk in ("why", "effects", "emitters"):
            sample.pop(junk, None)
        sample["haze_color"] = "#ffffff"
        sample["leak_color"] = "#ffffff"
        look_p, cam_p, extra = palette.split_for_shot(sample)
        assert set(look_p) | set(cam_p) | set(extra) == set(sample)
        for k in extra:
            assert k in known, f"{mood} produced {k}, which no scene understands"
