import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from display import internal_panel, monitor_argv  # noqa: E402

MON = {
    "name": "eDP-1",
    "width": 1920,
    "height": 1080,
    "refreshRate": 48.04,
    "x": 0,
    "y": 0,
    "scale": 1.0,
    "transform": 0,
    "availableModes": ["1920x1080@60.05Hz", "1920x1080@48.04Hz"],
}


def test_uses_the_panels_exact_rate():
    # This exact command was run on the real panel and switched it to 60.049 Hz.
    assert monitor_argv(MON, 60) == [
        "hyprctl",
        "eval",
        'hl.monitor({ output = "eDP-1", mode = "1920x1080@60.05Hz", position = "0x0", scale = 1 })',
    ]


def test_keeps_scale_and_rotation():
    mon = {**MON, "scale": 1.25, "transform": 1, "refreshRate": 60.05}
    assert monitor_argv(mon, 48) == [
        "hyprctl",
        "eval",
        'hl.monitor({ output = "eDP-1", mode = "1920x1080@48.04Hz", position = "0x0", scale = 1.25, transform = 1 })',
    ]


def test_rate_the_panel_lacks_is_skipped():
    assert monitor_argv(MON, 144) is None


def test_already_at_that_rate_is_skipped():
    assert monitor_argv(MON, 48) is None


def test_odd_names_or_modes_never_reach_lua():
    assert monitor_argv({**MON, "name": 'eDP-1"}) os.execute("x'}, 60) is None
    bad_mode = {**MON, "availableModes": ['1920x1080@60.05Hz" })--']}
    assert monitor_argv(bad_mode, 60) is None


def test_internal_panel_is_the_edp_output():
    external = {**MON, "name": "DP-3"}
    assert internal_panel([external, MON]) is MON
    assert internal_panel([external]) is None
