"""Home widgets and Relax (B20, 2026-09-27): settings, and the hub loads the
shared widget registry. The behaviour is checked in the browser by
tests/browser/hub_widgets_harness.js."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

import forge_theme  # noqa: E402


def test_widget_settings_and_their_defaults():
    s = forge_theme.SETTINGS
    assert (
        s["widgets"]["default"] is True and s["widgets"]["group"] == forge_theme.WIDGETS
    )
    assert s["widget_look"]["default"] == "material"
    assert set(s["widget_look"]["choices"]) == {"material", "glass"}
    assert s["widget_scale"]["min"] < 1 < s["widget_scale"]["max"]
    assert s["breath_seconds"]["default"] == 4


def test_every_widget_is_one_registry_entry():
    js = (ROOT / "shared" / "forge_widgets.js").read_text()
    kinds = re.findall(r'W\.define\("(\w+)"', js)
    # B20's five, then S25's (2026-09-28) planned ones
    assert kinds == [
        "clock",
        "nowplaying",
        "system",
        "notes",
        "breathe",
        "weather",
        "player",
        "calendar",
        "disk",
        "network",
        "jan",
        "alarms",
        "visualiser",
        # v2 (2026-10-07)
        "activity",
        "battery",
        "countdown",
        "worldclock",
        "focus",
        "todo",
        "moon",
    ]


def test_the_hub_loads_and_feeds_them():
    hub = (ROOT / "hub" / "index.html").read_text()
    assert '<script src="../shared/forge_widgets.js"' in hub
    assert 'id="widgets"' in hub and "ForgeWidgets.mount(" in hub
    assert hub.index('id="widgets"') < hub.index('id="tiles"')
