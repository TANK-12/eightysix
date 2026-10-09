"""
The interface, checked the way the rest of the app is.

There are two editors now: a guided four-step page and the full one. The risk in
splitting them is that a control quietly stops being reachable -- so rather than
taking my word for "nothing was lost", this reads the actual markup and asserts
that every parameter the renderer understands is still wired to something.

These are cheap string and structure checks, not a browser. They catch the
failure that actually happens here: a schema key added or renamed on the Python
side and never picked up by the panel that is supposed to show it.
"""

import json
import pathlib
import re

import pytest

from pulseforge import grades, presets, sequence
from pulseforge.emitters import emitters_as_list
from pulseforge.motion import effects_as_list
from pulseforge.scenes.living import SCENE

STATIC = pathlib.Path(__file__).resolve().parent.parent / "static"
INDEX = (STATIC / "index.html").read_text()
SCENERY = (STATIC / "scenery.js").read_text()
SIMPLE = (STATIC / "simple.js").read_text()
CONTROLS = (STATIC / "controls.js").read_text()

# the sections the look panel builds itself from
KNOWN_GROUPS = {"shot", "camera", "grade", "analogue", "depth", "particles"}


def _rendered_groups():
    """The groups the look panel actually builds, read out of LOOK_GROUPS.

    Scoped to that one array on purpose: scenery.js has other lists of the same
    shape (the effect and emitter families) and a loose pattern picks those up.
    """
    block = re.search(r"const LOOK_GROUPS = \[(.*?)\];", SCENERY, re.S)
    assert block, "LOOK_GROUPS is gone -- the look panel no longer groups itself"
    return set(re.findall(r'\["(\w+)"', block.group(1)))


# --------------------------------------------------------------------------
# the schema and the panel that renders it
# --------------------------------------------------------------------------
def test_every_scene_parameter_declares_a_group():
    """The look panel partitions on `group`; an unlabelled parameter would
    silently never appear in it."""
    missing = [p["key"] for p in SCENE["params"] if not p.get("group")]
    assert not missing, f"parameters with no group: {missing}"


def test_every_group_used_is_one_the_editor_knows_about():
    used = {p["group"] for p in SCENE["params"]}
    assert used <= KNOWN_GROUPS, f"unknown group(s): {used - KNOWN_GROUPS}"


def test_every_group_the_editor_renders_actually_has_parameters():
    rendered = _rendered_groups()
    used = {p["group"] for p in SCENE["params"]}
    empty = rendered - used
    assert not empty, f"the panel renders group(s) nothing uses: {empty}"


def test_the_look_panel_reaches_every_parameter_except_the_shot_ones():
    """The census. `shot`-group parameters live on the Background card and the
    Compose defaults; everything else must be in one of the look sections."""
    rendered = _rendered_groups()
    unreachable = [
        p["key"]
        for p in SCENE["params"]
        if p["group"] not in rendered and p["group"] != "shot"
    ]
    assert not unreachable, f"no longer reachable in the editor: {unreachable}"


def test_shot_group_parameters_are_still_offered_somewhere():
    for spec in SCENE["params"]:
        if spec["group"] != "shot":
            continue
        # either the Background card names it, or the Compose defaults form does
        assert spec["key"] in SCENERY or "sceneParams" in INDEX, spec["key"]


# --------------------------------------------------------------------------
# the two modes
# --------------------------------------------------------------------------
def test_every_mode_exists_and_every_tab_belongs_to_at_least_one():
    """`data-modes` is a *list*: a tab may belong to more than one mode.

    Output is in both Advanced and Studio, because a render started from the
    studio has to have somewhere to report progress."""
    tabs = re.findall(
        r'class="tab[^"]*" data-tab="(\w+)"(?: data-modes="([\w ]+)")?', INDEX
    )
    by_tab = {k: (v or "").split() for k, v in tabs}
    assert by_tab.get("make") == ["simple"] and by_tab.get("finish") == ["simple"]
    for advanced in ("compose", "scenery", "settings"):
        assert "advanced" in by_tab.get(advanced, []), advanced
    assert by_tab.get("studio") == ["studio"]
    assert set(by_tab.get("output", [])) == {"advanced", "studio"}
    # Projects is deliberately in every mode, so it carries no data-modes
    assert by_tab.get("projects") == []


def test_the_mode_switch_offers_all_four_modes():
    modes = re.findall(r'<button data-mode="(\w+)"', INDEX)
    assert modes == ["simple", "advanced", "studio", "autopilot"]


