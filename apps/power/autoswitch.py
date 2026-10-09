"""Pick a mode automatically when the charger is plugged in or pulled out."""

from __future__ import annotations

import json
import os

CONFIG_PATH = os.path.expanduser("~/.config/forge-power/auto.json")
AC_ONLINE = "/sys/class/power_supply/AC/online"
DEFAULT = {"enabled": False, "battery": "cool", "ac": "auto"}


def load_config(path: str = CONFIG_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return dict(DEFAULT)
    if (
        not isinstance(data, dict)
        or set(data) != set(DEFAULT)
        or type(data["enabled"]) is not bool
    ):
        return dict(DEFAULT)
    return data


def save_config(path: str, cfg: dict, mode_names: list[str]) -> None:
    if not isinstance(cfg, dict) or set(cfg) != set(DEFAULT):
        raise ValueError("auto-switch needs exactly: enabled, battery, ac")
    if type(cfg["enabled"]) is not bool:
        raise ValueError("enabled must be true or false")
    for key in ("battery", "ac"):
        if cfg[key] not in mode_names:
            raise ValueError(f"no mode called {cfg[key]!r}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle)
    os.replace(tmp, path)


def on_ac(path: str = AC_ONLINE) -> bool:
    try:
        with open(path, encoding="ascii") as handle:
            return handle.read().strip() == "1"
    except OSError:
        return False


def decide(cfg: dict, on_ac: bool, last_source: str | None) -> str | None:
    """The mode to apply now, or None when nothing should change."""
    if not cfg["enabled"]:
        return None
    source = "ac" if on_ac else "battery"
    if source == last_source:
        return None
    return cfg[source]
