"""Settings > Speed and detail (Emerson, 2026-09-27): every frame-rate and
detail slider in one section, with plugged-in and battery versions, and the
battery ones applied by the hub, forge.py and the Browser's pages.

The JS halves (shared/forge_power.js, shared/forge_webcap.js) run under node,
so the rules are checked in the same code the pages load."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT))

import forge_theme  # noqa: E402

SPEED = forge_theme.SPEED
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")


def node(script: str) -> Any:
    out = subprocess.run(
        [NODE or "node", "-e", script],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=ROOT,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# --- the settings table -----------------------------------------------------


def test_every_pair_names_two_real_settings_and_a_known_rule():
    for key, (twin, rule) in forge_theme.POWER_PAIRS.items():
        assert key in forge_theme.SETTINGS, key
        assert twin in forge_theme.SETTINGS, twin
        assert rule in ("min", "scale"), rule


def test_new_settings_keep_todays_behaviour_plugged_in():
    s = forge_theme.load(Path("/nonexistent/settings.json"))
    assert s["video_fps"] == 60 and s["video_height"] == "2160"
    assert s["smooth_scroll"] is True and s["battery_particles"] == 0.5
    plugged = forge_theme.power_values(s, on_battery=False)
    assert plugged["max_fps"] == 60 and plugged["particle_amount"] == 1.0


def test_battery_values_only_ever_lighten():
    s = forge_theme.load(Path("/nonexistent/settings.json"))
    s.update(
        max_fps=40,
        battery_fps=50,  # higher than plugged in: plugged-in cap still holds
        video_fps=60,
        battery_video_fps=30,
        video_height="720",
        battery_video_height="1080",
        smooth_scroll=True,
        battery_smooth_scroll=False,
        particle_amount=1.5,
        desktop_particle_amount=2.0,
        battery_particles=0.5,
    )
    now = forge_theme.power_values(s, on_battery=True)
    assert now["max_fps"] == 40
    assert now["video_fps"] == 30
    assert now["video_height"] == "720"
    assert now["smooth_scroll"] is False
    assert now["particle_amount"] == 0.75
    assert now["desktop_particle_amount"] == 1.0


def test_every_frame_rate_setting_is_in_the_speed_section():
    for key, spec in forge_theme.SETTINGS.items():
        if spec.get("unit") == "fps" or key.endswith("_fps"):
            groups = [spec.get("group"), *spec.get("also", [])]
            assert SPEED in groups, key


def test_also_names_only_real_groups():
    groups = {s.get("group") for s in forge_theme.SETTINGS.values()}
    for key, spec in forge_theme.SETTINGS.items():
        for name in spec.get("also", []):
            assert name in groups and name != spec.get("group"), key


def test_the_theme_carries_the_pairs_for_the_pages():
    theme = forge_theme.theme(forge_theme.load(Path("/nonexistent/settings.json")))
    assert theme["power_pairs"]["max_fps"] == ["battery_fps", "min"]
    assert theme["battery_video_height"] == "1080"


# --- shared/forge_power.js agrees with Python --------------------------------


@needs_node
@pytest.mark.parametrize("on_battery", [False, True])
def test_the_js_resolver_matches_python(on_battery):
    s = forge_theme.load(Path("/nonexistent/settings.json"))
    s.update(
        max_fps=45,
        battery_fps=20,
        video_height="1440",
        battery_video_height="480",
        battery_smooth_scroll=False,
        particle_amount=1.25,
        battery_particles=0.4,
    )
    theme = {**s, "power_pairs": forge_theme.theme(s)["power_pairs"]}
    got = node(
        "const P = require('./shared/forge_power.js');"
        f"console.log(JSON.stringify(P.paired({json.dumps(theme)}, {json.dumps(on_battery)})));"
    )
    assert got == forge_theme.power_values(s, on_battery)


# --- shared/forge_webcap.js: the Browser's pages ----------------------------

WEBCAP = """
const window = { requestAnimationFrame: (f) => 1, cancelAnimationFrame: () => {} };
window.MediaSource = { isTypeSupported: () => true };
globalThis.window = window;
globalThis.HTMLMediaElement = function () {};
HTMLMediaElement.prototype.canPlayType = () => "probably";
eval(require('fs').readFileSync('shared/forge_webcap.js', 'utf8'));
"""
YT = 'video/webm; codecs="vp9"; width={w}; height={h}; framerate={f}'


@needs_node
def test_video_formats_above_the_caps_are_refused():
    types = [
        YT.format(w=1920, h=1080, f=60),
        YT.format(w=1920, h=1080, f=30),
        YT.format(w=1280, h=720, f=29.97),
        YT.format(w=1080, h=1920, f=30),  # an upright Short counts its width
        YT.format(w=640, h=360, f=24),
        'video/mp4; codecs="avc1.4d401f"',  # nothing to judge: left alone
    ]
    got = node(
        WEBCAP
        + "window.ForgeWebCap.set({video_fps: 30, video_height: '720', max_fps: 60});"
        + f"console.log(JSON.stringify({json.dumps(types)}.map((t) => ["
        + "window.MediaSource.isTypeSupported(t),"
        + "new HTMLMediaElement().canPlayType(t) !== ''])));"
    )
    assert [a for a, _ in got] == [False, False, True, False, True, True]
    assert [b for _, b in got] == [a for a, _ in got]


@needs_node
def test_no_caps_means_every_format_passes():
    got = node(
        WEBCAP
        + "window.ForgeWebCap.set({video_fps: 60, video_height: '2160', max_fps: 60});"
        + f"console.log(JSON.stringify(window.MediaSource.isTypeSupported({json.dumps(YT.format(w=3840, h=2160, f=60))})));"
    )
    assert got is True


def test_the_view_script_carries_the_cap_and_the_values():
    pytest.importorskip("gi")
    import forge_views

    script = forge_views.power_script({"max_fps": 24, "video_fps": 30})
    assert "window.ForgeFrameCap" in script and "ForgeWebCap" in script
    assert '"max_fps": 24' in script


# --- the Settings page collates them ------------------------------------------


def test_settings_page_draws_also_rows_in_the_second_card():
    js = (ROOT / "apps/settings/static/app.js").read_text(encoding="utf-8")
    assert "spec.also" in js, "buildGroups must read the also list"


# --- easing off (Emerson, 2026-09-29): GPU load and a flat battery ------------


def ease(theme: dict, on_battery: bool, state: dict) -> Any:
    return node(
        "const P = require('./shared/forge_power.js');"
        f"console.log(JSON.stringify(P.values({json.dumps(theme)}, {json.dumps(on_battery)}, {json.dumps(state)})));"
    )


BASE = {
    "max_fps": 60,
    "particle_fps": 30,
    "desktop_particle_fps": 30,
    "particle_amount": 1.2,
    "desktop_particle_amount": 1.0,
    "desktop_visualiser_fps": 30,
    "battery_fps": 30,
    "battery_particle_fps": 20,
    "battery_particles": 0.5,
    "battery_visualiser": False,
    "battery_saver": 20,
}


@needs_node
def test_each_gpu_level_adds_one_step():
    theme = {
        **BASE,
        "power_pairs": forge_theme.theme(forge_theme.load(Path("/nonexistent/x.json")))[
            "power_pairs"
        ],
    }
    one = ease(theme, False, {"gpu": 1})
    assert one["visualiser_shown"] is False and one["desktop_visualiser"] == "off"
    assert one["particle_amount"] == 1.2 and one["max_fps"] == 60
    two = ease(theme, False, {"gpu": 2})
    assert two["particle_amount"] == 0.6 and two["desktop_particle_amount"] == 0.5
    assert two["max_fps"] == 60
    three = ease(theme, False, {"gpu": 3})
    assert three["max_fps"] == 25 and three["particle_fps"] == 25
    assert three["desktop_particle_fps"] == 25 and three["desktop_visualiser_fps"] == 25
    none = ease(theme, False, {"gpu": 0})
    assert "visualiser_shown" not in none and none["max_fps"] == 60


@needs_node
def test_switch_off_and_battery_rules():
    theme = {
        **BASE,
        "power_pairs": forge_theme.theme(forge_theme.load(Path("/nonexistent/x.json")))[
            "power_pairs"
        ],
    }
    assert ease({**theme, "gpu_ease": False}, False, {"gpu": 3})["max_fps"] == 60
    unplugged = ease(theme, True, {"gpu": 0, "battery": 80})
    assert unplugged["max_fps"] == 30 and unplugged["particle_fps"] == 20
    assert (
        unplugged["visualiser_shown"] is False and unplugged["particle_amount"] == 0.6
    )
    flat = ease(theme, True, {"gpu": 0, "battery": 15})
    assert flat["max_fps"] == 25 and flat["particle_fps"] == 20  # never under 20
    assert flat["particle_amount"] == 0.3
    kept = ease({**theme, "battery_visualiser": True}, True, {"battery": 80})
    assert "visualiser_shown" not in kept


def test_new_settings_are_in_speed_and_detail():
    for key in (
        "gpu_ease",
        "gpu_ease_note",
        "battery_particle_fps",
        "battery_visualiser",
        "battery_saver",
    ):
        assert forge_theme.SETTINGS[key]["group"] == SPEED, key
    assert forge_theme.SETTINGS["battery_particle_fps"]["min"] == 20
