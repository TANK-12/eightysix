"""Tests for tools/sync_models.py: copies changed files only and never deletes."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sync_models  # noqa: E402


class SyncOne(unittest.TestCase):
    def test_copies_changes_keeps_extras_and_skips_blends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp, "src"), Path(tmp, "dest")
            src.mkdir()
            (src / "m.glb").write_bytes(b"one")
            (src / "m.json").write_text("{}")
            (src / "m.blend").write_bytes(b"never")
            first = sync_models.sync_one("m", src, dest)
            self.assertEqual(first["copied"], ["m.glb", "m.json"])
            self.assertFalse((dest / "m.blend").exists())
            listing = json.loads((dest / "SOURCE.json").read_text())["files"]
            self.assertEqual(set(listing), {"m.glb", "m.json"})

            (dest / "kept.txt").write_text("mine")
            (src / "m.glb").write_bytes(b"two")
            second = sync_models.sync_one("m", src, dest)
            self.assertEqual(second["copied"], ["m.glb"])
            self.assertEqual(second["same"], ["m.json"])
            self.assertEqual((dest / "m.glb").read_bytes(), b"two")
            self.assertTrue((dest / "kept.txt").exists(), "never deletes")


if __name__ == "__main__":
    unittest.main()
