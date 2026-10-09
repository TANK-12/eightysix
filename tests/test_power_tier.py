"""The effects' power tier (2026-10-07, "more intelligent power on and off"):
shared/forge_power.js decides full / reduced / paused from the plug, the
charge, the other programs' GPU load and how much of the page shows; the
GNOME extension's share reaches it through shared/forge_seen.py (the hub) and
desktop/particles.py (the desktop)."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FORGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORGE / "shared"))
import forge_gpuload  # noqa: E402
import forge_seen  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "particles_tier", FORGE / "desktop" / "particles.py"
)
assert spec and spec.loader
particles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(particles)

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")
POWER = FORGE / "shared" / "forge_power.js"


def node(script: str):
    out = subprocess.run(
        [
            NODE or "node",
            "-e",
            f"const P = require({json.dumps(str(POWER))});\n{script}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


@needs_node
def test_level_sweep_shown_gpu_battery():
    """Every mix of share, GPU level, plug and charge: the share only ever
    raises the level, to 3 under COVERED_SHARE, and a fully shown page is
    exactly what it was before the share existed."""
    got = node("""
        const out = [];
        const theme = {battery_saver: 20};
        for (let s = 0; s <= 20; s++) for (let g = 0; g <= 3; g++)
          for (const bat of [false, true]) for (const pct of [null, 5, 50, 100]) {
            const shown = s / 20;
            out.push([shown, g, bat, pct,
              P.level(theme, {gpu: g, battery: pct}, bat),
              P.level(theme, {gpu: g, battery: pct, shown}, bat),
              P.tier(theme, {gpu: g, battery: pct, shown}, bat)]);
          }
        console.log(JSON.stringify({rows: out, cut: P.COVERED_SHARE}));
        """)
    cut = got["cut"]
    assert 0.1 < cut < 0.5
    assert len(got["rows"]) == 21 * 4 * 2 * 4
    for shown, _g, _bat, _pct, base, level, tier in got["rows"]:
        assert level == (3 if shown < cut else base), (shown, base, level)
        assert tier == "full" if not level else tier.startswith("reduced: ")


@needs_node
def test_full_when_plugged_in_and_shown():
    got = node("""
        const t = {max_fps: 60, particle_amount: 1, particle_fps: 30, visualiser_shown: true};
        const a = P.values(t, false, {gpu: 0, battery: 80, shown: 1});
        const b = P.values(t, false, {gpu: 0, battery: 80, shown: 0.2});
        console.log(JSON.stringify({a, b, tier: P.tier(t, {shown: 1}, false),
          paused: P.tier(t, {shown: 1, hidden: true}, false)}));
        """)
    assert got["tier"] == "full" and got["paused"] == "paused: hidden"
    assert got["a"].get("max_fps") == 60 and "visualiser_shown" not in got["a"]
    # mostly covered: the reduced tier's last step, and the sliver at 15 fps
    assert got["b"]["max_fps"] == 15 and got["b"]["particle_fps"] == 15
    assert got["b"]["visualiser_shown"] is False
    assert got["b"]["particle_amount"] == 0.5


def test_pid_shown_reads_the_extension_file():
    data = {"pids": {"7": False}, "shown": {"pids": {"7": 0.25, "8": True}}}
    assert forge_seen.pid_shown(data, 7) == 0.25
    assert forge_seen.pid_shown(data, 8) == 1.0  # a bool is no share
    assert forge_seen.pid_shown(data, 9) == 1.0
    assert forge_seen.pid_shown({}, 7) == 1.0
    assert forge_seen.pid_shown({"shown": {"pids": {"7": 3}}}, 7) == 1.0
    assert forge_seen.pid_shown({"shown": {"pids": {"7": -1}}}, 7) == 0.0


def test_read_shown_per_screen(tmp_path):
    f = tmp_path / "under.json"
    f.write_text(
        json.dumps(
            {"0": True, "pids": {}, "shown": {"screens": {"0": 0.05, "1": 1, "x": 0}}}
        )
    )
    assert particles.read_shown(f) == {0: 0.05, 1: 1.0}
    assert particles.read_under(f) == {0: True}
    f.write_text("{bad")
    assert particles.read_shown(f) == {}
    assert particles.read_shown(tmp_path / "none.json") == {}
    f.write_text(json.dumps({"0": False}))  # an extension from before tiers
    assert particles.read_shown(f) == {}


@needs_node
def test_tier_says_why():
    got = node("""
        const t = {battery_saver: 20};
        console.log(JSON.stringify([
          P.tier(t, {gpu: 3, reason: "cpu"}, false),
          P.tier(t, {gpu: 2, reason: "gpu"}, false),
          P.tier(t, {gpu: 0, battery: 10}, true),
          P.tier(t, {gpu: 0, shown: 0.2}, false),
          P.tier(t, {gpu: 0, shown: 0.6}, false),
          P.tier(t, {gpu: 3, reason: "cpu", hidden: true}, false),
          P.values({max_fps: 60, particle_fps: 30}, false, {gpu: 3, reason: "cpu"}).max_fps,
        ]));
        """)
    assert got == [
        "reduced: machine busy",
        "reduced: GPU busy",
        "reduced: battery low",
        "reduced: mostly covered",
        "full",
        "paused: hidden",
        25,  # a busy machine: 25 fps, Emerson's load floor, not the sliver's 15
    ]


def test_cpu_busy_hysteresis():
    """Enter at 70 % held 10 s, leave under 50 % held 20 s; spikes, dips and
    the band between keep what it was."""
    b = forge_gpuload.CpuBusy()
    t = 0.0

    def run(pct, seconds, step=3.0):
        nonlocal t
        out = []
        end = t + seconds
        while t < end:
            out.append(b.feed(pct, t))
            t += step
        return out

    assert not any(run(95, 9))  # under 10 s of load: still calm
    assert not any(run(40, 3))  # a dip resets the count
    assert run(75, 15)[-1] is True  # held past 10 s: busy
    assert all(run(60, 60))  # the band between: stays busy
    assert all(run(45, 18))  # calm under 20 s: still busy
    assert all(run(80, 3))  # a spike resets the calm count
    assert run(30, 24)[-1] is False  # calm past 20 s: back to full
    assert not any(run(65, 60))  # under the enter mark: never busy


def test_cpu_busy_sweep_never_flickers():
    """Any load wobbling around one level, sampled every 3 s for 10 minutes,
    changes state at most once."""
    for level in range(0, 101, 5):
        for wobble in (0, 5, 15):
            b = forge_gpuload.CpuBusy()
            states = [
                b.feed(level + (wobble if i % 2 else -wobble), i * 3.0)
                for i in range(200)
            ]
            flips = sum(1 for a, c in zip(states, states[1:]) if a != c)
            assert flips <= 1, (level, wobble, flips)


def fake_stat(root, busy, idle):
    (root / "stat").write_text(f"cpu  {busy} 0 0 {idle} 0 0 0 0 0 0\ncpu0 1 1 1 1\n")


def test_gpuload_reads_the_machine(tmp_path):
    class Meter:
        proc = tmp_path
        t = 0.0

        def clock(self):
            return self.t

        def sample(self):
            return {"busy": 0.0, "by": "", "heavy": False}

    m = Meter()
    busy = idle = 0
    fake_stat(tmp_path, busy, idle)
    load = forge_gpuload.GpuLoad(meter=m)  # type: ignore[arg-type]
    out = {}
    for _ in range(6):  # 90 % for 15 s
        m.t += 3
        busy, idle = busy + 270, idle + 30
        fake_stat(tmp_path, busy, idle)
        out = load.read()
    assert out["level"] == 3 and out["reason"] == "cpu" and out["cpu"] == 90.0
    for _ in range(8):  # 10 % for 24 s
        m.t += 3
        busy, idle = busy + 30, idle + 270
        fake_stat(tmp_path, busy, idle)
        out = load.read()
    assert out["level"] == 0 and out["reason"] == ""


def test_cpu_times_bad_files(tmp_path):
    assert forge_gpuload.cpu_times(tmp_path) is None
    (tmp_path / "stat").write_text("intr 1 2\n")
    assert forge_gpuload.cpu_times(tmp_path) is None
    fake_stat(tmp_path, 10, 30)
    assert forge_gpuload.cpu_times(tmp_path) == (10, 40)
    assert forge_gpuload.cpu_times() is not None  # the real /proc


HUB = (FORGE / "hub" / "index.html").read_text(encoding="utf-8")


def test_hub_wires_the_tier_and_the_new_keys():
    # the tier reaches the widgets and the 3D wallpaper (helper-6's side)
    assert "power_tier: powerTheme.power_tier" in HUB
    assert 'tier: powerTheme.power_tier || "full"' in HUB
    assert "window.forgeShare = " in HUB and "window.forgeTier = " in HUB
    # Alt+W widgets page and Alt+Q close the open app
    assert 'action === "widgets"' in HUB and 'action === "close-app"' in HUB
    assert "body.widgets-only #tiles" in HUB
    forge_py = (FORGE / "forge.py").read_text(encoding="utf-8")
    assert '("pulse", "ambient", "zen", "widgets")' in forge_py
    assert '"temps": forge_sysinfo.temperatures()' in forge_py


@needs_node
def test_values_carry_the_tier():
    got = node("""
        console.log(JSON.stringify([
          P.values({}, false, {gpu: 0}).power_tier,
          P.values({}, false, {gpu: 3, reason: "cpu"}).power_tier,
          P.apply({}, false, {shown: 0.1}).power_tier,
        ]));
        """)
    assert got == ["full", "reduced: machine busy", "reduced: mostly covered"]
