"""App size, text size and icon size (S2, A15).

App size is WebKit page zoom on the one hub view, so the hub and every app lay
out again at the new size instead of being stretched by CSS zoom (which is
what pushed apps off centre and grew a sideways scrollbar). Pages keep
talking in CSS pixels; the browser views laid over the window need window
pixels, so their rects are multiplied by the zoom on the way through.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "shared"))

import forge  # noqa: E402
import forge_theme  # noqa: E402
import forge_views  # noqa: E402


def test_page_zoom_takes_the_saved_scale():
    assert forge.page_zoom(1.25) == 1.25
    assert forge.page_zoom("1.5") == 1.5


def test_page_zoom_falls_back_and_clamps():
    assert forge.page_zoom(None) == 1.0
    assert forge.page_zoom("big") == 1.0
    assert forge.page_zoom(0) == 1.0
    assert forge.page_zoom(9) == forge.PAGE_ZOOM_MAX
    assert forge.page_zoom(0.1) == forge.PAGE_ZOOM_MIN


def test_view_rects_become_window_pixels():
    msg = {"op": "rect", "id": "a", "rect": [10, 20, 300, 200]}
    out = forge_views.to_window(msg, 1.5)
    assert out["rect"] == [15.0, 30.0, 450.0, 300.0]
    assert msg["rect"] == [10, 20, 300, 200]  # the caller's message is untouched


def test_view_create_and_inset_are_scaled_too():
    create = {"op": "create", "id": "a", "owner": "browser", "rect": [0, 40, 800, 600]}
    assert forge_views.to_window(create, 1.25)["rect"] == [0.0, 50.0, 1000.0, 750.0]
    inset = forge_views.to_window({"op": "inset", "top": 40, "bottom": 60}, 1.25)
    assert (inset["top"], inset["bottom"]) == (50.0, 75.0)


def test_view_messages_pass_through_at_100_percent():
    msg = {"op": "navigate", "id": "a", "url": "https://example.org"}
    assert forge_views.to_window(msg, 1.0) == msg
    assert (
        forge_views.to_window({"op": "rect", "id": "a", "rect": "junk"}, 2)["rect"]
        == "junk"
    )


def test_app_size_setting_covers_the_whole_hub():
    spec = forge_theme.SETTINGS["ui_scale"]
    assert spec["label"] == "App size"
    assert (spec["min"], spec["max"], spec["default"]) == (0.8, 1.5, 1.0)


def test_text_and_icon_size_sit_with_app_size():
    for key, label in (
        ("ui_scale", "App size"),
        ("text_scale", "Text size"),
        ("icon_scale", "Icon size"),
    ):
        spec = forge_theme.SETTINGS[key]
        assert spec["group"] == forge_theme.SIZE, key
        assert spec["label"] == label
        assert spec["default"] == 1.0
    assert forge_theme.SETTINGS["text_scale"]["max"] == 1.5


def test_sizes_are_saved_and_clamped(tmp_path=None):
    import tempfile
    from pathlib import Path

    path = Path(tmp_path or tempfile.mkdtemp()) / "settings.json"
    saved = forge_theme.save({"text_scale": 1.3, "icon_scale": 7}, path)
    assert saved["text_scale"] == 1.3
    assert saved["icon_scale"] == forge_theme.SETTINGS["icon_scale"]["max"]
    assert forge_theme.load(path)["text_scale"] == 1.3


def test_custom_presets_are_cleaned():
    kept = forge_theme.save(
        {
            "size_presets": [
                {
                    "name": "Night reading",
                    "ui_scale": 1.1,
                    "text_scale": 1.4,
                    "icon_scale": 1.2,
                },
                {"name": "", "ui_scale": 1},  # no name: dropped
                "junk",
                {"name": "x" * 80, "ui_scale": 9, "text_scale": "big", "icon_scale": 1},
            ]
        },
        __import__("pathlib").Path(__import__("tempfile").mkdtemp()) / "s.json",
    )["size_presets"]
    assert [p["name"] for p in kept] == ["Night reading", "x" * 30]
    assert kept[1]["ui_scale"] == 1.5 and kept[1]["text_scale"] == 1.0


def test_preset_list_is_built_ins_then_yours():
    names = [
        p["name"]
        for p in forge_theme.size_presets(
            {
                "size_presets": [
                    {"name": "Mine", "ui_scale": 1, "text_scale": 1.2, "icon_scale": 1}
                ]
            }
        )
    ]
    assert names[:5] == ["Small", "Default", "Comfortable", "Large", "Extra large"]
    assert names[-1] == "Mine"
    default = forge_theme.size_presets({})[1]
    assert (default["ui_scale"], default["text_scale"], default["icon_scale"]) == (
        1.0,
        1.0,
        1.0,
    )


def test_the_hub_may_save_only_sizes():
    import json
    import tempfile
    from pathlib import Path

    path = Path(tempfile.mkdtemp()) / "settings.json"
    picked = forge.save_hub_settings(
        {
            "text_scale": 1.2,
            "wallpaper": "/etc/passwd",
            "size_presets": [{"name": "Mine", "text_scale": 1.3}],
        },
        path,
    )
    assert set(picked) == {"text_scale", "size_presets"}
    stored = json.loads(path.read_text())
    assert stored["text_scale"] == 1.2 and stored.get("wallpaper", "") == ""
    assert stored["size_presets"][0]["name"] == "Mine"


def test_your_presets_are_marked_as_yours():
    listed = forge_theme.size_presets(
        {"size_presets": [{"name": "Mine", "text_scale": 1.3}]}
    )
    assert listed[-1]["mine"] is True and not any(p.get("mine") for p in listed[:5])


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except (AssertionError, AttributeError, KeyError) as exc:
                failed += 1
                print(f"FAIL {name}: {exc!r}")
    sys.exit(1 if failed else 0)
