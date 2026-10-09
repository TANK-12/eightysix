"""Full screen as three separate wishes (S7, A16).

Emerson: "the full screen is still broken and will un-window the whole forge
app". With Start full screen on, the window being full screen and an app being
full screen were one flag, so leaving an app's full screen (or pressing F11
in an app) dropped the whole window out of full screen, and the bar's Full
screen button did nothing because the window already was. forge.FullScreen
keeps them apart: the window fills the screen while any wish holds, and the
hub hides its bar only for the app's.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import forge  # noqa: E402


def test_start_full_screen_keeps_the_bar():
    fs = forge.FullScreen(desktop=True)
    assert fs.window and not fs.app


def test_an_app_full_screen_inside_start_full_screen_leaves_the_window_alone():
    fs = forge.FullScreen(desktop=True)
    fs.set_app(True)
    assert fs.window and fs.app
    fs.set_app(False)
    assert fs.window, "leaving the app's full screen must not un-window Forge"
    assert not fs.app


def test_the_key_in_an_app_cycles_window_then_app_then_back():
    # Emerson (2026-10-07): Alt+F goes from the normal window under GNOME's
    # bar, to the window full screen with the hub's bar, to the app alone
    # with the bar on hover, and round again.
    fs = forge.FullScreen()
    fs.key(app_open=True)
    assert fs.window and fs.desktop and not fs.app
    fs.key(app_open=True)
    assert fs.window and fs.app
    fs.key(app_open=True)
    assert not fs.window and not fs.app
    fs.key(app_open=True)
    assert fs.window and not fs.app


def test_the_key_after_the_app_s_own_button_goes_back_to_the_window():
    fs = forge.FullScreen()
    fs.set_app(True)
    fs.key(app_open=True)
    assert not fs.window and not fs.app


def test_the_key_on_the_home_screen_has_only_two_levels():
    fs = forge.FullScreen()
    fs.key(app_open=False)
    assert fs.window and not fs.app
    fs.key(app_open=False)
    assert not fs.window


def test_the_key_on_the_home_screen_toggles_the_window():
    fs = forge.FullScreen(desktop=True)
    fs.key(app_open=False)
    assert not fs.window
    fs.key(app_open=False)
    assert fs.window and not fs.app


def test_a_windowed_forge_fills_the_screen_for_an_app_and_comes_back():
    fs = forge.FullScreen()
    assert not fs.window
    fs.set_app(True)
    assert fs.window
    fs.set_app(False)
    assert not fs.window


def test_escape_leaves_the_app_full_screen_only():
    fs = forge.FullScreen(desktop=True)
    fs.set_app(True)
    assert fs.escape() is True
    assert fs.window and not fs.app
    assert fs.escape() is False, "Esc on the desktop belongs to the page"


def test_escape_during_a_video_full_screen_is_the_page_s():
    fs = forge.FullScreen()
    fs.set_element(True)
    assert fs.window
    assert fs.escape() is False
    fs.set_element(False)
    assert not fs.window


def test_a_video_full_screen_inside_an_app_full_screen_returns_to_it():
    fs = forge.FullScreen()
    fs.set_app(True)
    fs.set_element(True)
    fs.set_element(False)
    assert fs.window and fs.app


def test_the_window_manager_taking_full_screen_away_clears_every_wish():
    fs = forge.FullScreen(desktop=True)
    fs.set_app(True)
    fs.window_left()
    assert not fs.window and not fs.app and not fs.desktop


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except (AssertionError, AttributeError) as exc:
                failed += 1
                print(f"FAIL {name}: {exc!r}")
    sys.exit(1 if failed else 0)
