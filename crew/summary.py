#!/usr/bin/env python3
"""What the crew are doing, read off the board.

Emerson asked for a live manifest of what each agent is up to, refreshed every
few minutes. Each worker owns one file in this directory and rewrites it; this
just reads whatever is there, so a worker that dies leaves its last state
behind rather than a gap, and a new worker needs no registration.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MARKS = {"working": "•", "done": "✓", "blocked": "!", "stopped": "×"}


def rows():
    out = []
    for name in sorted(os.listdir(HERE)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(HERE, name), encoding="utf-8") as handle:
                out.append(json.load(handle))
        except (OSError, ValueError) as exc:
            out.append({"agent": name, "status": "blocked", "doing": f"unreadable: {exc}"})
    return out


def show():
    now = time.time()
    entries = rows()
    if not entries:
        print("nobody on the board yet")
        return
    print(f"crew board — {time.strftime('%H:%M:%S')}")
    for entry in entries:
        age = now - float(entry.get("updated") or 0)
        stale = "" if age < 300 else f"  (last said something {int(age // 60)} min ago)"
        print(
            f"  {MARKS.get(entry.get('status'), '?')} {entry.get('agent', '?'):<22}"
            f" {entry.get('model', ''):<7} {entry.get('doing', '')}{stale}"
        )
        for finished in entry.get("done", [])[-3:]:
            print(f"      ✓ {finished}")


if __name__ == "__main__":
    if "--watch" in sys.argv:
        try:
            while True:
                os.system("clear")
                show()
                time.sleep(20)
        except KeyboardInterrupt:
            pass
    else:
        show()
