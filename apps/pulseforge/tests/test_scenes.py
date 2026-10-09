"""Every frame-generator scene yields correctly-shaped frames for a few frames."""

import numpy as np
import pytest

from pulseforge.scenes import scenes_as_list, get_scene
from pulseforge.scenes.registry import SceneContext

N = 6
W, H, FPS = 320, 180, 30


def _fake_feat(n):
    rng = np.random.default_rng(0)
    return {
        "fps": float(FPS),
        "n_frames": n,
        "duration": n / FPS,
        "energy": rng.random(n),
        "sub": rng.random(n),
        "centroid": rng.random(n),
        "bands": rng.random((n, 12)),
        "onset": rng.random(n),
        "beat": (rng.random(n) > 0.8),
    }


@pytest.mark.parametrize(
    # "montage" and "amv" are assembled by ffmpeg from an edit decision list
    # and have no frames() at all; that is their contract, not a gap.
    "scene",
    [s["id"] for s in scenes_as_list() if s["family"] not in ("montage", "amv")],
)
def test_scene_frames_shape(scene):
    meta, frame_fn = get_scene(scene)
    params = {p["key"]: p["default"] for p in meta.get("params", [])}
    ctx = SceneContext(W, H, FPS, N, N / FPS, _fake_feat(N), params, [], None, "/tmp")
    frames = list(zip(range(N), frame_fn(ctx)))
    assert len(frames) == N
    for _i, fr in frames:
        arr = np.asarray(fr)
        assert arr.shape == (H, W, 3)
        assert arr.dtype == np.uint8
        assert arr.max() > 0, f"{scene} produced an all-black frame"


def test_montage_needs_clips():
    from pulseforge.scenes import montage

    meta = montage.SCENE
    params = {p["key"]: p["default"] for p in meta["params"]}
    ctx = SceneContext(W, H, FPS, N, N / FPS, _fake_feat(N), params, [], None, "/tmp")
    assert montage.build_edl(ctx) == []  # no clips folder attached -> empty EDL


def test_amv_needs_clips():
    from pulseforge.scenes import amv

    meta = amv.SCENE
    assert meta["family"] == "amv"
    params = {p["key"]: p["default"] for p in meta["params"]}
    ctx = SceneContext(W, H, FPS, N, N / FPS, _fake_feat(N), params, [], None, "/tmp")
    assert amv.build_edl(ctx) == []  # no clips folder attached -> empty EDL
