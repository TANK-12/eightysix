"""Particles on the normal desktop (B38): desktop/particles.py decides where
it may run and follows the setting through hub/theme.js."""

import importlib.util
import os
import sys
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORGE / "shared"))
spec = importlib.util.spec_from_file_location(
    "particles", FORGE / "desktop" / "particles.py"
)
assert spec and spec.loader
particles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(particles)

import forge_theme  # noqa: E402


def test_it_only_runs_where_it_can_sit_under_the_windows():
    assert (
        particles.host({"FORGE_DESKTOP_PARTICLES_HOST": "gnome-extension"})
        == "gnome-extension"
    )
    assert particles.host({"XDG_CURRENT_DESKTOP": "Hyprland"}) == "layer-shell"
    assert particles.host({"HYPRLAND_INSTANCE_SIGNATURE": "x"}) == "layer-shell"
    # plain GNOME without the extension: an ordinary window would float on top
    assert particles.host({"XDG_CURRENT_DESKTOP": "GNOME"}) is None
    assert particles.host({}) is None


def test_without_a_host_it_says_why_and_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(os, "environ", {"XDG_CURRENT_DESKTOP": "GNOME"})
    assert particles.main() == 2
    assert "extension" in capsys.readouterr().err


def test_it_reads_theme_js_and_follows_the_setting(tmp_path):
    js = tmp_path / "theme.js"
    js.write_text(
        'window.FORGE_THEME = {"desktop_particles": true, "particles": "snow"};\n'
    )
    theme = particles.read_theme(js)
    assert theme["particles"] == "snow" and particles.wanted(theme)
    js.write_text('window.FORGE_THEME = {"desktop_particles": false};\n')
    assert not particles.wanted(particles.read_theme(js))
    assert particles.read_theme(tmp_path / "missing.js") == {}


def test_the_setting_is_off_by_default_and_in_theme_js():
    entry = forge_theme.SETTINGS["desktop_particles"]
    assert entry["default"] is False and entry["kind"] == "bool"
    assert (
        forge_theme.theme(forge_theme.load(Path("/nonexistent/settings.json")))[
            "desktop_particles"
        ]
        is False
    )


def test_it_has_its_own_settings_page():
    """Emerson 2026-09-27: the desktop particles should have their own
    settings; every number is a slider."""
    fields = forge_theme.SETTINGS
    keys = (
        "desktop_particle_kind",
        "desktop_particle_amount",
        "desktop_particle_fps",
        "desktop_particles_rest",
    )
    for key in keys:
        assert fields[key]["group"] == forge_theme.DESKTOP_PARTICLES, key
    kind = fields["desktop_particle_kind"]
    assert kind["default"] == "same" and "snow" in kind["choices"]
    assert "off" not in kind["choices"]  # the on/off switch stays where it was
    for key in ("desktop_particle_amount", "desktop_particle_fps"):
        assert "min" in fields[key] and "max" in fields[key], key
    assert fields["desktop_particle_fps"]["max"] == 60
    assert fields["desktop_particles_rest"]["default"] is True
    assert fields["desktop_particles"]["group"] == forge_theme.HOME_SCREEN
    theme = forge_theme.theme(forge_theme.load(Path("/nonexistent/settings.json")))
    for key in keys:
        assert key in theme, key


def test_it_rests_only_while_covered_and_only_when_asked():
    assert particles.resting({}, covered=True)
    assert not particles.resting({}, covered=False)
    assert not particles.resting({"desktop_particles_rest": False}, covered=True)
    assert particles.resting({"desktop_particles_rest": True}, covered=True)


def test_on_battery_reads_the_mains_adapter(tmp_path):
    def supply(name, **files):
        (tmp_path / name).mkdir()
        for key, value in files.items():
            (tmp_path / name / key).write_text(value + "\n")

    assert particles.on_battery(tmp_path) is False, "no adapter: a desktop"
    supply("BAT0", type="Battery", status="Not charging")
    supply("AC", type="Mains", online="1")
    assert particles.on_battery(tmp_path) is False
    (tmp_path / "AC" / "online").write_text("0\n")
    assert particles.on_battery(tmp_path) is True


def test_read_under_takes_the_extensions_screens(tmp_path):
    f = tmp_path / "under.json"
    f.write_text('{"0": true, "1": false, "x": true}')
    assert particles.read_under(f) == {0: True, 1: False}
    assert particles.read_under(tmp_path / "missing.json") == {}
    f.write_text("[1, 2]")
    assert particles.read_under(f) == {}
