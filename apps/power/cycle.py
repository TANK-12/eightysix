"""Step to the next power mode and say so in a notification; bound to a Hyprland hotkey."""

from __future__ import annotations

import subprocess
import sys

import modes


def next_mode(names: list[str], current: str | None) -> str:
    if current in names:
        return names[(names.index(current) + 1) % len(names)]
    return names[0]


def _notify(title: str, body: str) -> None:
    subprocess.run(
        ["notify-send", "-a", "Forge Power", "-t", "2500", title, body],
        capture_output=True,
        timeout=10,
    )


def main() -> int:
    loaded = modes.load_modes()
    target = next_mode([m["name"] for m in loaded], modes.current_mode())
    label = next(m["label"] for m in loaded if m["name"] == target)
    try:
        result = modes.apply_mode(target)
    except modes.HelperError as exc:
        _notify("Power mode not changed", str(exc))
        return 1
    failed = [r["setting"] for r in result.get("results", []) if not r["ok"]]
    _notify(
        f"{label} mode",
        f"{len(failed)} setting(s) could not be applied" if failed else "Applied",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
