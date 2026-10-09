import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import pytest  # noqa: E402

import web_app  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    theme = web_app.forge_theme
    monkeypatch.setattr(theme, "CONFIG", tmp_path / "settings.json")
    monkeypatch.setattr(web_app, "HUB_DIR", tmp_path / "hub")
    # the real theme renders the wallpaper; only the setting matters here
    monkeypatch.setattr(
        theme,
        "theme",
        lambda s=None: {k: (s or {})[k] for k in ("max_fps", "battery_fps")},
    )
    return web_app, tmp_path


def test_frame_rate_cap_defaults_to_no_cap(client):
    c, _ = client
    assert c.get_fps() == {"max_fps": 60, "battery_fps": 30, "min": 1, "max": 60}


def test_setting_the_cap_saves_it_and_rewrites_theme_js(client):
    c, tmp = client
    r = c.set_fps(c.FpsBody(max_fps=24))
    assert r["max_fps"] == 24 and r["theme"] == {"max_fps": 24, "battery_fps": 30}
    assert c.get_fps()["max_fps"] == 24
    assert '"max_fps": 24' in (tmp / "hub" / "theme.js").read_text()


def test_out_of_range_caps_are_clamped(client):
    c, _ = client
    assert c.set_fps(c.FpsBody(max_fps=0))["max_fps"] == 1
    assert c.set_fps(c.FpsBody(max_fps=500))["max_fps"] == 60


def test_the_battery_cap_saves_alone_and_leaves_the_other(client):
    c, tmp = client
    c.set_fps(c.FpsBody(max_fps=50))
    r = c.set_fps(c.FpsBody(battery_fps=12))
    assert r["battery_fps"] == 12 and r["max_fps"] == 50
    assert c.get_fps()["battery_fps"] == 12
    assert '"battery_fps": 12' in (tmp / "hub" / "theme.js").read_text()
    assert c.set_fps(c.FpsBody(battery_fps=0))["battery_fps"] == 1
