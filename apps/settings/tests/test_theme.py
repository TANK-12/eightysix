"""shared/forge_theme.py: settings, wallpapers, colour and the hub's theme.js.

No network. ImageMagick is used for real where a test needs it (it is on this
machine for the desktop), and one test proves Forge still works without it.
"""

import json
import shutil
from pathlib import Path

import pytest

import forge_theme

HISTOGRAM = """          3890: (26.6,29.6,34.8) #1B1E23 srgb(10%,11%,13%)
           299: (55.9,71.8,90.1) #38485A srgb(21%,28%,35%)
           200: (96.8,116.1,138.4) #61748A srgb(37%,45%,54%)
           247: (144.3,160.4,178.3) #90A0B2 srgb(56%,62%,69%)
"""


# --- settings ---------------------------------------------------------------


def test_missing_settings_read_as_defaults(tmp_path):
    settings = forge_theme.load(tmp_path / "nope.json")
    assert settings == {k: s["default"] for k, s in forge_theme.SETTINGS.items()}


def test_saving_clamps_and_ignores_what_it_does_not_know(tmp_path):
    path = tmp_path / "settings.json"
    saved = forge_theme.save(
        {
            "glass": 5,
            "gaps": "wide",
            "open_on": "sideways",
            "accent": "red",
            "bogus": 1,
        },
        path,
    )
    assert saved["glass"] == 1.0
    assert saved["gaps"] == forge_theme.SETTINGS["gaps"]["default"]
    assert saved["open_on"] == "home"
    assert saved["accent"] == ""
    assert "bogus" not in json.loads(path.read_text())


def test_a_broken_settings_file_does_not_stop_forge(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ not json")
    assert forge_theme.load(path)["radius"] == forge_theme.SETTINGS["radius"]["default"]


# --- wallpapers ---------------------------------------------------------------


def _folder(tmp_path):
    folder = tmp_path / "Wallpapers"
    folder.mkdir()
    (folder / "b-mountain.jpg").write_bytes(b"x")
    (folder / "a-sea.PNG").write_bytes(b"x")
    (folder / "notes.txt").write_text("not a picture")
    return folder


def test_only_pictures_are_wallpapers(tmp_path):
    names = [w["name"] for w in forge_theme.list_wallpapers(_folder(tmp_path))]
    assert names == ["a-sea.PNG", "b-mountain.jpg"]


def test_a_wallpaper_name_cannot_reach_outside_the_folder(tmp_path):
    folder = _folder(tmp_path)
    (tmp_path / "secret.jpg").write_bytes(b"x")
    assert forge_theme.wallpaper_path("../secret.jpg", folder) is None
    assert forge_theme.wallpaper_path("notes.txt", folder) is None
    assert forge_theme.wallpaper_path("a-sea.PNG", folder) == folder / "a-sea.PNG"


def test_the_chosen_wallpaper_then_the_desktops_then_the_first(tmp_path, monkeypatch):
    folder = _folder(tmp_path)
    state = tmp_path / "path.txt"
    monkeypatch.setattr(forge_theme, "DESKTOP_WALLPAPER", state)
    # the state file is the Hyprland route; on GNOME the live gsettings answer
    # first (B37), which would make this test read the real desktop
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "Hyprland")

    chosen = forge_theme.chosen_wallpaper({"wallpaper": "b-mountain.jpg"}, folder)
    assert chosen == folder / "b-mountain.jpg"

    state.write_text(str(folder / "b-mountain.jpg"))
    desktop = forge_theme.chosen_wallpaper({"wallpaper": ""}, folder)
    assert desktop is not None and desktop.name == "b-mountain.jpg"

    state.write_text("/no/such/file.jpg")
    first = forge_theme.chosen_wallpaper({"wallpaper": ""}, folder)
    assert first is not None and first.name == "a-sea.PNG"


# --- colour ---------------------------------------------------------------------


def test_the_histogram_is_read_most_common_first():
    rows = forge_theme.parse_histogram(HISTOGRAM)
    assert rows[0] == (3890, "#1b1e23")
    assert [c for _n, c in rows] == ["#1b1e23", "#38485a", "#90a0b2", "#61748a"]


def test_the_accent_is_a_colour_not_the_darkest_grey():
    accent = forge_theme.pick_accent(["#1b1e23", "#38485a", "#61748a", "#90a0b2"])
    hue, lightness, saturation = forge_theme._hls(accent)
    assert abs(lightness - 0.68) < 0.01
    # Lifted to 0.45; the round trip through an 8-bit #rrggbb colour can shave
    # a fraction off that.
    assert saturation >= 0.44
    assert 0.55 < hue < 0.65  # the wallpaper's slate blue, not an invented hue


