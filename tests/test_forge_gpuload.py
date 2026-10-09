"""shared/forge_gpuload.py (Emerson, 2026-09-29): other programs' GPU load
from DRM fdinfo, with Forge's own drawing and gnome-shell left out, and the
easing ladder that turns it into a level 0-3."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

import forge_gpuload as g  # noqa: E402

REGISTRY = {"names": {"blender": "Blender"}, "heavy": ["gamescope", ".exe"]}


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def fdinfo(client: int, render_ns: int, video_ns: int = 0) -> str:
    return (
        "pos:\t0\nflags:\t02100002\ndrm-driver:\ti915\ndrm-pdev:\t0000:00:02.0\n"
        f"drm-client-id:\t{client}\ndrm-engine-render:\t{render_ns} ns\n"
        f"drm-engine-video:\t{video_ns} ns\ndrm-engine-capacity-video:\t2\n"
    )


def make_proc(root: Path, pid: int, comm: str, parent: int = 1, cmdline: str = ""):
    d = root / str(pid)
    (d / "fd").mkdir(parents=True)
    (d / "fdinfo").mkdir()
    (d / "comm").write_text(comm + "\n")
    (d / "stat").write_text(f"{pid} ({comm}) S {parent} 1 1 0\n")
    (d / "cmdline").write_text(cmdline.replace(" ", "\0"))
    return d


def gpu_fd(d: Path, fd: int, text: str):
    os.symlink("/dev/dri/renderD128", d / "fd" / str(fd))
    (d / "fdinfo" / str(fd)).write_text(text)


def test_parse_fdinfo_counts_render_not_video():
    key, busy = g.parse_fdinfo(fdinfo(7, 500, video_ns=9999)) or ("", 0)
    assert key == "0000:00:02.0/7" and busy == 500
    assert g.parse_fdinfo("pos:\t0\nflags:\t0\n") is None


def test_busy_share_of_other_programs(tmp_path):
    clock = Clock()
    blender = make_proc(tmp_path, 200, "blender")
    gpu_fd(blender, 5, fdinfo(1, 0))
    gpu_fd(blender, 6, fdinfo(1, 0))  # same client twice: counted once
    shell = make_proc(tmp_path, 300, "gnome-shell")
    gpu_fd(shell, 4, fdinfo(2, 0))
    meter = g.GpuMeter(tmp_path, clock, REGISTRY)
    assert meter.sample() == {"busy": 0.0, "by": "", "heavy": False}
    clock.t += 2.0
    (blender / "fdinfo" / "5").write_text(fdinfo(1, 1_400_000_000))
    (blender / "fdinfo" / "6").write_text(fdinfo(1, 1_400_000_000))
    (shell / "fdinfo" / "4").write_text(fdinfo(2, 2_000_000_000))  # all of it: ignored
    got = meter.sample()
    assert got["busy"] == 0.7 and got["by"] == "Blender" and got["heavy"] is False


def test_forges_own_webkit_is_left_out(tmp_path):
    clock = Clock()
    make_proc(tmp_path, 10, "python3", cmdline="python3 /home/ejb/Forge/forge.py")
    web = make_proc(tmp_path, 11, "WebKitWebProces", parent=10)
    gpu_fd(web, 3, fdinfo(9, 0))
    other = make_proc(tmp_path, 12, "WebKitWebProces", parent=1)  # someone else's
    gpu_fd(other, 3, fdinfo(10, 0))
    meter = g.GpuMeter(tmp_path, clock, REGISTRY)
    meter.sample()
    clock.t += 1.0
    (web / "fdinfo" / "3").write_text(fdinfo(9, 900_000_000))
    (other / "fdinfo" / "3").write_text(fdinfo(10, 300_000_000))
    got = meter.sample()
    assert got["busy"] == 0.3 and got["by"] == "WebKitWebProces"


def test_a_game_that_starts_later_is_seen_and_counts_as_heavy(tmp_path):
    clock = Clock()
    meter = g.GpuMeter(tmp_path, clock, REGISTRY, rescan=999)
    meter.sample()
    game = make_proc(tmp_path, 400, "Game.exe")
    gpu_fd(game, 8, fdinfo(3, 0))
    clock.t += 1
    meter.sample()
    clock.t += 1
    (game / "fdinfo" / "8").write_text(fdinfo(3, 100_000_000))
    got = meter.sample()
    assert got["heavy"] is True and got["busy"] == 0.1


def test_easing_goes_up_at_once_and_down_one_step_after_calm():
    e = g.Easing(calm=10)
    assert e.feed({"busy": 0.3, "by": "Jan"}, 0)["level"] == 1
    assert e.feed({"busy": 0.9, "by": "Jan"}, 1) == {
        "level": 3,
        "by": "Jan",
        "busy": 0.9,
    }
    assert e.feed({"busy": 0.0}, 2)["level"] == 3  # calm starts
    assert e.feed({"busy": 0.0}, 11)["level"] == 3
    assert e.feed({"busy": 0.0}, 12)["level"] == 2  # 10 s calm: one step
    assert e.feed({"busy": 0.0}, 22)["level"] == 1
    got = e.feed({"busy": 0.0}, 32)
    assert got["level"] == 0 and got["by"] == ""


def test_heavy_program_goes_straight_to_the_bottom_rung():
    assert g.Easing().target(0.05, heavy=True) == 3
    assert g.Easing().target(0.5, heavy=False) == 2


def test_registry_file_loads():
    reg = g.load_registry()
    assert reg["names"]["blender"] == "Blender" and "gamescope" in reg["heavy"]
    assert g.load_registry(Path("/nonexistent.json")) == {"names": {}, "heavy": []}


def test_battery_percent(tmp_path):
    bat = tmp_path / "BAT0"
    bat.mkdir()
    (bat / "type").write_text("Battery\n")
    (bat / "capacity").write_text("17\n")
    assert g.battery_percent(tmp_path) == 17
    assert g.battery_percent(tmp_path / "none") is None
