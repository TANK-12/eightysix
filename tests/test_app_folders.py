"""App folders (drag one app onto another in the hub): the app_folders
setting is cleaned on load and save, and the hub may save it through
forge.py."""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "shared"))

import forge  # noqa: E402
import forge_theme  # noqa: E402


def test_a_folder_needs_two_apps_and_an_app_sits_in_one_folder():
    got = forge_theme._clean_folders(
        {
            "a1": {"label": "Games", "members": ["cosmos", "arcade"]},
            "a2": {"label": "Solo", "members": ["board"]},
            "a3": {"label": "", "members": ["arcade", "board", "files"]},
        }
    )
    assert got == {
        "a1": {"label": "Games", "members": ["cosmos", "arcade"]},
        "a3": {"label": "Folder", "members": ["board", "files"]},
    }


def test_bad_ids_labels_and_shapes_are_dropped():
    assert forge_theme._clean_folders("nope") == {}
    assert forge_theme._clean_folders({"bad id!": {"members": ["a", "b"]}}) == {}
    assert forge_theme._clean_folders({"x": ["a", "b"]}) == {}
    long = forge_theme._clean_folders({"x": {"label": "L" * 90, "members": ["a", "b"]}})
    assert long["x"]["label"] == "L" * 40


def test_saved_folders_come_back_from_the_settings_file(tmp_path):
    path = tmp_path / "theme.json"
    folders = {"k1": {"label": "Make", "members": ["pixelforge", "panelforge"]}}
    picked = forge.save_hub_settings(
        {"app_folders": folders, "accent": "#000000"}, path
    )
    assert picked == {"app_folders": folders}, "the hub may save folders, not colours"
    assert forge_theme.load(path)["app_folders"] == folders


def test_no_folders_by_default(tmp_path):
    assert forge_theme.load(tmp_path / "none.json")["app_folders"] == {}
