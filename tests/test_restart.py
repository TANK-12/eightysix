"""Restart Forge from a key (Emerson, 2026-09-27: "give a key bind for
restarting forge"), and the Claude app starting at launch so conversations a
restart cut off carry on (apps/claude/tests/test_resume_after_restart.py).

    apps/dossier/.venv/bin/python -m pytest tests/test_restart.py
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "shared"))

import forge  # noqa: E402
import forge_theme  # noqa: E402
from gi.repository import Gdk  # noqa: E402

CTRL = Gdk.ModifierType.CONTROL_MASK
SHIFT = Gdk.ModifierType.SHIFT_MASK


def test_ctrl_shift_r_restarts_and_settings_can_name_it():
    table = forge.key_table()
    assert forge.key_action(Gdk.keyval_from_name("R"), CTRL | SHIFT, table) == "restart"
    assert forge_theme.HUB_KEY_LABELS["restart"] == "Restart Forge"
    moved = forge.key_table({"restart": "Ctrl+Alt+R"})
    alt = Gdk.ModifierType.MOD1_MASK
    assert forge.key_action(Gdk.keyval_from_name("r"), CTRL | alt, moved) == "restart"


def test_no_two_default_keys_clash():
    seen: dict = {}
    for action, text in forge_theme.HUB_KEYS.items():
        for part in text.split(","):
            parsed = forge.parse_key(part.strip())
            assert parsed is not None, (action, part)
            assert parsed not in seen, (action, seen.get(parsed))
            seen[parsed] = action


def test_a_restart_runs_the_same_script_on_screen():
    argv = forge.restart_argv("/usr/bin/python3", ["forge.py", "--background"])
    assert argv == ["/usr/bin/python3", os.path.abspath("forge.py")]


def backend(name, start_at_launch=False):
    return SimpleNamespace(name=name, start_at_launch=start_at_launch)


def test_on_demand_only_apps_that_ask_start_at_launch():
    apps = [backend("claude", True), backend("notes"), backend("old", True)]
    lazy = forge.launch_now(apps, lazy=True, archived={"old"})
    assert [b.name for b in lazy] == ["claude"]
    eager = forge.launch_now(apps, lazy=False, archived={"old"})
    assert [b.name for b in eager] == ["claude", "notes"]


def test_the_claude_app_asks_to_start_at_launch():
    manifest = json.loads((ROOT / "apps/claude/forge_app.json").read_text())
    assert manifest["start_at_launch"] is True
