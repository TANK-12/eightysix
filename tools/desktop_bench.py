"""Before/after bench for the desktop's particles, visualiser, widgets and 3D
wallpaper (tools/desktop_bench.html, 2026-10-07).

Runs the bench page in headless Chrome (Flatpak) once with an older copy of
the shared scripts and once with the current ones, scenario by scenario and
interleaved, `--runs` times each, so other sessions' load hits both alike.
Per run it records, for that browser's own processes only:
  - CPU: % of one core, from /proc/<pid>/stat
  - GPU: % busy of the GPU engines, from the DRM fdinfo of those processes
    (shared/forge_gpuload.GpuMeter, the per-client numbers intel_gpu_top shows)
  - frames drawn a second and the JavaScript time per drawn frame (in-page)
and the system load (load average and the five busiest processes) beside
it. The summary is the median of the runs, the spread (max - min) and the
change in %.

    apps/claude/.venv/bin/python tools/desktop_bench.py OLD_SHARED_DIR \
        [--seconds 10] [--runs 3] [--gpu] [--only TEXT]

--gpu lets Chrome draw with the laptop's GPU (no --disable-gpu); without it
everything is drawn in software, and CPU% is then the drawing cost.
OLD_SHARED_DIR holds the older forge_particles.js, forge_visual.js,
forge_widgets.js, forge_widgets.css and forge_depth.js (a backups/ folder).
"""

import argparse
import asyncio
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORGE / "tests"))
sys.path.insert(0, str(FORGE / "shared"))

import websockets  # noqa: E402
from cdp_driver import Page, browsers_using, close_browser, free_port, reap  # type: ignore  # noqa: E402
from forge_gpuload import GpuMeter  # noqa: E402

FILES = (
    "forge_particles.js",
    "forge_visual.js",
    "forge_widgets.js",
    "forge_widgets.css",
    "forge_depth.js",
)
TICK = os.sysconf("SC_CLK_TCK")
WALL = Path.home() / ".cache/forge/wallpaper"

SCENARIOS = [
    *(
        ("particles", f"kind={k}")
        for k in (
            "soft",
            "embers",
            "constellation",
            "petals",
            "rain",
            "lanterns",
            "stars",
        )
    ),
    *(
        ("visual", f"style={s}")
        for s in ("bars", "ring", "wave", "orbit", "terrain", "aurora")
    ),
    # new in v2: the old scripts fall back to soft drift / draw nothing here
    *(("particles", f"kind={k}") for k in ("wisps", "galaxy")),
    *(("visual", f"style={s}") for s in ("spectrum", "nebula")),
    ("particles", "kind=embers&fps=30"),
    ("widgets", ""),
    ("depth", ""),
    ("depth", "app=1"),
    ("depth", "tier=reduced"),
    ("all", "kind=embers&style=orbit"),
    ("all", "kind=embers&style=orbit&tier=reduced"),
    ("all", "kind=embers&style=orbit&tier=paused"),
]
LONG = "kind=embers&style=orbit"  # 30 s, plus hidden and back


def cpu_ticks(pids: list[int]) -> int:
    total = 0
    for pid in pids:
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            total += int(fields[11]) + int(fields[12])
        except (OSError, IndexError, ValueError):
            pass
    return total


def load_note() -> str:
    up = Path("/proc/loadavg").read_text().split()[:3]
    top = subprocess.run(
        ["ps", "-eo", "pcpu,comm", "--sort=-pcpu", "--no-headers"],
        capture_output=True,
        text=True,
    ).stdout.splitlines()[:5]
    return f"load {' '.join(up)}; top: " + ", ".join(" ".join(t.split()) for t in top)


def build(where: Path, shared: Path) -> None:
    (where / "shared").mkdir(parents=True)
    for name in FILES:
        shutil.copy(shared / name, where / "shared" / name)
    shutil.copy(FORGE / "shared" / "forge_idle.js", where / "shared" / "forge_idle.js")
    shutil.copy(FORGE / "tools" / "desktop_bench.html", where / "bench.html")
    pics = sorted(WALL.glob("*-depth.png"))
    if pics:
        shutil.copy(pics[0], where / "depth.png")
        shutil.copy(str(pics[0]).replace("-depth.png", ".jpg"), where / "wall.jpg")


