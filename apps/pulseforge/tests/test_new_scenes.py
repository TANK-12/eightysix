"""Tunnel and Scope: registered, and the music really moves them."""

import numpy as np
import pytest

from pulseforge.scenes import get_scene
from pulseforge.scenes.registry import SceneContext

W, H, FPS, N = 160, 90, 30, 12


def _feat(level: float, beats: bool):
    n = N
    return {
        "fps": float(FPS),
        "n_frames": n,
        "duration": n / FPS,
        "energy": np.full(n, level),
        "sub": np.full(n, level),
        "centroid": np.full(n, level),
        "bands": np.full((n, 12), level),
        "onset": np.full(n, level),
        "beat": np.array([beats and k % 4 == 0 for k in range(n)]),
    }


def _last(scene, feat):
    meta, fn = get_scene(scene)
    params = {p["key"]: p["default"] for p in meta["params"]}
    ctx = SceneContext(W, H, FPS, N, N / FPS, feat, params, [], None, "/tmp")
    return np.asarray(list(fn(ctx))[-1], dtype=np.float64)


@pytest.mark.parametrize("scene", ["tunnel", "scope"])
def test_loud_music_draws_more_than_quiet(scene):
    quiet = _last(scene, _feat(0.05, False))
    loud = _last(scene, _feat(0.9, True))
    assert loud.mean() > quiet.mean() * 1.2
    assert np.abs(loud - quiet).mean() > 2.0


@pytest.mark.parametrize("scene", ["tunnel", "scope"])
def test_frames_change_over_time(scene):
    meta, fn = get_scene(scene)
    params = {p["key"]: p["default"] for p in meta["params"]}
    ctx = SceneContext(
        W, H, FPS, N, N / FPS, _feat(0.5, True), params, [], None, "/tmp"
    )
    frames = [np.asarray(f, dtype=np.float64) for f in fn(ctx)]
    assert np.abs(frames[-1] - frames[1]).mean() > 1.0