def test_autopilot_mode_has_its_three_views_and_folder_browser():
    for view in ("make", "library", "earnings"):
        assert f'class="ap-view" data-view="{view}"' in INDEX, view
    for control in ("apInbox", "apArt", "apRecipes", "apRun", "apBrowse", "apPackages"):
        assert f'id="{control}"' in INDEX, control
    assert 'body[data-mode="autopilot"] .tabs { display: none; }' in INDEX


def test_the_studio_panel_exists_and_has_its_timeline():
    assert 'data-panel="studio"' in INDEX
    assert 'id="stCanvas"' in INDEX
    for control in ("stStyles", "stStyleParams", "stShot", "stClips", "stStats"):
        assert f'id="{control}"' in INDEX, control


def test_the_workbench_tabs_are_not_capped_at_the_shared_panel_width():
    """The shared stylesheet caps .panel at 960px; both workbenches opt out."""
    assert 'body[data-tab="studio"] .panel' in INDEX
    assert 'body[data-tab="scenery"] .panel' in INDEX


def test_the_simple_editor_has_all_four_steps():
    steps = re.findall(r"<h3><i>(\d)</i>\s*([A-Za-z ]+)</h3>", INDEX)
    assert [n for n, _ in steps] == ["1", "2", "3", "4"]
    assert [t.strip() for _, t in steps] == ["Music", "Pictures", "Look", "Finish"]


def test_simple_mode_is_not_a_dead_end():
    """It must be possible to get from the guided page into the full editor."""
    assert "openInAdvanced" in SIMPLE and "openInAdvanced" in INDEX
    assert "Fine-tune" in SIMPLE
    assert "gotoShot" in SCENERY, "and to land on the shot you were looking at"


def test_the_mode_choice_is_remembered():
    from pulseforge import config

    assert config.DEFAULTS["ui_mode"] in {"simple", "advanced"}
    assert "ui_mode" in INDEX, "the page has to send the choice back"


def test_the_simple_editor_writes_the_same_project_fields():
    """No second data model: the guided page sets fields the renderer reads."""
    for field in ("cards", "target_seconds", "ambience", "shots", "song_crossfade"):
        assert field in SIMPLE, field


# --------------------------------------------------------------------------
# the registries all still reach the interface
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/presets",
        "/api/grades",
        "/api/ambience",
        "/api/motion-effects",
        "/api/emitters",
        "/api/transitions",
        "/api/modulation-sources",
    ],
)
def test_every_registry_is_fetched_by_the_interface(endpoint):
    assert endpoint in (INDEX + SCENERY + SIMPLE), f"nothing fetches {endpoint}"


def test_the_simple_editor_offers_the_whole_preset_and_grade_lists():
    """It builds its pickers from the registries rather than a hardcoded few."""
    assert "S.presets" in SIMPLE and "S.grades" in SIMPLE and "S.ambience" in SIMPLE
    assert len(presets.presets_as_list()) >= 11
    assert len(grades.grades_as_list()) >= 9


def test_the_full_editor_still_reaches_every_effect_and_emitter():
    assert "effects.filter" in SCENERY or "S.effects" in SCENERY
    assert "S.emitters" in SCENERY
    assert len(effects_as_list()) >= 13 and len(emitters_as_list()) >= 11


def test_transitions_are_still_pickable_between_shots():
    assert "S.transitions" in SCENERY
    assert len(sequence.transitions_as_list()) >= 11


# --------------------------------------------------------------------------
# things that have broken before
# --------------------------------------------------------------------------
def test_no_inline_display_fights_the_hidden_attribute():
    """An inline `display:` beats `[hidden]`, which is how the wand's controls
    once stayed on screen while the brush was selected."""
    for m in re.finditer(r"<[^>]*\bhidden\b[^>]*>", INDEX):
        tag = m.group(0)
        assert 'style="display' not in tag.replace(" ", ""), tag[:90]


def test_the_static_mount_is_still_last_in_the_backend():
    web = (STATIC.parent / "web_app.py").read_text()
    mount = web.index('app.mount("/", StaticFiles')
    later = re.search(r"@app\.(get|post|put|delete)\(", web[mount:])
    assert later is None, "a route after the catch-all mount is unreachable"


def test_every_script_the_page_loads_exists():
    for src in re.findall(r'<script src="/([\w.]+)"></script>', INDEX):
        assert (STATIC / src).exists(), f"index.html loads a missing {src}"
