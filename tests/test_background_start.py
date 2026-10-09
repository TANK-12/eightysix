"""Forge starting hidden at login and coming up instantly (S7, A4).

Emerson: "start up of the app faster without the ui loading in, maybe have it
launch in the background on start up". Forge starts at login with its window
hidden (forge.py --background from ~/.config/autostart); opening Forge then
only asks the running one to show its window, and closing the window hides it
again unless Settings says to quit.
"""

import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "shared"))

import forge  # noqa: E402
import forge_open  # noqa: E402
import forge_theme  # noqa: E402


def test_start_at_login_writes_and_removes_the_autostart_entry():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "autostart" / "forge.desktop"
        forge_theme.set_autostart(True, path)
        text = path.read_text()
        assert "Exec=/usr/bin/python3 " in text, "the system python, never a venv's"
        assert "forge.py --background" in text
        assert "X-GNOME-Autostart-enabled=true" in text
        forge_theme.set_autostart(True, path)  # twice is fine
        forge_theme.set_autostart(False, path)
        assert not path.exists()
        forge_theme.set_autostart(False, path)  # and so is removing nothing


def test_launch_flags():
    assert forge.launch_flags([]) == {"background": False}
    assert forge.launch_flags(["--background"]) == {"background": True}
    assert forge.launch_flags(["--app", "cosmos"]) == {"background": False}


def test_a_second_launch_asks_the_running_forge_to_show_itself():
    shown = []
    with tempfile.TemporaryDirectory() as tmp:
        sock = Path(tmp) / "forge.sock"
        server = forge_open.serve(
            lambda name: name == "cosmos", path=sock, on_show=shown.append
        )
        assert server is not None
        try:
            assert forge_open.request_show("token-123", path=sock) == "ok"
            assert (
                forge_open.request_open("", path=sock) == "ok"
            ), "a ping still answers"
            assert forge_open.request_open("cosmos", path=sock) == "ok"
            assert forge_open.request_open("nope", path=sock) == "unknown"
        finally:
            server.close()
    assert shown == ["token-123"], "only the show request shows the window"


def test_show_with_nothing_running_says_so():
    with tempfile.TemporaryDirectory() as tmp:
        assert forge_open.request_show("", path=Path(tmp) / "none.sock") is None


def test_the_new_settings_have_sane_defaults_and_cleaning():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        s = forge_theme.load(path)
        assert s["start_at_login"] is True
        assert s["close_action"] == "background"
        assert s["hidden_apps"] == [] and s["archived_apps"] == []
        s = forge_theme.save(
            {
                "hidden_apps": ["cosmos", "cosmos", "bad name!", 7, "group:games"],
                "close_action": "explode",
            },
            path,
        )
        assert s["hidden_apps"] == ["cosmos", "group:games"]
        assert s["close_action"] == "background"


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except (AssertionError, AttributeError, TypeError, KeyError) as exc:
                failed += 1
                print(f"FAIL {name}: {exc!r}")
    sys.exit(1 if failed else 0)


def test_hub_is_told_when_forge_starts_hidden():
    assert forge.shell_url() == forge.SHELL_URL
    assert forge.shell_url(background=True) == forge.SHELL_URL + "?background=1"
    assert forge.shell_url("cosmos") == forge.SHELL_URL + "#app=cosmos"
    assert (
        forge.shell_url("cosmos", True) == forge.SHELL_URL + "?background=1#app=cosmos"
    )
