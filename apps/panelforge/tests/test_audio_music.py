"""Mood music: renders, loops seamlessly, and mood crossfades cleanly."""

import numpy as np

from panelforge.music import generate


def test_all_moods_render_non_silent_no_clip():
    for mood in generate.moods():
        samples, sr = generate.generate(mood)
        assert sr == generate.SR
        assert samples.shape[0] > sr  # at least ~1s
        assert np.max(np.abs(samples)) > 0.01
        assert np.max(np.abs(samples)) <= 1.0


def test_loop_is_seamless():
    """Tiling the loop with itself should not produce a jump at the seam
    that's out of line with normal sample-to-sample movement."""
    loop, sr = generate.generate("calm")
    doubled = np.concatenate([loop, loop], axis=0)
    seam = np.abs(doubled[loop.shape[0]] - doubled[loop.shape[0] - 1])
    interior = np.abs(np.diff(loop, axis=0))
    typical = np.percentile(interior, 95)
    assert np.max(seam) <= typical * 6 + 1e-4


def test_tile_to_length():
    loop, sr = generate.generate("action")
    out = generate.tile_to_length(loop, sr, 5.0)
    assert abs(out.shape[0] / sr - 5.0) < 0.05
    assert np.max(np.abs(out)) <= 1.0


def test_crossfade_moods_no_hard_jump():
    a, sr = generate.generate("calm")
    b, _ = generate.generate("action")
    out = generate.crossfade_moods(a, b, sr, overlap_s=1.0)
    assert out.shape[0] < a.shape[0] + b.shape[0]
    assert np.max(np.abs(out)) <= 1.2  # blended, not summed to clipping
