import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import display_gnome  # noqa: E402


def _mode(mid, w, h, hz, current=False):
    return (mid, w, h, hz, 1.0, [1.0], {"is-current": current} if current else {})


def _state(panel_modes, external=None):
    monitors = [(("eDP-1", "AUO", "x", "0"), panel_modes, {})]
    logical = [(0, 0, 1.0, 0, True, [("eDP-1", "AUO", "x", "0")], {})]
    if external:
        monitors.append((("HDMI-1", "D", "y", "1"), external, {}))
        logical.append((1920, 0, 1.0, 0, False, [("HDMI-1", "D", "y", "1")], {}))
    return (7, monitors, logical, {})


PANEL = [
    _mode("1920x1080@60.049", 1920, 1080, 60.049, current=True),
    _mode("1920x1080@48.040", 1920, 1080, 48.04),
    _mode("1440x1080@59.989", 1440, 1080, 59.989),
]


def test_panel_moves_to_matching_rate_at_same_size():
    layout, note = display_gnome.plan(_state(PANEL), 48)
    assert layout == [(0, 0, 1.0, 0, True, [("eDP-1", "1920x1080@48.040", {})])]
    assert note == "switched to 48 Hz"


def test_external_monitor_keeps_its_mode():
    ext = [_mode("2560x1440@144", 2560, 1440, 144.0, current=True)]
    layout, _ = display_gnome.plan(_state(PANEL, ext), 48)
    assert layout[1] == (1920, 0, 1.0, 0, False, [("HDMI-1", "2560x1440@144", {})])


def test_already_there_or_missing_rate_does_nothing():
    assert display_gnome.plan(_state(PANEL), 60) == ([], "already 60 Hz")
    assert display_gnome.plan(_state(PANEL), 90)[0] == []