def test_a_grey_wallpaper_falls_back_instead_of_inventing_red():
    assert (
        forge_theme.pick_accent(["#202020", "#808080", "#c0c0c0"])
        == forge_theme.FALLBACK_ACCENT
    )
    assert forge_theme.swatches(["#202020", "#808080"]) == []


def test_text_on_the_accent_stays_readable():
    _darker, on_light = forge_theme._variants("#a8d8ff")
    _darker, on_dark = forge_theme._variants("#1f3a8a")
    assert on_light == "#0b1220" and on_dark == "#ffffff"


# --- rendering and the theme ------------------------------------------------------

needs_magick = pytest.mark.skipif(
    not shutil.which("magick"), reason="ImageMagick not installed"
)


@needs_magick
def test_a_wallpaper_is_rendered_once_and_reused(tmp_path, monkeypatch):
    import subprocess

    source = tmp_path / "blue.png"
    subprocess.run(
        ["magick", "-size", "320x180", "xc:#3366aa", str(source)], check=True
    )
    first = forge_theme.render(source, tmp_path / "cache")
    assert Path(first["image"]).is_file() and Path(first["blur"]).is_file()
    assert first["palette"]

    # A second render must not run ImageMagick at all.
    monkeypatch.setattr(forge_theme, "_run", lambda args: pytest.fail("re-rendered"))
    again = forge_theme.render(source, tmp_path / "cache")
    assert again["image"] == first["image"]


@needs_magick
def test_a_thumbnail_is_small_and_cached(tmp_path):
    import subprocess

    source = tmp_path / "wide.png"
    subprocess.run(
        ["magick", "-size", "1920x1080", "xc:#aa6633", str(source)], check=True
    )
    thumb = forge_theme.thumbnail(source, tmp_path / "cache")
    size = subprocess.run(
        ["magick", "identify", "-format", "%wx%h", str(thumb)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert size == "480x270"
    assert forge_theme.thumbnail(source, tmp_path / "cache") == thumb


def test_without_imagemagick_the_original_picture_is_used(tmp_path, monkeypatch):
    source = tmp_path / "pic.jpg"
    source.write_bytes(b"x")
    monkeypatch.setattr(forge_theme, "_magick", lambda: None)
    rendered = forge_theme.render(source, tmp_path / "cache")
    assert rendered["image"] == source and rendered["palette"] == []


def test_the_theme_reaches_the_hub_as_a_script_global(tmp_path, monkeypatch):
    folder = _folder(tmp_path)
    monkeypatch.setattr(forge_theme, "WALLPAPER_DIR", folder)
    monkeypatch.setattr(forge_theme, "DESKTOP_WALLPAPER", tmp_path / "none.txt")
    monkeypatch.setattr(
        forge_theme,
        "render",
        lambda source, cache=None: {
            "image": source,
            "blur": source,
            "palette": ["#1b1e23", "#38485a"],
        },
    )
    settings = dict(forge_theme.load(tmp_path / "s.json"), accent="#ff8800")
    data = forge_theme.theme(settings)
    assert data["accent"] == "#ff8800"
    assert data["wallpaper"].startswith("file://") and data["follows_desktop"]

    out = forge_theme.write_theme_js(tmp_path / "hub", data)
    text = out.read_text()
    assert text.startswith("window.FORGE_THEME = ") and text.rstrip().endswith(";")
    assert json.loads(text[len("window.FORGE_THEME = ") : -2]) == data


@needs_magick
def test_warming_makes_each_thumbnail_once_current_wallpaper_first(
    tmp_path, monkeypatch
):
    import subprocess

    folder = tmp_path / "Wallpapers"
    folder.mkdir()
    for name, colour in (("a.png", "#113355"), ("b.png", "#553311")):
        subprocess.run(
            ["magick", "-size", "640x360", f"xc:{colour}", str(folder / name)],
            check=True,
        )
    order = []
    real = forge_theme.thumbnail

    def recording(source, cache=None, background=False):
        assert background, "the warm-up must run niced, outside the interactive slots"
        order.append(source.name)
        return real(source, cache, background)

    monkeypatch.setattr(forge_theme, "thumbnail", recording)
    cache = tmp_path / "cache"
    assert forge_theme.warm_thumbnails(["b.png"], folder, cache) == 2
    assert order == ["b.png", "a.png"]
    assert forge_theme.warm_thumbnails(["b.png"], folder, cache) == 0
    assert len(list((cache / "thumbs").glob("*.jpg"))) == 2
    assert not list((cache / "thumbs").glob(".*")), "a temporary file was left behind"
