"""On/off switches for the login autostart entries in ~/.config/autostart."""

from __future__ import annotations

import os

AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
HEADER = "[Desktop Entry]"


def _path(directory: str, filename: str) -> str:
    if os.path.basename(filename) != filename or not filename.endswith(".desktop"):
        raise ValueError(f"not an autostart file name: {filename!r}")
    return os.path.join(directory, filename)


def list_entries(directory: str = AUTOSTART_DIR) -> list[dict]:
    if not os.path.isdir(directory):
        return []
    rows = []
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".desktop"):
            continue
        with open(os.path.join(directory, filename), encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        name, enabled, section = filename, True, ""
        for line in lines:
            if line.startswith("["):
                section = line.strip()
            elif section != HEADER:
                continue
            elif line.startswith("Name=") and name == filename:
                name = line[5:]
            elif line.strip() in ("Hidden=true", "X-GNOME-Autostart-enabled=false"):
                enabled = False
        rows.append({"file": filename, "name": name, "enabled": enabled})
    return rows


def set_enabled(directory: str, filename: str, enabled: bool) -> None:
    path = _path(directory, filename)
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines(keepends=True)
    lines = [line for line in lines if not line.startswith("Hidden=")]
    if enabled:
        lines = [
            (
                "X-GNOME-Autostart-enabled=true\n"
                if line.strip() == "X-GNOME-Autostart-enabled=false"
                else line
            )
            for line in lines
        ]
    else:
        at = next((i for i, l in enumerate(lines) if l.strip() == HEADER), -1)
        lines.insert(at + 1, "Hidden=true\n")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("".join(lines))
