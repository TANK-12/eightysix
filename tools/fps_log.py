#!/usr/bin/env python3
"""Log the game's frame rate for each graphics preset on a fixed bot route.

Refuses while a Blender job runs: renders share the GPU, and they are what made the old game's
numbers meaningless. For each preset it plays tools/bot/fps_route.json through tools/bot_run.sh
(off screen unless --visible) and writes logs/fps/<stamp>-<preset>.json in the shape the Forge
hub reads, plus the uncapped estimate.

Off screen the game presents in mailbox mode, so the headless compositor does not cap the frame
rate (paced_share, the share of frames at exactly the refresh interval, stays near 0). Should a
run be paced after all (paced_share >= 0.5), the record says so in vsync_cap_hz and
est_uncapped_fps (the slower of GPU and CPU time per frame) stands in for the capped average.
--visible measures on the desktop instead.

Usage: tools/fps_log.py [--presets low,medium,high,ultra] [--visible]
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FPS_DIR = ROOT / "logs" / "fps"
MAP_ID = "test_range"


def blender_running() -> bool:
    """True while any headless Blender job runs on this machine."""
    return (
        subprocess.run(["pgrep", "-f", "[b]lender -b"], capture_output=True).returncode
        == 0
    )


def presets() -> dict:
    """Preset id to its registry entry, in registry order."""
    data = json.loads((ROOT / "data" / "graphics_presets.json").read_text())
    return data["entries"]


def run_route(preset: str, visible: bool) -> Path | None:
    """Play the route once; return the run's image folder, or None if it failed."""
    cmd = [
        str(ROOT / "tools" / "bot_run.sh"),
        "fps_route",
        f"--preset={preset}",
        f"--name=fps-{preset}",
    ]
    if visible:
        cmd.append("--visible")
    done = subprocess.run(cmd, capture_output=True, text=True)
    lines = done.stdout.strip().splitlines()
    folder = Path(lines[-1]) if lines else None
    if folder is None or not (folder / "report.json").is_file():
        sys.stderr.write(done.stdout + done.stderr)
        return None
    return folder


def record_from(
    report: dict, preset: str, target: float | None, folder: Path, visible: bool
) -> dict:
    """The hub's fps record for one preset, from a bot report."""
    measure = next(
        (m for m in report.get("measures", []) if m.get("label") == "route"), {}
    )
    # Vsync only caps the average when it actually held frames to the refresh interval.
    capped = (
        bool(measure.get("vsync"))
        and not visible
        and measure.get("paced_share", 0) >= 0.5
    )
    estimate = measure.get("est_uncapped_fps")
    return {
        "when": report.get("finished", ""),
        "map": MAP_ID,
        "preset": preset,
        "target_fps": target,
        "avg_fps": measure.get("avg_fps"),
        "p1_low_fps": measure.get("p1_low_fps"),
        "min_fps": measure.get("min_fps"),
        "frame_ms_avg": measure.get("frame_ms_avg"),
        "seconds": measure.get("seconds"),
        "resolution": report.get("resolution"),
        "render_scale": report.get("render_scale"),
        "gpu": report.get("gpu", ""),
        "blender_running": False,
        "window": "on screen" if visible else "off screen",
        "vsync_cap_hz": measure.get("refresh_hz") if capped else None,
        "paced_share": measure.get("paced_share"),
        "est_uncapped_fps": estimate,
        "est_uncapped_p1_low_fps": measure.get("est_uncapped_p1_low_fps"),
        "gpu_ms_avg": measure.get("gpu_ms_avg"),
        "cpu_ms_avg": measure.get("cpu_ms_avg"),
        "bound_by": measure.get("bound_by"),
        "target_met_estimate": (
            None if target is None or estimate is None else estimate >= target
        ),
        "images": folder.name,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Log the frame rate per graphics preset on a fixed bot route."
    )
    parser.add_argument(
        "--presets", default="", help="comma list; default every preset"
    )
    parser.add_argument(
        "--visible", action="store_true", help="measure on the desktop, vsync off"
    )
    args = parser.parse_args()

    entries = presets()
    wanted = [p for p in args.presets.split(",") if p] or list(entries)
    unknown = [p for p in wanted if p not in entries]
    if unknown:
        print(f"fps_log: unknown preset(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    if blender_running():
        print(
            "fps_log: a Blender job is running (pgrep -f '[b]lender -b'); not measuring",
            file=sys.stderr,
        )
        return 3

    FPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    rows = []
    for preset in wanted:
        folder = run_route(preset, args.visible)
        if blender_running():
            print(
                "fps_log: a Blender job started during the run; stopping, nothing logged for it",
                file=sys.stderr,
            )
            return 3
        if folder is None:
            print(f"fps_log: the {preset} run failed", file=sys.stderr)
            return 1
        report = json.loads((folder / "report.json").read_text())
        target = entries[preset].get("target_fps")
        record = record_from(report, preset, target, folder, args.visible)
        (FPS_DIR / f"{stamp}-{preset}.json").write_text(
            json.dumps(record, indent=2) + "\n"
        )
        rows.append(record)

    print(
        f"{'preset':<8} {'target':>6} {'avg':>6} {'1% low':>7} {'min':>6} {'est. uncapped':>14} {'bound':>6}"
    )
    for r in rows:
        target = "none" if r["target_fps"] is None else f"{r['target_fps']:.0f}"
        print(
            f"{r['preset']:<8} {target:>6} {r['avg_fps']:>6} {r['p1_low_fps']:>7} {r['min_fps']:>6} "
            f"{r['est_uncapped_fps']!s:>14} {r['bound_by']!s:>6}"
        )
    cap = rows[0]["vsync_cap_hz"] if rows else None
    if cap:
        print(
            f"(off screen: vsync forced on at {cap} Hz, so avg cannot pass it; see est. uncapped)"
        )
    print(f"logged: {FPS_DIR}/{stamp}-*.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
