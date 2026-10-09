"""Forge's own keys (S2: A16, A11, A12, A4) and leaving full screen.

One table maps an action to the keys that do it; forge.py catches them on the
window before the page sees them, so they work inside any app. Keys are
written the way people say them ("Alt+F"), and Settings may override the
defaults. Leaving full screen puts the window back as it was before.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import forge  # noqa: E402
from gi.repository import Gdk  # noqa: E402

ALT = Gdk.ModifierType.MOD1_MASK
CTRL = Gdk.ModifierType.CONTROL_MASK
SHIFT = Gdk.ModifierType.SHIFT_MASK
NUMLOCK = Gdk.ModifierType.MOD2_MASK


def key(name):
    return Gdk.keyval_from_name(name)


def test_keys_are_written_the_way_people_say_them():
    assert forge.parse_key("Alt+F") == (key("f"), ALT)
    assert forge.parse_key("alt + space") == (key("space"), ALT)
    assert forge.parse_key("F11") == (key("F11"), 0)
    assert forge.parse_key("Alt+Left") == (key("Left"), ALT)
    assert forge.parse_key("Ctrl+Alt+3") == (key("3"), ALT | CTRL)
    assert forge.parse_key("") is None
    assert forge.parse_key("Alt+Nonsense") is None


def test_default_table():
    table = forge.key_table()
    assert forge.key_action(key("f"), ALT, table) == "fullscreen"
    assert forge.key_action(key("F11"), 0, table) == "fullscreen"
    assert forge.key_action(key("Left"), ALT, table) == "prev-app"
    assert forge.key_action(key("Right"), ALT, table) == "next-app"
    assert forge.key_action(key("1"), ALT, table) == "app-1"
    assert forge.key_action(key("9"), ALT, table) == "app-9"
    assert forge.key_action(key("space"), ALT, table) == "overview"
    assert forge.key_action(key("z"), ALT, table) == "zen"


def test_plain_f_no_longer_toggles_full_screen():
    table = forge.key_table()
    assert forge.key_action(key("f"), 0, table) is None
    assert forge.key_action(key("F"), SHIFT, table) is None


def test_num_lock_and_caps_do_not_get_in_the_way():
    table = forge.key_table()
    assert forge.key_action(key("F"), ALT | NUMLOCK, table) == "fullscreen"
    assert forge.key_action(key("Left"), ALT | NUMLOCK, table) == "prev-app"


def test_extra_modifiers_do_not_match():
    table = forge.key_table()
    assert forge.key_action(key("f"), ALT | CTRL, table) is None
    assert (
        forge.key_action(key("Left"), ALT | CTRL, table) is None
    )  # GNOME's workspace key


def test_settings_can_rebind_an_action():
    table = forge.key_table({"overview": "Alt+Down", "fullscreen": "Alt+Return, F11"})
    assert forge.key_action(key("Down"), ALT, table) == "overview"
    assert forge.key_action(key("space"), ALT, table) is None
    assert forge.key_action(key("Return"), ALT, table) == "fullscreen"
    assert forge.key_action(key("f"), ALT, table) is None
    # A broken entry keeps the default rather than losing the action.
    assert (
        forge.key_action(key("z"), ALT, forge.key_table({"zen": "Alt+Nope"})) == "zen"
    )


def test_leaving_full_screen_returns_to_how_it_was():
    assert forge.restore_plan({"maximized": True, "size": (1400, 900)}) == ("maximize",)
    assert forge.restore_plan({"maximized": False, "size": (1200, 800)}) == (
        "resize",
        1200,
        800,
    )


def test_started_full_screen_comes_back_maximised():
    # Start full screen had no "before": come back as a normal maximised
    # window with its title bar, not a bare borderless one.
    assert forge.restore_plan(None) == ("maximize",)


def test_key_overrides_are_cleaned_when_saved():
    import sys as _sys
    import tempfile
    from pathlib import Path

    _sys.path.insert(0, forge.SHARED_DIR)
    import forge_theme

    path = Path(tempfile.mkdtemp()) / "s.json"
    saved = forge_theme.save(
        {"hub_keys": {"overview": " Alt+Down ", "zen": "", "not-an-action": "Alt+Q"}},
        path,
    )["hub_keys"]
    assert saved == {"overview": "Alt+Down"}
    assert set(forge_theme.HUB_KEY_LABELS) == set(forge_theme.HUB_KEYS)


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
