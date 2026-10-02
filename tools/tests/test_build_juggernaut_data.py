"""Tests for tools/build_juggernaut_data.py's sub-gun muzzle sockets (Emerson's note 12 after version 012)."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_juggernaut_data as b  # noqa: E402


class SubgunMuzzles(unittest.TestCase):
    def setUp(self) -> None:
        self.model = json.loads(b.MODEL_JSON.read_text())
        self.origin = next(j for j in self.model["joints"] if j["bone"] == "body")[
            "head"
        ]
        self.muzzles = b.subgun_muzzles(self.model, self.origin)

    def test_each_muzzle_sits_on_its_sub_arm_front_face(self) -> None:
        for side in ("L", "R"):
            hull = next(
                p for p in self.model["parts"] if p["name"] == f"JG2_subarm.{side}"
            )["hull"]
            at = [
                self.muzzles[f"subgun_{side}"]["at"][i] + self.origin[i]
                for i in range(3)
            ]
            for i in range(2):
                lo, hi = min(v[i] for v in hull), max(v[i] for v in hull)
                self.assertTrue(
                    lo <= at[i] <= hi, f"{side} axis {i} inside the sub-arm"
                )
            self.assertAlmostEqual(
                at[2],
                min(v[2] for v in hull),
                delta=0.01,
                msg=f"{side} at the front face",
            )

    def test_muzzles_are_mirrored_and_outboard_of_the_old_socket(self) -> None:
        left, right = self.muzzles["subgun_L"]["at"], self.muzzles["subgun_R"]["at"]
        self.assertAlmostEqual(left[0], -right[0], places=3)
        self.assertEqual(left[1:], right[1:])
        old = next(s for s in self.model["sockets"] if s["name"] == "subarm_R")["pos"]
        self.assertGreater(right[0], old[0] - self.origin[0] + 0.3)

    def test_mechs_json_carries_them(self) -> None:
        sockets = json.loads(b.MECHS_JSON.read_text())["entries"]["juggernaut_m2"][
            "sockets"
        ]
        for name, s in self.muzzles.items():
            self.assertEqual(sockets[name]["at"], s["at"])


if __name__ == "__main__":
    unittest.main()
