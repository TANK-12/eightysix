import json

"""The wider settings table and the wallpaper-tinted app colours.

`surfaces()` decides the panel, border and text colours every app is drawn
with. The contrast tests are the point: a tint that looks good but leaves text
unreadable on one wallpaper is a regression, so every mode is checked against
several very different accents.
"""

import forge_theme as ft

ACCENTS = ["#e07a3a", "#3a7ae0", "#40c070", "#c040c0", "#f0e060", "#6ea8fe"]


def _luminance(colour):
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_every_setting_has_a_label_and_a_group_unless_it_has_its_own_card():
    for key, spec in ft.SETTINGS.items():
        assert spec.get("custom") or (spec.get("label") and spec.get("group")), key
        if spec["kind"] == "choice":
            assert set(spec.get("labels", {})) == set(spec["choices"]), key


def test_the_new_settings_are_kept_in_bounds(tmp_path):
    saved = ft.save(
        {
            "ui_scale": 9,
            "auto_fullscreen": "sometimes",
            "dock_size": 5,
            "tint": -1,
            "start_fullscreen": 0,
        },
        tmp_path / "s.json",
    )
    assert saved["ui_scale"] == ft.SETTINGS["ui_scale"]["max"]
    assert saved["auto_fullscreen"] == ft.SETTINGS["auto_fullscreen"]["default"]
    assert saved["dock_size"] == ft.SETTINGS["dock_size"]["min"]
    assert saved["tint"] == 0.0
    assert saved["start_fullscreen"] is False


def test_the_defaults_are_what_the_user_asked_for():
    assert ft.SETTINGS["theme_source"]["default"] == "wallpaper"
    assert ft.SETTINGS["start_fullscreen"]["default"] is True
    assert ft.SETTINGS["auto_fullscreen"]["default"] == "smart"
    assert ft.SETTINGS["reveal_bar"]["default"] is True
    # Only the top bar by default; the dock shows at the bottom edge.
    assert ft.SETTINGS["dock"]["default"] == "hidden"
    # Apps start when first opened, for a faster, lighter launch.
    assert ft.SETTINGS["start_apps"]["default"] == "demand"


def test_wallpaper_mode_tints_the_panels_towards_the_accent_hue():
    accent = "#e07a3a"
    hue = ft._hls(accent)[0]
    tinted = ft.surfaces(accent, 0.8, "wallpaper", "normal")
    for key in ("bg", "panel", "panel_2", "border"):
        h, _lightness, s = ft._hls(tinted[key])
        assert abs(h - hue) < 0.03 and s > 0.1, (key, tinted[key])


def test_more_tint_means_more_colour():
    weak = ft.surfaces("#3a7ae0", 0.2, "wallpaper", "normal")
    strong = ft.surfaces("#3a7ae0", 1.0, "wallpaper", "normal")
    assert ft._hls(strong["panel"])[2] > ft._hls(weak["panel"])[2]


def test_neutral_mode_is_the_classic_palette():
    assert ft.surfaces("#e07a3a", 1.0, "neutral", "normal") == ft.NEUTRAL_SURFACES
    assert ft.NEUTRAL_SURFACES["panel"] == "#171a21"


def test_text_stays_readable_on_every_panel_in_every_mode():
    for mode in ("wallpaper", "neutral"):
        for level in ("normal", "high"):
            for tint in (0.0, 0.5, 1.0):
                for accent in ACCENTS:
                    s = ft.surfaces(accent, tint, mode, level)
                    for panel in ("bg", "panel", "panel_2"):
                        where = (mode, level, tint, accent, panel)
                        assert contrast(s["text"], s[panel]) >= 7, where
                        assert contrast(s["muted"], s[panel]) >= 4.5, where


def test_high_contrast_brightens_the_quiet_text_and_the_borders():
    normal = ft.surfaces("#40c070", 0.5, "wallpaper", "normal")
    high = ft.surfaces("#40c070", 0.5, "wallpaper", "high")
    assert contrast(high["muted"], high["panel"]) > contrast(
        normal["muted"], normal["panel"]
    )
    assert contrast(high["border"], high["panel"]) > contrast(
        normal["border"], normal["panel"]
    )


def test_the_theme_carries_every_setting_and_the_surfaces(tmp_path, monkeypatch):
    monkeypatch.setattr(ft, "WALLPAPER_DIR", tmp_path / "none")
    monkeypatch.setattr(ft, "DESKTOP_WALLPAPER", tmp_path / "none.txt")
    settings = dict(ft.load(tmp_path / "s.json"), theme_source="neutral")
    data = ft.theme(settings)
    for key, spec in ft.SETTINGS.items():
        if not spec.get("custom"):
            assert data[key] == settings[key], key
    assert data["surfaces"] == ft.NEUTRAL_SURFACES


def test_music_tracks_come_from_the_folder_only_when_music_is_on(tmp_path):
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.flac").write_bytes(b"x")
    tracks = ft.music_tracks(str(tmp_path))
    assert [t["name"] for t in tracks] == ["a", "c"]
    assert tracks[0]["url"].startswith("file://")
    assert ft.music_tracks(str(tmp_path / "missing")) == []
    assert ft.music_tracks("") == []

    settings = {k: spec["default"] for k, spec in ft.SETTINGS.items()}
    settings["music_folder"] = str(tmp_path)
    assert ft.theme(settings)["music_tracks"] == []
    settings["music"] = True
    assert len(ft.theme(settings)["music_tracks"]) == 2


def test_particles_and_music_settings_are_cleaned():
    assert ft._clean("particles", "wild") == "soft"
    assert ft._clean("particles", "lively") == "lively"
    assert ft._clean("music_volume", 250) == 200  # boost goes to 200% (A27)
    assert ft._clean("music_volume", 150) == 150
    assert ft._clean("music_folder", None) == ""


def test_saving_one_key_keeps_the_rest_of_the_file_as_stored(tmp_path):
    # S12 (2026-09-27): changing the wallpaper sometimes turned particles off.
    # Each app backend has its own copy of forge_theme from when it started;
    # save() rewrote the whole file from that copy, so an older copy reset or
    # dropped settings it did not know. Now only the changed keys are written.
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {"particles": "a-kind-from-later", "particle_amount": 2.5, "zz_new": 1}
        )
    )
    ft.save({"wallpaper": "x.jpg"}, path)
    stored = json.loads(path.read_text())
    assert stored["particles"] == "a-kind-from-later"
    assert stored["particle_amount"] == 2.5
    assert stored["zz_new"] == 1
    assert stored["wallpaper"] == "x.jpg"
