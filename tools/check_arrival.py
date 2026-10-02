#!/usr/bin/env python3
"""Did every Legion unit of a bot run reach the Juggernaut? (lane B5 part 4)

Reads <run folder>/report.json (a bot run that calls report_legion, such as tools/bot_run.sh b5_finale_long) and
prints, per unit slot, the closest it came to the player and how it ended. A unit has arrived when it got within
--within metres or was in the attack state at any report. A Löwe stands off and shoots (engage range up to 500 m)
and an Ameise scout keeps 150-250 m away, so those two count as arrived within STAND_OFF_M of the player.
Exit 0 when every unit arrived, 1 when one did not.

Usage: tools/check_arrival.py images/NNN-b5_finale_long [--within 100]
"""

import argparse
import json
import sys
from pathlib import Path

STAND_OFF_M = {"lowe": 520.0, "ameise": 260.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--within", type=float, default=100.0)
    args = ap.parse_args()
    report = json.loads((Path(args.folder) / "report.json").read_text())
    snaps = report.get("legion", [])
    if not snaps:
        print("no legion snapshots in the report")
        return 1
    slots: dict[int, list[dict]] = {}
    for snap in snaps:
        for i, unit in enumerate(snap["units"]):
            slots.setdefault(i, []).append(unit)
    ok = True
    for i, seen in sorted(slots.items()):
        kind = seen[0]["id"]
        closest = min(u["to_player_m"] for u in seen)
        fought = any(u["state"] == "attack" or u.get("shots", 0) > 0 for u in seen)
        limit = max(args.within, STAND_OFF_M.get(kind, 0.0))
        arrived = closest <= limit or fought
        ok = ok and arrived
        print(
            f"{kind:9s} slot {i}: closest {closest:5.0f} m, fought {fought}, {'arrived' if arrived else 'DID NOT ARRIVE'}"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
