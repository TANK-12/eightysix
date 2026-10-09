"""Background watcher: applies the auto-switch mode when the charger is plugged in or pulled out.

Runs as the user service forge-power-watch.service, so it works with Forge closed. It reads
one sysfs file every few seconds and does nothing while auto-switch is off.
"""

from __future__ import annotations

import sys
import time

import autoswitch
import modes

POLL_SECONDS = 5


def main() -> int:
    last_source: str | None = None
    while True:
        cfg = autoswitch.load_config()
        plugged = autoswitch.on_ac()
        target = autoswitch.decide(cfg, plugged, last_source)
        if not cfg["enabled"]:
            last_source = None
        elif target is not None:
            last_source = "ac" if plugged else "battery"
            try:
                result = modes.apply_mode(target)
                print(f"applied {target} ({last_source}): {result.get('display', '')}")
            except (modes.HelperError, KeyError, ValueError) as exc:
                print(f"could not apply {target}: {exc}", file=sys.stderr)
            sys.stdout.flush()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
