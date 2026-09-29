"""Tests for tools/fps_log.py: the hub record built from a bot report."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fps_log  # noqa: E402

REPORT = {
    "finished": "2026-09-30T07:00:00",
    "resolution": [1920, 1080],
    "render_scale": 0.65,
    "gpu": "Intel(R) Iris(R) Xe Graphics (ADL GT2)",
    "measures": [
        {
            "label": "route",
            "avg_fps": 59.8,
            "p1_low_fps": 51.0,
            "min_fps": 40.2,
            "frame_ms_avg": 16.72,
            "seconds": 20.0,
            "vsync": True,
            "paced_share": 0.9,
            "refresh_hz": 60.0,
            "est_uncapped_fps": 88.4,
            "gpu_ms_avg": 11.3,
            "cpu_ms_avg": 6.1,
            "bound_by": "gpu",
        }
    ],
}


class RecordFrom(unittest.TestCase):
    def test_off_screen_record_has_the_hub_fields_and_the_cap(self) -> None:
        r = fps_log.record_from(
            REPORT, "low", 60.0, Path("/x/images/004-fps-low"), visible=False
        )
        for key in (
            "when",
            "map",
            "preset",
            "target_fps",
            "avg_fps",
            "p1_low_fps",
            "min_fps",
        ):
            self.assertIn(key, r)
        self.assertEqual(r["avg_fps"], 59.8)
        self.assertEqual(r["vsync_cap_hz"], 60.0)
        self.assertTrue(r["target_met_estimate"])
        self.assertEqual(r["images"], "004-fps-low")
        self.assertFalse(r["blender_running"])

    def test_visible_run_has_no_cap_and_ultra_has_no_target(self) -> None:
        r = fps_log.record_from(
            REPORT, "ultra", None, Path("/x/images/005-fps-ultra"), visible=True
        )
        self.assertIsNone(r["vsync_cap_hz"])
        self.assertIsNone(r["target_met_estimate"])
        self.assertEqual(r["window"], "on screen")

    def test_unpaced_vsync_is_not_a_cap(self) -> None:
        report = {"measures": [dict(REPORT["measures"][0], paced_share=0.05)]}
        r = fps_log.record_from(
            report, "low", 60.0, Path("/x/images/007-fps-low"), visible=False
        )
        self.assertIsNone(r["vsync_cap_hz"])

    def test_missing_measure_gives_empty_numbers(self) -> None:
        r = fps_log.record_from(
            {"measures": []},
            "high",
            30.0,
            Path("/x/images/006-fps-high"),
            visible=False,
        )
        self.assertIsNone(r["avg_fps"])
        self.assertIsNone(r["target_met_estimate"])

    def test_presets_come_from_the_registry(self) -> None:
        self.assertEqual(list(fps_log.presets()), ["low", "medium", "high", "ultra"])


if __name__ == "__main__":
    unittest.main()
