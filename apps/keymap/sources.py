"""Scope registry for the keybind sources.

Reads ~/.config/hypr/hyprland/shells.lua -- the user's own declarative shell
registry -- at request time, so a shell added there later (a fourth entry
with its own `keybinds` file) shows up here automatically with no code
change. This mirrors the "registries over hardcoded lists" convention the
rest of this machine's config already follows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

HYPR_DIR = Path.home() / ".config" / "hypr"
SHELLS_LUA = HYPR_DIR / "hyprland" / "shells.lua"
VARIABLES_LUA = HYPR_DIR / "variables.lua"  # Caelestia's kb* values live here

UNIVERSAL_FILES = [
    HYPR_DIR / "hyprland" / "keybinds.lua",
    HYPR_DIR / "custom" / "keybinds.lua",
]

_SHELL_ENTRY = re.compile(
    r"(\w+)\s*=\s*\{\s*"
    r'name\s*=\s*"([^"]+)"'
    r".*?"
    r'keybinds\s*=\s*(nil|HOME\s*\.\.\s*"([^"]+)")',
    re.DOTALL,
)


@dataclass
class Scope:
    key: str  # "universal", or the shell's registry key (e.g. "caelestia")
    label: str
    files: list[Path]


def load_scopes() -> list[Scope]:
    scopes = [
        Scope(
            key="universal", label="Universal (all shells)", files=list(UNIVERSAL_FILES)
        )
    ]

    text = SHELLS_LUA.read_text(encoding="utf-8")
    for m in _SHELL_ENTRY.finditer(text):
        key, label, _, keybinds_path = m.groups()
        files: list[Path] = []
        if keybinds_path:
            # The Lua source is `HOME .. "/rest/of/path"` -- HOME isn't captured
            # since it's not a string literal, so re-prepend the real home dir.
            files.append(Path(f"{Path.home()}{keybinds_path}"))
        scopes.append(Scope(key=key, label=label, files=files))

    return scopes


def scopes_for_file(file: Path, scopes: list[Scope]) -> list[str]:
    return [s.label for s in scopes if file in s.files]
