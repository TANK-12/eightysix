"""v2 checks: motion curves rank clips, energy-matched EDL, FIFO job queue."""

import subprocess
import time

import numpy as np
import pytest

from pulseforge import clips as clipmod
from pulseforge.config import ffmpeg_caps
from pulseforge.scenes.montage import build_edl
from pulseforge.scenes.registry import SceneContext

pytestmark = pytest.mark.skipif(
    not ffmpeg_caps()["ffmpeg"], reason="ffmpeg not available"
)


def _make_clip(path, src, seconds=4):
    lavfi = {
        "testsrc2": f"testsrc2=size=160x90:rate=15:duration={seconds}",
        "still": f"color=c=gray:size=160x90:rate=15:duration={seconds}",
    }[src]
    subprocess.run(
        [
            ffmpeg_caps()["ffmpeg"],
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            lavfi,
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )


def test_motion_curve_ranks_busy_over_still(tmp_path):
    busy = tmp_path / "busy.mp4"
    still = tmp_path / "still.mp4"
    _make_clip(busy, "testsrc2")
    _make_clip(still, "still")
    m_busy = clipmod.motion_curve(str(busy))
    m_still = clipmod.motion_curve(str(still))
    assert len(m_busy) and len(m_still)
    assert m_busy.mean() > m_still.mean() + 0.1


def test_montage_edl_matches_energy_to_motion(tmp_path):
    busy = tmp_path / "busy.mp4"
    still = tmp_path / "still.mp4"
    _make_clip(busy, "testsrc2", seconds=6)
    _make_clip(still, "still", seconds=6)

    fps, dur = 30.0, 6.0
    n = int(fps * dur)
    energy = np.concatenate([np.full(n // 2, 0.95), np.full(n - n // 2, 0.05)])
    beat = np.zeros(n, dtype=bool)
    beat[:: int(fps // 2)] = True  # a beat every 0.5 s
    feat = {
        "fps": fps,
        "n_frames": n,
        "duration": dur,
        "energy": energy,
        "beat": beat,
        "bands": np.zeros((n, 12)),
    }
    params = {p["key"]: p["default"] for p in build_edl.__globals__["SCENE"]["params"]}
    params["max_shot"] = 1.0
    ctx = SceneContext(
        160, 90, fps, n, dur, feat, params, [str(tmp_path)], None, str(tmp_path)
    )
    edl = build_edl(ctx)
    assert edl
    loud = [e for e in edl if e["start"] is not None and e["target_energy"] > 0.5]
    quiet = [e for e in edl if e["target_energy"] <= 0.5]
    assert loud and quiet
    loud_motion = np.mean([e["motion"] for e in loud])
    quiet_motion = np.mean([e["motion"] for e in quiet])
    assert loud_motion > quiet_motion


def test_job_queue_runs_fifo():
    from web_app import AppState

    st = AppState()
    order = []

    def make_target_factory(tag):
        def make_target(job):
            def run():
                time.sleep(0.02)
                order.append(tag)
                return tag

            return run

        return make_target

    for tag in ("a", "b", "c"):
        st.enqueue("test", "p", make_target_factory(tag))

    deadline = time.time() + 5
    while len(order) < 3 and time.time() < deadline:
        time.sleep(0.02)
    assert order == ["a", "b", "c"]
