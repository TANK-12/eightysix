"""Sections: the headings the home screen sorts its tiles under.

WHY THIS EXISTS
    Emerson found the home screen "not organised well": 26 tiles in one flat
    grid. Sections are discovered like groups: sections/<id>.json holds the
    heading, and an app or group joins one with a "section" manifest field.
    These check the Python half. An app naming no section, or one with no
    file, still reaches the hub; the hub puts it under "Other".

HOW TO RUN
    /usr/bin/python3 tests/test_app_sections.py

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


def _write(dir_, item_id, **fields):
    os.makedirs(dir_, exist_ok=True)
    with open(os.path.join(dir_, f"{item_id}.json"), "w") as f:
        json.dump(fields, f)


def _point_at(tmp):
    forge.APPS_DIR = os.path.join(tmp, "apps")
    forge.GROUPS_DIR = os.path.join(tmp, "groups")
    forge.SECTIONS_DIR = os.path.join(tmp, "sections")
    forge.HUB_DIR = os.path.join(tmp, "hub")


def test_sections_are_discovered_in_order_and_a_bad_file_is_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        _point_at(tmp)
        _write(forge.SECTIONS_DIR, "play", label="Play", icon="🎮", order=3)
        _write(forge.SECTIONS_DIR, "create", label="Create", order=1)
        with open(os.path.join(forge.SECTIONS_DIR, "broken.json"), "w") as f:
            f.write("{nope")
        sections = forge.discover_sections()
        assert list(sections) == ["create", "play"]
        assert sections["play"] == {
            "id": "play",
            "label": "Play",
            "icon": "🎮",
            "blurb": "",
            "order": 3,
        }


def test_section_travels_with_apps_and_groups_into_status_js():
    with tempfile.TemporaryDirectory() as tmp:
        _point_at(tmp)
        _make_app(forge.APPS_DIR, "novel", 9001, 1, section="create")
        _make_app(forge.APPS_DIR, "stray", 9002, 2)
        _make_app(forge.APPS_DIR, "farm", 9003, 3, group="pixel")
        _write(forge.GROUPS_DIR, "pixel", label="Pixel", section="play")
        _write(forge.SECTIONS_DIR, "create", label="Create", order=1)
        backends = forge.discover_backends()
        manager = forge.BackendManager(backends)
        snap = manager.snapshot()
        assert snap["novel"]["section"] == "create"
        assert snap["stray"]["section"] == ""
        manager.write_status()
        with open(os.path.join(forge.HUB_DIR, "status.js")) as f:
            text = f.read()
        lines = dict(
            line.split(" = ", 1) for line in text.strip().splitlines() if " = " in line
        )
        sections = json.loads(lines["window.FORGE_SECTIONS"].rstrip(";"))
        groups = json.loads(lines["window.FORGE_GROUPS"].rstrip(";"))
        assert list(sections) == ["create"]
        assert groups["pixel"]["section"] == "play"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
