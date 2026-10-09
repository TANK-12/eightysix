"""Starting apps: the launch environment, real app names on this laptop, and
Forge apps opened inside the Forge window.

WHY THIS EXISTS
    "none of the apps open except terminal when I ask the acchan thing"
    (Emerson, 2026-09-25). acchan.service starts at login, before GNOME gives
    the user manager WAYLAND_DISPLAY and DISPLAY, so every app it launched had
    no screen to open on. The terminal still opened because gnome-terminal
    asks a D-Bus service, which has the session's variables, to make the
    window. The app-name tests use the .desktop files really installed here
    and skip an app that is not installed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acchan import desktop  # noqa: E402
from acchan.tools import apps  # noqa: E402

DISPLAY_KEYS = ("WAYLAND_DISPLAY", "DISPLAY", "XDG_CURRENT_DESKTOP")


@pytest.fixture
def bare_env(monkeypatch):
    """This process as acchan.service sees it: no display variables."""
    for key in DISPLAY_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(desktop, "_ADOPTED", set())
    monkeypatch.setattr(desktop, "_CACHED", None)
    monkeypatch.setattr(desktop, "_hyprland_signature", lambda: "")
    live = {
        "WAYLAND_DISPLAY": "wayland-9",
        "DISPLAY": ":9",
        "XDG_CURRENT_DESKTOP": "GNOME",
    }
    monkeypatch.setattr(desktop, "_manager_env", lambda: dict(live))
    return live


def test_missing_display_variables_come_from_the_session(bare_env):
    desktop.adopt_session_env()
    assert os.environ["WAYLAND_DISPLAY"] == "wayland-9"
    assert os.environ["DISPLAY"] == ":9"


def test_own_display_variables_are_kept(bare_env, monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    desktop.adopt_session_env()
    assert os.environ["WAYLAND_DISPLAY"] == "wayland-1"
    assert os.environ["DISPLAY"] == ":9"


def test_adopted_variables_follow_a_new_session(bare_env, monkeypatch):
    desktop.adopt_session_env()
    monkeypatch.setattr(
        desktop, "_manager_env", lambda: {"WAYLAND_DISPLAY": "wayland-2"}
    )
    desktop.adopt_session_env()
    assert os.environ["WAYLAND_DISPLAY"] == "wayland-2"


def test_launched_app_gets_the_display(bare_env, monkeypatch):
    seen = {}

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            seen["cmd"] = cmd
            seen["env"] = dict(kwargs.get("env") or os.environ)

    monkeypatch.setattr(desktop.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(
        apps,
        "find_app",
        lambda name, strict=False: {
            "name": "Dolphin",
            "exec": "dolphin %U",
            "categories": "",
        },
    )
    assert apps.launch_app("file explorer") == "Started Dolphin."
    assert seen["cmd"][-1] == "dolphin"
    assert seen["env"]["WAYLAND_DISPLAY"] == "wayland-9"
    assert seen["env"]["DISPLAY"] == ":9"


def _installed(app_id: str) -> bool:
    return any(a["id"] == app_id for a in apps._entries())


@pytest.mark.parametrize(
    "said, app_id",
    [
        ("firefox", "firefox"),
        ("browser", "firefox"),
        ("web browser", "firefox"),
        ("files", "org.gnome.Nautilus"),
        ("file explorer", "org.kde.dolphin"),
        ("qobuz", "com.blitzfc.qbz"),
        ("qbz", "com.blitzfc.qbz"),
        ("steam", "com.valvesoftware.Steam"),
        ("terminal", "org.gnome.Terminal"),
        ("text editor", "org.gnome.TextEditor"),
        ("blender", "org.blender.Blender"),
        ("cosmos", "forge:cosmos"),
        ("novelforge", "forge:novelforge"),
        ("drift peaks", "forge:driftpeaks"),
    ],
)
def test_real_app_names_on_this_laptop(said, app_id):
    if not _installed(app_id):
        pytest.skip(f"{app_id} is not installed here")
    found = apps.find_app(said)
    assert found is not None and found["id"] == app_id
    strict = apps.find_app(said, strict=True)
    assert strict is not None and strict["id"] == app_id


def test_forge_apps_are_listed():
    listed = apps.list_apps("forge")
    assert "Cosmos [Forge]" in listed


def test_forge_app_opens_in_the_running_forge(monkeypatch):
    asked, started = [], []
    monkeypatch.setattr(
        apps.forge_open, "request_open", lambda name: asked.append(name) or "ok"
    )
    monkeypatch.setattr(apps, "hypr_exec", started.append)
    assert apps.launch_app("cosmos") == "Opened Cosmos in Forge."
    assert asked == ["cosmos"] and started == []


def test_forge_app_starts_forge_when_it_is_closed(monkeypatch):
    started = []
    monkeypatch.setattr(apps.forge_open, "request_open", lambda name: None)
    monkeypatch.setattr(apps.forge_open, "forge_running", lambda: False)
    monkeypatch.setattr(apps, "hypr_exec", started.append)
    assert apps.launch_app("cosmos") == "Starting Forge on Cosmos."
    assert started and started[0].endswith("forge.py --app cosmos")


def test_old_forge_without_the_socket_is_not_started_twice(monkeypatch):
    started, focused = [], []
    monkeypatch.setattr(apps.forge_open, "request_open", lambda name: None)
    monkeypatch.setattr(apps.forge_open, "forge_running", lambda: True)
    monkeypatch.setattr(apps, "hypr_exec", started.append)
    monkeypatch.setattr(apps, "_focus_forge", lambda: focused.append(True))
    reply = apps.launch_app("cosmos")
    assert started == [] and focused == [True]
    assert "restart" in reply.lower() and "Cosmos" in reply
