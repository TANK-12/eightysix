"""
The fourth batch: Jan instead of an image generator, reflection and fog, film
grades, per-song levelling, fades, snapshots, project files and the pre-flight
check.

The Jan tests deliberately do **not** need Jan running. What matters is not that
a model replies -- it is that whatever it replies is checked against reality
before anything is applied, and that a missing server is a clear message rather
than a hang. Both are testable without a server, and both are where the bugs
would be.
"""

import json

import numpy as np
import pytest
from PIL import Image

from pulseforge import grades, jan, preflight, projectfile, sequence, snapshots

EFFECTS = ["water", "sway", "sky_clouds"]
EMITTERS = ["rain", "stars", "birds"]
PRESETS = ["lofi_lake", "night_sky"]


# --------------------------------------------------------------------------
# the local model
# --------------------------------------------------------------------------
def test_a_missing_server_is_a_clear_message_not_a_hang():
    st = jan.status()
    assert set(st) == {"running", "model", "detail"}
    if not st["running"]:
        assert "Jan" in st["detail"] or "model server" in st["detail"]


def test_json_is_found_inside_whatever_prose_comes_back():
    assert jan.extract_json('Sure! {"a": 1} hope that helps') == {"a": 1}
    assert jan.extract_json('```json\n{"b": 2}\n```') == {"b": 2}
    assert jan.extract_json('here you go:\n{\n  "c": [1,2]\n}\n') == {"c": [1, 2]}
    assert jan.extract_json("no json here") is None
    assert jan.extract_json("") is None


def test_a_broken_first_object_does_not_stop_it_finding_a_later_one():
    assert jan.extract_json('{not json} then {"ok": true}') == {"ok": True}


def test_invented_names_are_dropped_not_applied():
    """A small model will happily invent an effect. Nothing unchecked gets in."""
    out = jan.validate_look(
        {
            "preset": "cyberpunk_dream",
            "emitters": ["stars", "rainstorm", "birds"],
            "look": {"warmth": 0.4, "sparkle": 9},
        },
        EFFECTS,
        EMITTERS,
        PRESETS,
    )
    assert out["preset"] is None
    assert out["emitters"] == ["stars", "birds"]
    assert out["look"] == {"warmth": 0.4}
    assert any("cyberpunk_dream" in d for d in out["dropped"])
    assert any("rainstorm" in d for d in out["dropped"])
    assert any("sparkle" in d for d in out["dropped"])


def test_out_of_range_values_are_clamped_not_rejected():
    out = jan.validate_look(
        {"look": {"warmth": 40, "saturation": -3, "vignette": 0.5}},
        EFFECTS,
        EMITTERS,
        PRESETS,
    )
    assert out["look"] == {"warmth": 1.0, "saturation": 0.0, "vignette": 0.5}


def test_a_reply_that_is_not_json_at_all_says_so():
    out = jan.validate_look(
        {}, EFFECTS, EMITTERS, PRESETS, raw="I think fog would be nice"
    )
    assert out["preset"] is None and out["emitters"] == []
    assert any("not JSON" in d for d in out["dropped"])


def test_too_many_emitters_are_trimmed():
    out = jan.validate_look({"emitters": EMITTERS * 3}, EFFECTS, EMITTERS, PRESETS)
    assert len(out["emitters"]) <= 4


# --------------------------------------------------------------------------
# grades
# --------------------------------------------------------------------------
def test_every_grade_is_registered_with_a_description():
    listed = grades.grades_as_list()
    assert {g["id"] for g in listed} == set(grades.BY_ID)
    for g in listed:
        assert g["label"] and g["description"] and "fn" not in g


@pytest.mark.parametrize("gid", [g for g in grades.ids() if g != "none"])
def test_each_grade_changes_the_picture(gid):
    rng = np.random.default_rng(3)
    base = (rng.random((40, 60, 3)) * 200 + 20).astype(np.float32)
    out = grades.apply_grade(base.copy(), gid, 1.0)
    assert np.abs(out - base).mean() > 2.0
    assert out.min() >= 0.0 and out.max() <= 255.0


def test_grades_are_distinguishable_from_each_other():
    rng = np.random.default_rng(5)
    base = (rng.random((30, 40, 3)) * 200 + 20).astype(np.float32)
    means = {}
    for gid in grades.ids():
        out = grades.apply_grade(base.copy(), gid, 1.0)
        means[gid] = tuple(np.round(out.reshape(-1, 3).mean(axis=0), 1))
    assert len(set(means.values())) == len(means), f"two grades are identical: {means}"


