"""shared/forge_wallpapers.py: the index, look-alike copies and favourites.

No network. ImageMagick is used for real where a test needs it, to prove the
fingerprint actually matches a resized copy and not just a hand-made hash.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

import forge_theme
import forge_wallpapers as fw

needs_magick = pytest.mark.skipif(
    not shutil.which("magick"), reason="ImageMagick not installed"
)


@pytest.fixture
def home(tmp_path, monkeypatch):
    folder = tmp_path / "Wallpapers"
    folder.mkdir()
    monkeypatch.setattr(forge_theme, "WALLPAPER_DIR", folder)
    monkeypatch.setattr(forge_theme, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(forge_theme, "CONFIG", tmp_path / "config" / "settings.json")
    return folder


def row(name, width, height, hash_hex, size=100):
    return {
        "name": name,
        "width": width,
        "height": height,
        "hash": hash_hex,
        "bytes": size,
        "mtime": 0,
    }


H0 = "0" * 64
H_NEAR = "7" + "0" * 63  # 3 bits away from H0
H_FAR = "f" * 64


# --- fingerprints -------------------------------------------------------------


def test_the_hash_says_which_neighbour_is_brighter():
    rising = bytes(x for _y in range(16) for x in range(17))  # every step brighter
    falling = bytes(16 - x for _y in range(16) for x in range(17))
    assert fw.hash_bits(rising) == 0
    assert fw.hash_bits(falling) == (1 << 256) - 1
    assert fw.distance(f"{0:064x}", f"{7:064x}") == 3


def test_a_short_image_is_not_hashed():
    with pytest.raises(ValueError):
        fw.hash_bits(b"\x00" * 10)


# --- the index ------------------------------------------------------------------


def test_sub_folders_are_indexed_and_hidden_folders_are_not(home):
    (home / "top.jpg").write_bytes(b"x")
    (home / "anime").mkdir()
    (home / "anime" / "deep.png").write_bytes(b"x")
    (home / ".git").mkdir()
    (home / ".git" / "object.jpg").write_bytes(b"x")
    names = [w["name"] for w in forge_theme.list_wallpapers(home)]
    assert names == ["anime/deep.png", "top.jpg"]
    assert forge_theme.wallpaper_path("anime/deep.png", home) == home / "anime/deep.png"
    assert forge_theme.wallpaper_path(".git/object.jpg", home) is None


def test_each_picture_is_read_once_until_it_changes(home):
    (home / "a.jpg").write_bytes(b"one")
    (home / "b.jpg").write_bytes(b"two")
    read = []

    def fake_probe(source):
        read.append(source.name)
        return {"width": 10, "height": 5, "hash": H0}

    fw.build_index(probe_fn=fake_probe)
    assert sorted(read) == ["a.jpg", "b.jpg"]

    read.clear()
    rows = fw.build_index(probe_fn=fake_probe)
    assert read == [] and rows[0]["width"] == 10

    (home / "b.jpg").write_bytes(b"changed and longer")
    (home / "c.jpg").write_bytes(b"new")
    fw.build_index(probe_fn=fake_probe)
    assert sorted(read) == ["b.jpg", "c.jpg"]


def test_the_cached_index_reads_nothing_and_counts_what_is_left(home):
    (home / "a.jpg").write_bytes(b"one")
    rows, stale = fw.cached_index()
    assert stale == 1 and rows[0]["width"] == 0
    fw.build_index(probe_fn=lambda s: {"width": 4, "height": 3, "hash": H0})
    rows, stale = fw.cached_index()
    assert stale == 0 and rows[0]["width"] == 4


def test_a_deleted_picture_leaves_the_index(home):
    (home / "a.jpg").write_bytes(b"one")
    (home / "b.jpg").write_bytes(b"two")
    fw.build_index(probe_fn=lambda s: {"width": 4, "height": 3, "hash": H0})
    (home / "a.jpg").unlink()
    rows = fw.build_index(probe_fn=lambda s: pytest.fail("nothing new to read"))
    assert [r["name"] for r in rows] == ["b.jpg"]


def test_progress_is_reported_for_every_picture(home):
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        (home / name).write_bytes(b"x")
    seen = []
    fw.build_index(
        probe_fn=lambda s: None, progress=lambda done, total: seen.append((done, total))
    )
    assert seen == [(1, 3), (2, 3), (3, 3)]


# --- look-alike copies ------------------------------------------------------------


def test_the_highest_resolution_copy_is_the_one_shown():
    rows = fw.mark_duplicates(
        [
            row("small.png", 1672, 941, H0),
            row("big.png", 3344, 1882, H_NEAR),
            row("other.jpg", 3840, 2160, H_FAR),
        ]
    )
    by = {r["name"]: r["duplicate_of"] for r in rows}
    assert by == {"small.png": "big.png", "big.png": None, "other.jpg": None}


def test_same_size_copies_keep_the_bigger_file():
    rows = fw.mark_duplicates(
        [row("room.jpg", 3360, 1440, H0, 900), row("room.png", 3360, 1440, H0, 5000)]
    )
    assert [r["duplicate_of"] for r in rows] == ["room.png", None]


def test_a_different_shape_is_never_a_copy():
    rows = fw.mark_duplicates(
        [row("wide.jpg", 3840, 2160, H0), row("tall.jpg", 2160, 3840, H0)]
    )
    assert [r["duplicate_of"] for r in rows] == [None, None]


def test_unread_pictures_are_always_shown():
    rows = fw.mark_duplicates([row("a.jpg", 0, 0, ""), row("b.jpg", 0, 0, "")])
    assert [r["duplicate_of"] for r in rows] == [None, None]


def test_three_copies_collapse_onto_one():
    rows = fw.mark_duplicates(
        [
            row("a.jpg", 1920, 1080, H0),
            row("b.jpg", 3840, 2160, H_NEAR),
            row("c.jpg", 2560, 1440, H0),
        ]
    )
    assert [r["duplicate_of"] for r in rows] == ["b.jpg", None, "b.jpg"]


@needs_magick
def test_a_real_upscaled_copy_is_found_and_a_different_picture_is_not(home):
    original = home / "orig.png"
    subprocess.run(
        ["magick", "-size", "320x180", "plasma:fractal", "-seed", "4", str(original)],
        check=True,
    )
    subprocess.run(
        ["magick", str(original), "-resize", "640x360!", str(home / "orig-2x.jpg")],
        check=True,
    )
    subprocess.run(
        ["magick", "-size", "320x180", "gradient:red-blue", str(home / "other.png")],
        check=True,
    )
    rows = {r["name"]: r for r in fw.catalogue(fw.build_index())}
    assert rows["orig-2x.jpg"]["width"] == 640
    assert rows["orig.png"]["duplicate_of"] == "orig-2x.jpg"
    assert rows["orig-2x.jpg"]["duplicate_of"] is None
    assert rows["other.png"]["duplicate_of"] is None


# --- favourites and setting one -----------------------------------------------------


def test_favourites_are_kept_beside_the_settings(home):
    assert fw.favourites() == []
    fw.set_favourite("a.jpg", True)
    fw.set_favourite("b.jpg", True)
    fw.set_favourite("a.jpg", False)
    assert fw.favourites() == ["b.jpg"]
    assert fw.favourites_path().parent == forge_theme.CONFIG.parent
    rows = fw.catalogue([row("a.jpg", 1, 1, ""), row("b.jpg", 1, 1, "")])
    assert [r["favourite"] for r in rows] == [False, True]


def test_the_desktop_uses_the_first_tool_installed(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "Hyprland")
    monkeypatch.setattr(fw.shutil, "which", lambda name: name == "swww" or None)
    ran = []
    ok, message = fw.set_desktop(
        Path("/pics/sea.jpg"), runner=lambda cmd, **kw: ran.append(cmd)
    )
    assert ok and ran == [["swww", "img", "/pics/sea.jpg"]] and "swww" in message


def test_no_desktop_tool_is_reported_not_raised(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "Hyprland")
    monkeypatch.setattr(fw.shutil, "which", lambda name: None)
    ok, message = fw.set_desktop(Path("/pics/sea.jpg"), runner=lambda *a, **k: None)
    assert not ok and "caelestia" in message


def test_on_gnome_the_desktop_is_set_with_gsettings_light_and_dark(monkeypatch):
    # S12 (2026-09-27): on GNOME "desktop" ran Hyprland's awww, which changes
    # nothing there, and said it worked. GNOME keeps a second key for dark mode.
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setattr(fw.shutil, "which", lambda name: True)
    ran = []
    ok, message = fw.set_desktop(
        Path("/pics/my sea.jpg"), runner=lambda cmd, **kw: ran.append(cmd)
    )
    uri = "file:///pics/my%20sea.jpg"
    assert ok and "gsettings" in message
    assert ran == [
        ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri],
        ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri],
    ]


def test_gnome_never_runs_a_hyprland_tool(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    monkeypatch.setattr(fw.shutil, "which", lambda name: name == "awww" or None)
    ran = []
    ok, _message = fw.set_desktop(
        Path("/pics/sea.jpg"), runner=lambda cmd, **kw: ran.append(cmd)
    )
    assert not ok and ran == []


def test_forge_follows_the_gnome_wallpaper(monkeypatch, tmp_path):
    # Forge's "follow my desktop wallpaper" read only caelestia's state file,
    # which GNOME never writes.
    pic = tmp_path / "night sky.jpg"
    pic.write_bytes(b"x")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    answers = {"color-scheme": "'prefer-dark'", "picture-uri-dark": f"'{pic.as_uri()}'"}
    got = forge_theme.desktop_wallpaper(
        tmp_path / "missing.txt", gsettings=lambda key: answers.get(key, "''")
    )
    assert got == pic
