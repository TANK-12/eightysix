"""Tests for tools/make_mech_textures.py's albedo step (Alpha 0.1.1: a contrast knob, so the chipped paint's
blotches can be calmed without losing the chips)."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import make_mech_textures as m  # noqa: E402


class Albedo(unittest.TestCase):
    def setUp(self) -> None:
        rng = np.random.default_rng(86)
        self.colour = np.clip(rng.normal(0.6, 0.15, (64, 64, 3)), 0.0, 1.0).astype(
            np.float32
        )

    def test_contrast_one_changes_nothing(self) -> None:
        plain = m.albedo(self.colour, 0.65, 0.86)
        same = m.albedo(self.colour, 0.65, 0.86, 1.0)
        np.testing.assert_allclose(plain, same, atol=1e-6)

    def test_lower_contrast_calms_the_pattern_and_keeps_the_mean(self) -> None:
        full = m.albedo(self.colour, 0.65, 0.86)
        calm = m.albedo(self.colour, 0.65, 0.86, 0.6)
        self.assertAlmostEqual(float(calm.mean()), 0.86, delta=0.005)
        self.assertLess(float(calm.std()), float(full.std()) * 0.7)
        self.assertGreater(float(calm.std()), float(full.std()) * 0.5)


if __name__ == "__main__":
    unittest.main()