def test_zero_strength_and_none_leave_the_frame_alone():
    base = np.full((8, 8, 3), 120.0, dtype=np.float32)
    assert np.array_equal(grades.apply_grade(base.copy(), "faded", 0.0), base)
    assert np.array_equal(grades.apply_grade(base.copy(), "none", 1.0), base)
    assert np.array_equal(grades.apply_grade(base.copy(), "nonsense", 1.0), base)


def test_strength_blends_continuously():
    base = np.full((8, 8, 3), 100.0, dtype=np.float32)
    half = grades.apply_grade(base.copy(), "sepia", 0.5)
    full = grades.apply_grade(base.copy(), "sepia", 1.0)
    assert np.abs(half - base).mean() == pytest.approx(
        np.abs(full - base).mean() * 0.5, rel=0.02
    )


def test_a_grade_does_not_break_the_loop_seam(tmp_path):
    from pulseforge.scenes import living
    from pulseforge.scenes.registry import SceneContext

    Image.new("RGB", (160, 90), (90, 120, 170)).save(tmp_path / "bg.png")
    shot = {
        "image": "bg.png",
        "loop_seconds": 1.0,
        "layers": [],
        "emitters": [],
        "look": {"grade": "teal_orange", "grade_amount": 0.8, "grain": 0.05},
    }
    n = 30
    ctx = SceneContext(
        120,
        68,
        30,
        n + 1,
        1.0,
        {},
        {"_shot": shot, "_base_dir": str(tmp_path), "_mask_dir": str(tmp_path)},
        [],
        None,
        str(tmp_path),
        fast=True,
    )
    frames = list(living.frames(ctx))
    assert np.abs(frames[0].astype(int) - frames[n].astype(int)).max() == 0


# --------------------------------------------------------------------------
# levelling and fades
# --------------------------------------------------------------------------
def test_gains_level_the_playlist_against_itself(monkeypatch):
    """Relative, not absolute: an evenly quiet playlist needs no correction."""
    fake = {"a": -30.0, "b": -30.0, "c": -30.0}
    monkeypatch.setattr(sequence, "measure_loudness", lambda p: fake[p])
    assert sequence.auto_gains(["a", "b", "c"]) == [0.0, 0.0, 0.0]


def test_an_uneven_playlist_is_pulled_together(monkeypatch):
    fake = {"loud": -12.0, "mid": -20.0, "quiet": -28.0}
    monkeypatch.setattr(sequence, "measure_loudness", lambda p: fake[p])
    gains = sequence.auto_gains(["loud", "mid", "quiet"])
    after = [fake[k] + g for k, g in zip(["loud", "mid", "quiet"], gains)]
    assert max(after) - min(after) < 0.01
    assert gains[0] < 0 < gains[2], "the loud one comes down, the quiet one goes up"


def test_corrections_are_capped(monkeypatch):
    fake = {"a": -10.0, "b": -90.0}
    monkeypatch.setattr(sequence, "measure_loudness", lambda p: fake[p])
    assert all(abs(g) <= 18.0 for g in sequence.auto_gains(["a", "b"]))


def test_unmeasurable_songs_get_no_gain(monkeypatch):
    monkeypatch.setattr(sequence, "measure_loudness", lambda p: None)
    assert sequence.auto_gains(["a", "b"]) == [0.0, 0.0]


def test_fade_filters_are_built_only_when_they_fit():
    from pulseforge.render import _fade_filters

    assert _fade_filters(0, 0, 100) == []
    both = _fade_filters(2.0, 3.0, 100.0)
    assert both[0].startswith("fade=t=in") and "st=97.000" in both[1]
    assert (
        _fade_filters(0, 500.0, 100.0) == []
    ), "a fade longer than the video is skipped"
    assert _fade_filters(2.0, 0, 100.0, audio=True)[0].startswith("afade=")


# --------------------------------------------------------------------------
# snapshots
# --------------------------------------------------------------------------
@pytest.fixture
def a_project(tmp_path, monkeypatch):
    from pulseforge import config
    from pulseforge import project as projmod

    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(projmod, "PROJECTS_DIR", tmp_path / "projects")
    p = projmod.create("test project")
    Image.fromarray(np.full((16, 16), 255, np.uint8)).save(p.masks_dir() / "m.png")
    p.data["shots"] = [
        {
            "image": "bg.png",
            "layers": [
                {
                    "name": "sky",
                    "effect": "sky_clouds",
                    "params": {},
                    "region": {"kind": "brush", "brush": "m.png"},
                }
            ],
            "emitters": [],
        }
    ]
    p.data["playlist"] = []
    p.save()
    return p


