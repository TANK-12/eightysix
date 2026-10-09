"""Groups: one hub tile standing for several apps, opened as a chooser.

WHY THIS EXISTS
    Emberfield moved inside a "Pixel games" tile (PLAN-pixel-games-tab.md) and
    later pixel games join it with one manifest line. These check the Python
    half: groups are discovered from groups/*.json, members attach in app
    order, and an app naming a group that has no file keeps its own tile. The
    hub half is tests/browser/hub_groups_harness.js.

HOW TO RUN
    /usr/bin/python3 tests/test_app_groups.py

    The system python on purpose, as in test_app_discovery.py: forge.py
    imports gi/Gtk at module level.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import forge  # noqa: E402
from test_app_discovery import _make_app  # noqa: E402


def _write_group(groups_dir, group_id, **fields):
    os.makedirs(groups_dir, exist_ok=True)
    with open(os.path.join(groups_dir, f"{group_id}.json"), "w") as f:
        json.dump(fields, f)


def _point_at(tmp):
    forge.APPS_DIR = os.path.join(tmp, "apps")
    forge.GROUPS_DIR = os.path.join(tmp, "groups")
    forge.HUB_DIR = os.path.join(tmp, "hub")


def test_groups_are_discovered_and_a_bad_file_is_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        _point_at(tmp)
        _write_group(forge.GROUPS_DIR, "pixel-games", label="Pixel games", order=7)
        with open(os.path.join(forge.GROUPS_DIR, "broken.json"), "w") as f:
            f.write("{nope")
        groups = forge.discover_groups()
        assert list(groups) == ["pixel-games"]
        assert groups["pixel-games"]["label"] == "Pixel games"
        assert groups["pixel-games"]["order"] == 7


def test_members_attach_in_app_order_and_an_unknown_group_keeps_its_tile():
    with tempfile.TemporaryDirectory() as tmp:
        _point_at(tmp)
        _make_app(forge.APPS_DIR, "zeta", 9001, 2, group="pixel-games")
        _make_app(forge.APPS_DIR, "alpha", 9002, 1, group="pixel-games")
        _make_app(forge.APPS_DIR, "stray", 9003, 3, group="no-such-group")
        _make_app(forge.APPS_DIR, "tool", 9004, 4)
        _write_group(forge.GROUPS_DIR, "pixel-games", label="Pixel games")
        _write_group(forge.GROUPS_DIR, "empty", label="Nobody joins this")

        backends = forge.discover_backends()
        assert [b.name for b in backends] == ["alpha", "zeta", "stray", "tool"]
        attached = forge.attach_groups(backends, forge.discover_groups())
        assert list(attached) == ["pixel-games"]
        assert attached["pixel-games"]["members"] == ["alpha", "zeta"]

        snap = forge.BackendManager(backends).snapshot()
        assert set(snap) == {"alpha", "zeta", "stray", "tool"}  # nobody dropped
        assert snap["stray"]["group"] == "no-such-group"  # the hub ignores it
        assert snap["alpha"]["order"] == 1


def test_status_script_carries_the_groups_beside_the_apps():
    with tempfile.TemporaryDirectory() as tmp:
        _point_at(tmp)
        _make_app(forge.APPS_DIR, "alpha", 9002, 1, group="pixel-games")
        _write_group(forge.GROUPS_DIR, "pixel-games", label="Pixel games")
        forge.BackendManager(forge.discover_backends()).write_status()
        with open(os.path.join(forge.HUB_DIR, "status.js")) as f:
            lines = f.read().splitlines()
        prefix = "window.FORGE_GROUPS = "
        assert lines[0].startswith("window.FORGE_STATUS = ")
        found = [line for line in lines if line.startswith(prefix)]
        groups = json.loads(found[0][len(prefix) : -1])
        assert groups["pixel-games"]["members"] == ["alpha"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS  {name}")
