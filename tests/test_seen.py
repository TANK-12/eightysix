"""Whether anyone can see the Forge window (B34).

Emerson (2026-09-27): "i dont like how much gpu is being used ... especially
when im not even open to the forge app or in a different desktop, diff desktop
or minimised, but leave it when diff monitors". On GNOME Wayland GTK3 never
hears that it was minimised, so WebKit kept the page visible and every
animation ran at full rate. GNOME does send a fully-obscured visibility event
about four seconds after the window is hidden (measured with a probe window);
forge.Seen turns that and the window's state into one answer, and forge.py
unmaps the page while it is False so WebKit pauses it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import forge  # noqa: E402


def test_a_new_window_is_seen():
    assert forge.Seen().seen


def test_fully_obscured_is_not_seen_and_back_again():
    s = forge.Seen()
    assert s.visibility(obscured=True) is True
    assert not s.seen
    assert s.visibility(obscured=False) is True
    assert s.seen


def test_repeated_events_report_no_change():
    s = forge.Seen()
    assert s.visibility(obscured=False) is False
    s.visibility(obscured=True)
    assert s.visibility(obscured=True) is False


def test_minimised_or_unmapped_is_not_seen():
    s = forge.Seen()
    assert s.window_state(iconified=True) is True
    assert not s.seen
    s.window_state(iconified=False)
    assert s.seen
    assert s.mapped(False) is True
    assert not s.seen
    assert s.mapped(True) is True
    assert s.seen


def test_focus_or_the_pointer_means_someone_is_looking():
    # A safety net: if the compositor never says the window is back, the
    # first focus, click, key or pointer entry brings the page back anyway.
    s = forge.Seen()
    s.visibility(obscured=True)
    s.window_state(iconified=True)
    assert s.touched() is True
    assert s.seen
    assert s.touched() is False


def test_touched_does_not_map_a_withdrawn_window():
    s = forge.Seen()
    s.mapped(False)
    assert s.touched() is False
    assert not s.seen


def test_the_rest_setting_is_on_by_default_and_listed_in_settings():
    sys.path.insert(0, os.path.join(os.path.dirname(forge.__file__), "shared"))
    import forge_theme

    entry = forge_theme.SETTINGS["pause_when_hidden"]
    assert entry["default"] is True and entry["kind"] == "bool"
    assert entry["group"] == forge_theme.SPEED