def test_a_snapshot_comes_back_exactly(a_project):
    sid = snapshots.take(a_project, "before I ruin it")
    a_project.data["shots"] = []
    a_project.save()
    restored = snapshots.restore(a_project, sid)
    assert len(restored) == 1 and restored[0]["layers"][0]["name"] == "sky"


def test_a_snapshot_keeps_its_own_copy_of_the_masks(a_project):
    """A snapshot that pointed at live masks would change under you."""
    sid = snapshots.take(a_project, "clean")
    Image.fromarray(np.zeros((16, 16), np.uint8)).save(a_project.masks_dir() / "m.png")
    snapshots.restore(a_project, sid)
    back = np.asarray(Image.open(a_project.masks_dir() / "m.png"))
    assert back.mean() > 200, "the painted region should have come back too"


def test_snapshots_are_listed_newest_first(a_project):
    import time

    snapshots.take(a_project, "one")
    time.sleep(1.05)  # the id carries a whole-second timestamp
    snapshots.take(a_project, "two")
    listed = snapshots.listing(a_project)
    assert [s["label"] for s in listed][:2] == ["two", "one"]


def test_deleting_and_restoring_something_gone(a_project):
    sid = snapshots.take(a_project, "temp")
    assert snapshots.delete(a_project, sid) is True
    assert snapshots.delete(a_project, sid) is False
    with pytest.raises(KeyError):
        snapshots.restore(a_project, sid)


# --------------------------------------------------------------------------
# a project as a file
# --------------------------------------------------------------------------
def test_a_project_survives_a_round_trip(a_project, tmp_path, monkeypatch):
    from pulseforge import project as projmod

    a_project.data["target_seconds"] = 3600.0
    a_project.save()
    out = tmp_path / "p.pfproj"
    path, size = projectfile.export(a_project, out)
    assert size > 0

    info = projectfile.inspect(path)
    assert info["shots"] == 1 and info["includes_media"] is False

    fresh = projmod.create("landing spot")
    projectfile.restore(path, fresh)
    assert fresh.data["target_seconds"] == 3600.0
    assert fresh.data["shots"][0]["layers"][0]["name"] == "sky"
    assert (fresh.masks_dir() / "m.png").exists(), "masks travel with the project"
    assert fresh.data["name"] == "landing spot", "the destination keeps its own name"


def test_media_is_left_out_unless_asked_for(a_project, tmp_path):
    (a_project.assets_dir() / "big.png").write_bytes(b"\x89PNG" + b"0" * 5000)
    small, small_size = projectfile.export(a_project, tmp_path / "s.pfproj")
    big, big_size = projectfile.export(
        a_project, tmp_path / "b.pfproj", include_media=True
    )
    assert big_size > small_size


def test_a_file_that_is_not_a_project_is_refused(tmp_path):
    import zipfile

    bad = tmp_path / "not.pfproj"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("hello.txt", "nope")
    with pytest.raises(ValueError):
        projectfile.inspect(bad)


def test_paths_that_try_to_escape_are_skipped(a_project, tmp_path):
    import zipfile

    evil = tmp_path / "evil.pfproj"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr(projectfile.MANIFEST, json.dumps({"format": 1, "data": {}}))
        z.writestr("../escaped.txt", "should not be written")
    projectfile.restore(evil, a_project)
    assert not (tmp_path / "escaped.txt").exists()


# --------------------------------------------------------------------------
# pre-flight
# --------------------------------------------------------------------------
def test_no_songs_is_reported_as_a_problem(a_project):
    items = preflight.check_project(a_project)
    assert items[0]["level"] == "stop" and "No songs" in items[0]["title"]


def test_a_missing_render_is_reported(tmp_path):
    items = preflight.check_render(str(tmp_path / "nope.mp4"))
    assert items[0]["level"] == "stop"


def test_the_summary_counts_each_level():
    counts = preflight.summarise(
        [{"level": "stop"}, {"level": "check"}, {"level": "check"}, {"level": "fine"}]
    )
    assert counts == {"stop": 1, "check": 2, "fine": 1}


