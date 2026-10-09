"""Glass kinds (S26): every stylesheet in shared/glass/ is a real, self-contained kind.

WHY THIS EXISTS
    A glass kind is one CSS file found by scanning (forge_theme.list_glass),
    loaded by shared/forge_glass.js with a body class, glass-<id>. As with
    the looks, a file without its `/* glass: Label | about */` header never
    reaches Settings, and a rule not scoped under body.glass-<id> would leak
    into Flat and the other kind. Both are checked for any kind by scanning.

HOW TO RUN
    python3 -m pytest tests/test_hub_glass.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import forge_theme  # noqa: E402
from test_hub_looks import selectors  # noqa: E402

GLASS = os.path.join(ROOT, "shared", "glass")


def kinds():
    return sorted(f[:-4] for f in os.listdir(GLASS) if f.endswith(".css"))


def test_every_file_is_listed_with_flat_first():
    found = forge_theme.list_glass()
    assert list(found)[0] == "flat"
    assert set(kinds()) <= set(found), "a glass file lacks its /* glass: ... */ header"
    assert {"frosted", "liquid"} <= set(found)


def test_every_rule_is_scoped_to_its_own_kind():
    for kind in kinds():
        with open(os.path.join(GLASS, kind + ".css"), encoding="utf-8") as f:
            css = f.read()
        for sel in selectors(css):
            assert sel.startswith(f"body.glass-{kind}"), f"{kind}.css: {sel!r} leaks"


def test_the_setting_offers_every_kind_and_a_strength():
    spec = forge_theme.SETTINGS["glass_style"]
    assert spec["default"] == "flat"
    assert spec["choices"] == list(forge_theme.list_glass())
    strength = forge_theme.SETTINGS["glass_strength"]
    assert (
        strength["kind"] == "number" and strength["min"] == 0 and strength["max"] == 1
    )


def test_a_new_file_becomes_a_kind(tmp_path):
    (tmp_path / "ice.css").write_text(
        "/* glass: Ice | cold and clear */\nbody.glass-ice .tile {}\n"
    )
    (tmp_path / "junk.css").write_text("/* not a glass */\n")
    found = forge_theme.list_glass(tmp_path)
    assert found["ice"] == {"label": "Ice", "about": "cold and clear"}
    assert "junk" not in found


def test_the_visuals_popup_has_the_glass():
    assert {"glass_style", "glass_strength"} <= set(forge_theme.VISUALS_POPUP)
