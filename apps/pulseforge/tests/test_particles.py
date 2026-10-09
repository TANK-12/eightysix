"""The particle layer: every preset draws, "none" changes nothing, every
frame scene offers it, and sparks wait for a beat."""

import numpy as np
import pytest

from pulseforge import particles
from pulseforge.scenes import get_scene, scenes_as_list
from pulseforge.scenes.registry import SceneContext

W, H, FPS, N = 160, 90, 30, 20


def _feat(beats):
    return {
        "fps": float(FPS),
        "n_frames": N,
        "duration": N / FPS,
        "energy": np.full(N, 0.6),
        "sub": np.full(N, 0.5),
        "centroid": np.full(N, 0.5),
        "bands": np.full((N, 12), 0.5),
        "onset": np.full(N, 0.5),
        "beat": np.array([beats and k == 3 for k in range(N)]),
    }


def _black(ctx):
    for _ in range(ctx.n_frames):
        yield np.zeros((ctx.h, ctx.w, 3), np.uint8)


def _run(preset, beats=True, fn=_black):
    ctx = SceneContext(
        W, H, FPS, N, N / FPS, _feat(beats), {"particles": preset}, [], None, "/tmp"
    )
    return [np.asarray(f) for f in particles.wrap(fn)(ctx)]


@pytest.mark.parametrize("preset", list(particles.PRESETS))
def test_every_preset_draws(preset):
    frames = _run(preset)
    assert frames[-1].shape == (H, W, 3) and frames[-1].dtype == np.uint8
    assert frames[-1].max() > 20, preset


def test_none_passes_frames_through_unchanged():
    assert all(f.max() == 0 for f in _run("none"))


def test_sparks_wait_for_a_beat():
    assert max(f.max() for f in _run("sparks", beats=False)) == 0
    assert _run("sparks", beats=True)[6].max() > 20


def test_frame_scenes_offer_particles_and_edl_scenes_do_not():
    for scene in scenes_as_list():
        keys = {p["key"] for p in scene["params"]}
        frame_based = scene["family"] in ("visualizer", "scenery", "sprites")
        assert ("particles" in keys) == frame_based, scene["id"]


def test_a_streak_draws_a_tail_along_the_motion():
    """A preset with `streak` lights a line behind each particle, not a dot."""
    dot = dict(particles.PRESETS["sparks"], streak=0.0)
    tail = dict(particles.PRESETS["sparks"], streak=0.08)
    lit = []
    for preset in (dot, tail):
        layer = particles.Layer(preset, 0.05, 640, 360, 30.0)
        layer.step(0.5, True, 0.0)
        light = layer.step(0.5, False, 1 / 30)
        lit.append(int((light > 0.2).sum()))
    assert lit[1] > lit[0] * 1.5, lit
