"""S25 (2026-09-28): the effect keys, the visuals popup's table, the master
switches, and the shared visualiser styles."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

import forge_theme  # noqa: E402


def test_the_new_keys_and_their_defaults():
    k = forge_theme.HUB_KEYS
    assert k["effects"] == "Alt+E"
    assert k["particles-toggle"] == "Alt+P"
    assert k["visualiser-toggle"] == "Alt+M"
    assert k["visuals"] == "Alt+Shift+M"
    # no key is used twice
    seen = {}
    for action, text in k.items():
        for part in (p.strip().lower() for p in text.split(",")):
            assert part not in seen, (part, action, seen.get(part))
            seen[part] = action


def test_the_hub_handles_every_new_action():
    hub = (ROOT / "hub" / "index.html").read_text()
    for action in ("effects", "particles-toggle", "visualiser-toggle", "visuals"):
        assert f'action === "{action}"' in hub, action


def test_home_and_settings_keys():
    # Emerson (2026-09-29): "alt h goes to desktop and alt s goes to settings"
    k = forge_theme.HUB_KEYS
    assert k["home"] == "Alt+H"
    assert k["settings"] == "Alt+S"
    assert forge_theme.HUB_KEY_LABELS["home"] and forge_theme.HUB_KEY_LABELS["settings"]
    hub = (ROOT / "hub" / "index.html").read_text()
    for action in ("home", "settings"):
        assert f'action === "{action}"' in hub, action


def test_master_switches_keep_the_picked_style():
    s = forge_theme.SETTINGS
    assert s["particles_shown"]["default"] is True
    assert s["visualiser_shown"]["default"] is True
    assert s["visualiser_gain"]["min"] < 1 < s["visualiser_gain"]["max"]
    assert "rainbow" in s["visualiser_colours"]["choices"]


def test_the_popup_rows_come_from_the_table():
    rows = forge_theme.popup_rows(forge_theme.VISUALS_POPUP)
    assert [r["key"] for r in rows] == forge_theme.VISUALS_POPUP
    for r in rows:
        spec = forge_theme.SETTINGS[r["key"]]
        assert r["kind"] == spec["kind"] and r["default"] == spec["default"]
        if spec["kind"] == "choice":
            assert r["choices"] == spec["choices"]
    theme = forge_theme.theme(forge_theme.load(Path("/nonexistent/settings.json")))
    assert theme["visuals_popup"] == rows


def test_one_visualiser_table_for_every_picker():
    labels = forge_theme.VISUALISER_LABELS
    js = (ROOT / "shared" / "forge_visual.js").read_text()
    styles = re.findall(
        r"^    (\w+)\(c, w, h, v, size, accent, accent2, wave, st = \{\}\)", js, re.M
    )
    assert set(styles) == set(labels)
    for key in ("visualiser", "ambient_visualiser", "desktop_visualiser"):
        assert set(labels) <= set(forge_theme.SETTINGS[key]["choices"])
    assert "const TERRAIN_GAIN = 1.2;" in js
    hub = (ROOT / "hub" / "index.html").read_text()
    assert '<script src="../shared/forge_visual.js"></script>' in hub
    assert "STYLES: {" not in hub.split("const Visual = {")[1].split("anchor(w, h)")[0]
