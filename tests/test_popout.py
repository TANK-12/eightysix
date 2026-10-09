"""Pop-out monitor choice (A22): which screen an app popped out of Forge
goes to, and whether it fills it."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from forge_popout import pick_monitor, window_title  # noqa: E402


def test_one_monitor_opens_a_normal_window():
    assert pick_monitor(1, 0, 0) == (0, False)
    assert pick_monitor(0, None, None) == (0, False)


def test_two_monitors_fill_the_one_forge_is_not_on():
    assert pick_monitor(2, 0) == (1, True)
    assert pick_monitor(2, 1) == (0, True)


def test_the_pointers_monitor_wins_when_forge_is_not_there():
    assert pick_monitor(3, 0, 2) == (2, True)


def test_pointer_on_forges_monitor_goes_to_the_next_one():
    assert pick_monitor(3, 1, 1) == (2, True)
    assert pick_monitor(3, 2, 2) == (0, True)


def test_unknown_or_bad_indices_fall_back_to_the_first():
    assert pick_monitor(3, None, None) == (1, True)
    assert pick_monitor(3, 7, 9) == (1, True)


def test_window_title_names_the_app():
    assert window_title("Board") == "Board - Forge"
