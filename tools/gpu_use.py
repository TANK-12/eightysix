"""GPU and CPU use per process, from the kernel's DRM fdinfo counters.

Every process holding a GPU file descriptor lists, in /proc/<pid>/fdinfo, how
many nanoseconds of each engine (render, video, copy...) its client has used.
Sampling twice and dividing by the wall time gives each process's share of the
engine, with no root and no intel_gpu_top PMU access. A client id can show up
on several descriptors of one process; it is counted once.

    python3 tools/gpu_use.py [seconds] [--json] [--all]

Prints the busiest processes first, render engine % and CPU %.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

CLK = os.sysconf("SC_CLK_TCK")


def engines(pid: int) -> dict[str, int]:
    """Nanoseconds per engine for one process, each client id counted once."""
    seen: dict[str, dict[str, int]] = {}
    try:
        fds = list(Path(f"/proc/{pid}/fdinfo").iterdir())
    except OSError:
        return {}
    for fd in fds:
        try:
            text = fd.read_text()
        except OSError:
            continue
        if "drm-client-id" not in text:
            continue
        client = ""
        eng: dict[str, int] = {}
        for line in text.splitlines():
            key, _, val = line.partition(":")
            if key == "drm-client-id":
                client = val.strip()
            elif key.startswith("drm-engine-") and not key.startswith(
                "drm-engine-capacity"
            ):
                eng[key[len("drm-engine-") :]] = int(val.split()[0])
        seen[client] = eng
    total: dict[str, int] = {}
    for eng in seen.values():
        for k, v in eng.items():
            total[k] = total.get(k, 0) + v
    return total


def cpu_ticks(pid: int) -> int:
    try:
        parts = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except OSError:
        return 0
    return int(parts[11]) + int(parts[12])


def label(pid: int) -> str:
    try:
        args = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
        return args.decode(errors="replace").strip()[:90]
    except OSError:
        return "?"


def snapshot() -> dict[int, tuple[dict[str, int], int]]:
    out = {}
    for p in Path("/proc").iterdir():
        if p.name.isdigit():
            pid = int(p.name)
            out[pid] = (engines(pid), cpu_ticks(pid))
    return out


def sample(seconds: float) -> list[dict]:
    a, t0 = snapshot(), time.monotonic()
    time.sleep(seconds)
    b, t1 = snapshot(), time.monotonic()
    wall = t1 - t0
    rows = []
    for pid, (eng, ticks) in b.items():
        if pid not in a:
            continue
        eng0, ticks0 = a[pid]
        busy = {
            k: 100 * (v - eng0.get(k, 0)) / (wall * 1e9)
            for k, v in eng.items()
            if v - eng0.get(k, 0) > 0
        }
        cpu = 100 * (ticks - ticks0) / CLK / wall
        if busy or cpu >= 1:
            rows.append(
                {
                    "pid": pid,
                    "render": round(busy.get("render", 0.0), 1),
                    "other_gpu": round(
                        sum(v for k, v in busy.items() if k != "render"), 1
                    ),
                    "cpu": round(cpu, 1),
                    "cmd": label(pid),
                }
            )
    rows.sort(key=lambda r: (r["render"], r["cpu"]), reverse=True)
    return rows


def main(argv: list[str]) -> None:
    secs = float(next((x for x in argv if not x.startswith("-")), 10))
    rows = sample(secs)
    if "--all" not in argv:
        rows = [r for r in rows if r["render"] > 0 or r["cpu"] >= 5]
    if "--json" in argv:
        print(json.dumps({"seconds": secs, "rows": rows}, indent=1))
        return
    print(f"over {secs:g} s: render %   other GPU %   CPU %   process")
    for r in rows:
        print(
            f"{r['render']:>16.1f} {r['other_gpu']:>13.1f} {r['cpu']:>7.1f}   "
            f"{r['pid']} {r['cmd']}"
        )
    print(f"{'total':>10} {sum(r['render'] for r in rows):>5.1f}")


if __name__ == "__main__":
    main(sys.argv[1:])