async def browser(sandbox: Path, gpu: bool):
    """Headless Chrome on a DevTools port, like cdp_driver.chrome_page, with
    the GPU allowed when asked. Returns (proc, port, websocket url)."""
    port = free_port()
    args = [
        "flatpak",
        "run",
        f"--filesystem={sandbox}",
        "--command=/app/extra/google-chrome",
        "com.google.Chrome",
        "--headless=new",
        "--no-sandbox",
        "--allow-file-access-from-files",  # WebGL may read the file:// picture
        f"--user-data-dir={sandbox / 'chrome-profile'}",
        f"--remote-debugging-port={port}",
        "--window-size=1920,1080",
        *(["--enable-gpu", "--ignore-gpu-blocklist"] if gpu else ["--disable-gpu"]),
        "about:blank",
    ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tabs: list[dict] = []
    for _ in range(150):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
            break
        except OSError:
            await asyncio.sleep(0.1)
    target = next(t for t in tabs if t["type"] == "page")
    return proc, port, target["webSocketDebuggerUrl"]


async def measure(page, profile: Path, seconds: float, hidden: bool) -> dict:
    await page.js(f"bench.hide({str(hidden).lower()}); bench.reset(); 1")
    pids = browsers_using(profile)
    meter = GpuMeter()
    meter.shares()
    t0, c0 = time.monotonic(), cpu_ticks(pids)
    await asyncio.sleep(seconds)
    shares = meter.shares()
    dt, used = time.monotonic() - t0, cpu_ticks(pids) - c0
    b = json.loads(await page.js("JSON.stringify(bench)"))
    mine = set(browsers_using(profile))
    gpu = sum(s for pid, s in shares.items() if pid in mine)
    out = {"cpu_pct": round(100 * used / TICK / dt, 1), "gpu_pct": round(100 * gpu, 1)}
    for key, name in (
        ("p", "particles"),
        ("v", "visual"),
        ("w", "widget_vis"),
        ("d", "depth"),
    ):
        frames = b.get(f"{key}f", 0)
        if frames:
            out[f"{name}_fps"] = round(frames / dt, 1)
            out[f"{name}_ms"] = round(b[f"{key}ms"] / frames, 3)
    return out


async def one(
    dir_: Path, mode: str, query: str, seconds: float, long: bool, gpu: bool
) -> dict:
    proc, port, ws_url = await browser(dir_, gpu)
    try:
        async with websockets.connect(ws_url, max_size=None) as ws:
            page = Page(ws)
            await page.call("Page.enable")
            await page.go(f"file://{dir_}/bench.html?mode={mode}&{query}")
            await page.wait("window.bench && document.readyState === 'complete'", 15)
            await asyncio.sleep(2)  # settle: sprites, textures, first layout
            profile = dir_ / "chrome-profile"
            res = {"visible": await measure(page, profile, seconds, False)}
            if long:
                res["hidden"] = await measure(page, profile, seconds, True)
                res["back"] = await measure(page, profile, 3, False)
    finally:
        await close_browser(port)
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        reap(dir_ / "chrome-profile")
        shutil.rmtree(dir_ / "chrome-profile", ignore_errors=True)
    return res


def summary(runs: list[dict], part: str, key: str) -> tuple[float, float] | None:
    vals = [r[part][key] for r in runs if part in r and key in r[part]]
    if not vals:
        return None
    return statistics.median(vals), round(max(vals) - min(vals), 3)


def change(old, new) -> str:
    if not old or not new or not old[0]:
        return "-"
    return f"{100 * (new[0] - old[0]) / old[0]:+.0f}%"


def show(v) -> str:
    return f"{v[0]} ±{v[1]}" if v else "-"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("old", type=Path)
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--gpu", action="store_true")
    ap.add_argument("--only", default="", help="run scenarios whose text contains this")
    a = ap.parse_args()
    root = Path(tempfile.mkdtemp(prefix="desktop-bench-"))
    try:
        build(root / "old", a.old)
        build(root / "new", FORGE / "shared")
        table = []
        for mode, query in SCENARIOS:
            name = f"{mode} {query}".strip()
            if a.only and a.only not in name:
                continue
            long = query == LONG
            secs = 30 if long else a.seconds
            runs: dict[str, list] = {"old": [], "new": []}
            for _ in range(a.runs):
                for variant in ("old", "new"):
                    note = load_note()
                    r = await one(root / variant, mode, query, secs, long, a.gpu)
                    r["load"] = note
                    runs[variant].append(r)
                    print(
                        json.dumps({"scenario": name, "variant": variant, **r}),
                        flush=True,
                    )
            for part in ["visible", "hidden"] if long else ["visible"]:
                row = [f"{name}{' (hidden)' if part == 'hidden' else ''}"]
                for key in ("cpu_pct", "gpu_pct"):
                    o, n = summary(runs["old"], part, key), summary(
                        runs["new"], part, key
                    )
                    row.append(f"{show(o)} -> {show(n)} ({change(o, n)})")
                for fk in (
                    "depth_fps",
                    "particles_fps",
                    "visual_fps",
                    "widget_vis_fps",
                ):
                    o, n = summary(runs["old"], part, fk), summary(
                        runs["new"], part, fk
                    )
                    if not (o or n):
                        continue
                    mk = fk.replace("_fps", "_ms")
                    om, nm = summary(runs["old"], part, mk), summary(
                        runs["new"], part, mk
                    )
                    row.append(
                        f"{fk[:-4]} {o[0] if o else '-'} -> {n[0] if n else '-'} fps,"
                        f" {om[0] if om else '-'} -> {nm[0] if nm else '-'} ms ({change(om, nm)})"
                    )
                table.append(" | ".join(row))
        print(
            f"\nmedian of {a.runs} runs, ± spread (max - min);"
            f" {'GPU drawing' if a.gpu else 'software drawing'}"
        )
        print(
            "scenario | CPU % of a core | GPU % busy | frames a second, JS ms per frame"
        )
        print("\n".join(table))
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
