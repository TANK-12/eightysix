"""Background watcher: keeps background-marked processes deprioritized.

Runs as the user service forge-power-priority.service, so it works with
Forge closed. Lowering your own process's niceness needs no root. It reads
the config fresh every cycle so edits from the Power tab apply without a
restart.
"""

from __future__ import annotations

import sys
import time

import modes
import priority

POLL_SECONDS = 5


def current_squeeze() -> dict | None:
    """The active mode's background_tasks block (saver pins to efficiency cores)."""
    name = modes.current_mode()
    try:
        by_name = {m["name"]: m for m in modes.load_modes()}
    except (OSError, ValueError):
        return None
    return priority.squeeze_for(by_name[name]) if name in by_name else None


def main() -> int:
    pinned: set[int] = set()
    while True:
        cfg = priority.load_config()
        squeeze = current_squeeze()
        entries = priority.plan(cfg, priority.all_processes(), squeeze)
        if squeeze and "cpus" in squeeze:
            pinned |= {e["pid"] for e in entries}
        elif pinned:
            priority.unpin(pinned)
            pinned = set()
        for result in priority.apply(entries):
            if not result["ok"]:
                print(
                    f"could not renice {result['name']} ({result['pid']}): "
                    f"{result['error']}",
                    file=sys.stderr,
                )
        sys.stdout.flush()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