def test_shots_without_a_background_are_flagged(a_project, monkeypatch):
    monkeypatch.setattr(
        type(a_project), "playlist_paths", lambda self: ["/tmp/fake.mp3"]
    )
    a_project.data["shots"] = [{"image": "", "kind": "scene"}]
    items = preflight.check_project(a_project)
    titles = [i["title"] for i in items]
    assert "Shots with no background" in titles


# --------------------------------------------------------------------------
# the timeline the assembly actually builds
# --------------------------------------------------------------------------
def _assembled_offsets(plan):
    """The xfade offsets `_assemble_living` would use, without rendering."""
    import pulseforge.render as render_mod

    captured = {}

    class FakeJob:
        def __init__(self, cmd, **kw):
            captured["cmd"] = cmd

        def run(self, **kw):
            return 0

    real = render_mod.FFJob
    render_mod.FFJob = FakeJob
    try:
        for k, shot in enumerate(plan):
            shot.setdefault("_bed", f"bed{k}.mp4")
            shot.setdefault("_live", False)
        render_mod._assemble_living(
            plan,
            {"w": 1920, "h": 1080, "fps": 30},
            "audio.flac",
            plan[-1]["start"] + plan[-1]["duration"],
            "out.mp4",
            {"crf": 18},
            "",
            lambda s: None,
            lambda f: None,
        )
    finally:
        render_mod.FFJob = real
    fc = captured["cmd"][captured["cmd"].index("-filter_complex") + 1]
    import re

    return [float(x) for x in re.findall(r"xfade=[^;\[]*?offset=([\d.]+)", fc)]


def test_transitions_sit_where_the_shots_actually_start():
    """Offsets that accumulate `duration - transition` overlap the shots, so the
    video comes out shorter than the audio by every transition added together --
    the picture froze on the last shot while the music kept playing, and a
    fade-out timed off the end never fired."""
    plan = [
        {
            "index": 0,
            "start": 0.0,
            "duration": 4.0,
            "transition": "cut",
            "transition_s": 0.0,
        },
        {
            "index": 1,
            "start": 4.0,
            "duration": 6.0,
            "transition": "dissolve",
            "transition_s": 1.5,
        },
        {
            "index": 2,
            "start": 10.0,
            "duration": 5.0,
            "transition": "dissolve",
            "transition_s": 1.0,
        },
    ]
    assert _assembled_offsets(plan) == [4.0, 10.0]


def test_the_video_reaches_the_end_of_the_audio():
    plan = [
        {
            "index": 0,
            "start": 0.0,
            "duration": 30.0,
            "transition": "cut",
            "transition_s": 0.0,
        },
        {
            "index": 1,
            "start": 30.0,
            "duration": 30.0,
            "transition": "dissolve",
            "transition_s": 2.0,
        },
    ]
    offsets = _assembled_offsets(plan)
    ends_at = offsets[-1] + plan[-1]["duration"]
    audio_length = plan[-1]["start"] + plan[-1]["duration"]
    assert ends_at == pytest.approx(
        audio_length
    ), "the picture must last as long as the music"


# --------------------------------------------------------------------------
# one look across every shot -- what the simple editor is built around
# --------------------------------------------------------------------------
def test_a_look_applied_to_all_keeps_each_shot_its_own_picture(a_project):
    """Applying a preset to everything must not flatten the pictures into one."""
    from pulseforge import presets as presets_mod

    a_project.data["shots"] = [
        {"image": "lake.png", "layers": [], "emitters": [], "look": {}},
        {"image": "street.png", "layers": [], "emitters": [], "look": {}},
    ]
    out = [presets_mod.apply_to("lofi_lake", s) for s in a_project.data["shots"]]
    assert [s["image"] for s in out] == ["lake.png", "street.png"]
    assert all(s["preset"] == "lofi_lake" for s in out)
    assert all(s["look"]["warmth"] > 0 for s in out)


def test_a_grade_can_be_set_without_disturbing_the_rest_of_the_look():
    from pulseforge import presets as presets_mod

    shot = presets_mod.apply_to("night_sky", {"image": "a.png"})
    before = dict(shot["look"])
    shot["look"] = {**shot["look"], "grade": "faded", "grade_amount": 0.7}
    assert shot["look"]["grade"] == "faded"
    for key, value in before.items():
        assert shot["look"][key] == value, f"{key} was disturbed"
