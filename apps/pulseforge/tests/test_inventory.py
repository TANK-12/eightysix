"""
Nothing gets lost.

Features here are added in batches, and a rename or a refactor is exactly how a
working scene or format quietly disappears. So the full inventory is asserted:
if something that used to exist stops being registered, this fails, rather than
being noticed months later when someone opens an old project.

Adding to these lists is expected. Removing from them should take a deliberate
decision, not a passing edit.
"""

import pytest

from pulseforge import ambience, beatfx, editstyles, formats, grades, presets, sequence
from pulseforge.emitters import emitters_as_list
from pulseforge.motion import effects_as_list
from pulseforge.scenes import scenes_as_list

# Every scene that has ever shipped. `living` is the flagship; the rest predate
# it and still have to work.
SCENES = {"bars", "drift", "swarm", "aurora", "montage", "living", "amv"}
FORMATS = {"long_1080p", "uhd_2160p", "shorts_1080x1920", "loop_1080p"}
EFFECTS = {
    "water",
    "sway",
    "flow",
    "sky_clouds",
    "shimmer",
    "glow_pulse",
    "flicker",
    "breathe",
    "frames",
    "rays",
    "glass_rain",
}
EMITTERS = {
    "particles",
    "rain",
    "snow",
    "dust",
    "fireflies",
    "bubbles",
    "stars",
    "leaves",
    "birds",
    "fish",
    "sprites",
}
PRESETS = {
    "lofi_lake",
    "rainy_window",
    "night_sky",
    "forest",
    "snowfall",
    "autumn",
    "sakura",
    "underwater",
    "city_night",
    "sunset",
    "minimal",
}
TRANSITIONS = {
    "cut",
    "dissolve",
    "fade_black",
    "fade_white",
    "wipe_left",
    "wipe_right",
    "slide_left",
    "slide_up",
    "circle",
    "smooth",
    "pixelize",
}
AMBIENCE = {"rain", "fire", "vinyl", "wind", "waves"}
GRADES = {
    "none",
    "faded",
    "teal_orange",
    "kodak",
    "bleach",
    "night",
    "sepia",
    "vhs",
    "dream",
}


def _ids(rows):
    return {r["id"] for r in rows}


@pytest.mark.parametrize(
    "name,expected,actual",
    [
        ("scene", SCENES, None),
        ("format", FORMATS, None),
        ("effect", EFFECTS, None),
        ("emitter", EMITTERS, None),
        ("preset", PRESETS, None),
        ("transition", TRANSITIONS, None),
        ("ambience bed", AMBIENCE, None),
        ("grade", GRADES, None),
    ],
)
def test_nothing_has_been_dropped(name, expected, actual):
    live = {
        "scene": _ids(scenes_as_list()),
        "format": _ids(formats.as_list()),
        "effect": _ids(effects_as_list()),
        "emitter": _ids(emitters_as_list()),
        "preset": _ids(presets.presets_as_list()),
        "transition": _ids(sequence.transitions_as_list()),
        "ambience bed": _ids(ambience.beds_as_list()),
        "grade": _ids(grades.grades_as_list()),
    }[name]
    missing = expected - live
    assert not missing, f"{name}(s) that used to exist are gone: {sorted(missing)}"


def test_every_scene_can_still_be_fetched():
    """A scene in the list but broken on import would be just as lost."""
    from pulseforge.scenes import get_scene

    for scene in scenes_as_list():
        meta, fn = get_scene(scene["id"])
        assert callable(fn) and meta.get("label")


def test_the_public_helpers_kept_their_names():
    """Renames are the other way things disappear -- these are called from
    web_app.py, the tests and each other."""
    for module, names in [
        (
            sequence,
            [
                "build_audio",
                "audio_spans",
                "plan_shots",
                "text_filter",
                "transitions_as_list",
                "song_durations",
            ],
        ),
        (
            presets,
            [
                "apply_to",
                "presets_as_list",
                "save_user_preset",
                "delete_user_preset",
                "get",
            ],
        ),
        (formats, ["get", "as_list"]),
        (ambience, ["generate", "write_wav", "beds_as_list"]),
        (grades, ["apply_grade", "grades_as_list", "ids"]),
    ]:
        for n in names:
            assert hasattr(module, n), f"{module.__name__}.{n} is missing"


# --------------------------------------------------------------------------
# v8: the AMV studio's own registries
# --------------------------------------------------------------------------
BEAT_EFFECTS = {
    "zoom_punch",
    "shake",
    "push_in",
    "flash",
    "sat_pump",
    "hue_kick",
    "strobe",
    "invert_hit",
    "blur_hit",
    "rgb_split",
    "chroma_ghost",
    "echo_trail",
    "lens_warp",
    "grain",
    "vignette_pulse",
    "bar_slam",
    "mirror",
}
EDIT_STYLES = {
    "classic",
    "hype",
    "action",
    "emotional",
    "sakuga",
    "lyric",
    "retro",
    "edit",
    "cinematic",
    "chill",
    "build_drop",
}
AMV_TRANSITIONS = {
    "cut",
    "crossfade",
    "dissolve",
    "dip_black",
    "dip_white",
    "whip_left",
    "whip_right",
    "zoom_blur",
    "blur_wipe",
    "pixel",
    "radial",
    "circle_open",
    "squeeze",
    "grey",
    "diagonal",
    "slice",
    "smooth_left",
    "wipe_left",
}


def test_every_beat_effect_is_still_registered():
    assert BEAT_EFFECTS <= set(beatfx.FX), BEAT_EFFECTS - set(beatfx.FX)


def test_every_editing_style_is_still_registered():
    assert EDIT_STYLES <= set(editstyles.STYLES), EDIT_STYLES - set(editstyles.STYLES)


def test_every_amv_transition_is_still_registered():
    missing = AMV_TRANSITIONS - set(editstyles.TRANSITIONS)
    assert not missing, missing


def test_the_public_helpers_of_the_new_modules_are_still_there():
    from pulseforge import amvplan, musicmap, palette, shotdna

    for mod, names in (
        (musicmap, ("map_music", "estimate_tempo", "track_beats", "section_at")),
        (shotdna, ("analyse_clip", "window_stats", "describe", "detect_letterbox")),
        (amvplan, ("plan", "cut_points", "assign_shots", "scan_and_analyse")),
        (palette, ("look_from_image", "measure", "light_direction")),
        (beatfx, ("build", "build_chain", "fx_as_list")),
        (editstyles, ("get_style", "styles_as_list", "transition_list")),
    ):
        for n in names:
            assert hasattr(mod, n), f"{mod.__name__}.{n} went missing"
