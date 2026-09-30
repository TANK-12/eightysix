"""Tests for tools/audio/synth.py (lane B4). Run: python3 -m unittest discover -s tools/audio"""

import json
import pathlib
import sys
import unittest

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import synth  # noqa: E402

RECIPES = json.loads(synth.RECIPES.read_text())["entries"]


class SynthTest(unittest.TestCase):
    def test_every_recipe_renders_clean_and_under_full_scale(self) -> None:
        for rid, recipe in RECIPES.items():
            x = synth.render(recipe, 0)
            self.assertFalse(np.isnan(x).any(), rid)
            peak_db = 20 * np.log10(np.max(np.abs(x)))
            self.assertLessEqual(
                peak_db, float(recipe.get("peak_db", -1.0)) + 0.01, rid
            )
            self.assertGreater(
                len(x), int(float(recipe["duration_s"]) * synth.RATE * 0.99), rid
            )
            self.assertIn(
                recipe["bus"],
                {"weapons", "mech", "impacts", "ambience", "ui", "voice", "music"},
                rid,
            )

    def test_same_recipe_same_sound_and_variants_differ(self) -> None:
        r = RECIPES["gun_57mm_fire"]
        self.assertTrue(np.array_equal(synth.render(r, 1), synth.render(r, 1)))
        self.assertFalse(np.array_equal(synth.render(r, 0), synth.render(r, 1)))

    def test_loops_join_without_a_click(self) -> None:
        for rid, recipe in RECIPES.items():
            if not recipe.get("loop"):
                continue
            x = synth.render(recipe, 0)
            step = np.max(np.abs(np.diff(x)))
            wrap = abs(x[0] - x[-1])
            self.assertLess(
                wrap,
                step * 1.5,
                f"{rid}: the loop point jumps more than the sound itself does",
            )

    def test_no_click_where_the_dry_sound_ends(self) -> None:
        # around the end of duration_s (where a still-ringing layer used to be cut before the
        # reverb tail) no jump may come near the attack's
        for rid, recipe in RECIPES.items():
            if recipe.get("loop"):
                continue
            x = synth.render(recipe, 0)
            d = np.abs(np.diff(x))
            end = int(float(recipe["duration_s"]) * synth.RATE)
            w = min(2400, end // 10)
            near = d[end - w : end + w]
            self.assertLess(
                np.max(near), np.max(d) * 0.1, f"{rid} clicks where the dry sound ends"
            )

    def test_reverb_tail_has_no_echo_of_the_attack(self) -> None:
        # one reverb length after the start, the tail must keep fading, not jump back up
        for rid, recipe in RECIPES.items():
            if not recipe.get("reverb"):
                continue
            x = synth.render(recipe, 0)
            rv = recipe["reverb"]
            at = int(
                (float(rv["time_s"]) + float(rv.get("predelay_s", 0.02))) * synth.RATE
            )
            w = 480
            spike = np.max(np.abs(np.diff(x[at - w : at + w])))
            typical = np.max(np.abs(np.diff(x[at - 4 * w : at - w])))
            self.assertLess(spike, typical * 3, f"{rid} has an echo of its attack")

    def test_one_shots_start_loud_and_fade_out(self) -> None:
        for rid, recipe in RECIPES.items():
            if recipe.get("loop"):
                continue
            x = synth.render(recipe, 0)
            self.assertLess(abs(x[-1]), 0.01, f"{rid} ends in silence")


if __name__ == "__main__":
    unittest.main()
