"""Power modes are JSON files in modes/; this loads them and hands one to the root helper."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Callable

import display

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "helper"))

import forge_power  # noqa: E402

MODES_DIR = os.path.join(ROOT, "modes")
HELPER = "/usr/local/bin/forge-power"
REQUIRED = ("name", "label", "order", "settings")

HelperRunner = Callable[[list[str], str], dict]
RefreshSetter = Callable[[int], object]


class HelperError(RuntimeError):
    pass


def _check_display(block: object) -> None:
    if block is None:
        return
    if not isinstance(block, dict) or set(block) != {"refresh_hz"}:
        raise ValueError('display must be {"refresh_hz": <whole number>}')
    hz = block["refresh_hz"]
    if type(hz) is not int or not 30 <= hz <= 240:
        raise ValueError("display.refresh_hz must be a whole number from 30 to 240")


def _check_background(block: object) -> None:
    if block is None:
        return
    if (
        not isinstance(block, dict)
        or not set(block) <= {"nice", "efficiency_cores_only"}
        or type(block.get("nice")) is not int
        or not 1 <= block["nice"] <= 19
        or type(block.get("efficiency_cores_only", False)) is not bool
    ):
        raise ValueError(
            'background_tasks must be {"nice": 1-19, "efficiency_cores_only": true/false}'
        )


def load_modes(directory: str = MODES_DIR) -> list[dict]:
    modes = []
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(directory, filename), encoding="utf-8") as handle:
                data = json.load(handle)
            missing = [key for key in REQUIRED if key not in data]
            if missing:
                raise ValueError(f"missing {', '.join(missing)}")
            forge_power.validate(data["settings"])
            _check_display(data.get("display"))
            _check_background(data.get("background_tasks"))
        except ValueError as exc:
            raise ValueError(f"{filename}: {exc}") from exc
        modes.append(data)
    modes.sort(key=lambda m: (m["order"], m["name"]))
    return modes


def run_helper(argv: list[str], stdin_text: str) -> dict:
    proc = subprocess.run(
        argv, input=stdin_text, capture_output=True, text=True, timeout=120
    )
    if proc.returncode != 0:
        raise HelperError(proc.stderr.strip() or f"helper exited {proc.returncode}")
    return json.loads(proc.stdout)


def apply_mode(
    name: str,
    run: HelperRunner = run_helper,
    set_refresh: RefreshSetter = display.set_refresh,
) -> dict:
    by_name = {m["name"]: m for m in load_modes()}
    if name not in by_name:
        raise KeyError(name)
    mode = by_name[name]
    argv = ["sudo", "-n", HELPER, "apply", "--mode", name]
    result = run(argv, json.dumps(mode["settings"]))
    if mode.get("display"):
        result["display"] = set_refresh(mode["display"]["refresh_hz"])
    return result


def measure_watts(seconds: int = 2, run: HelperRunner = run_helper) -> dict:
    return run(["sudo", "-n", HELPER, "measure", "--seconds", str(seconds)], "")


def current_mode() -> str | None:
    try:
        with open(forge_power.STATE_FILE, encoding="utf-8") as handle:
            return json.load(handle).get("mode")
    except (OSError, ValueError):
        return None


def helper_installed() -> bool:
    return os.path.isfile(HELPER)
