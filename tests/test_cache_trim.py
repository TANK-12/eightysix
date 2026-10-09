"""Tests for tools/cache_trim.py, run with: python3 -m unittest tests/test_cache_trim.py"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import cache_trim  # noqa: E402  # pyright: ignore[reportMissingImports]

MB = 1024 * 1024


def make(root: Path, name: str, mb: int, age_minutes: float) -> Path:
    d = root / name
    d.mkdir()
    f = d / "blob"
    f.write_bytes(b"\0" * (mb * MB))
    t = time.time() - age_minutes * 60
    os.utime(f, (t, t))
    os.utime(d, (t, t))
    return d


class TrimTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def entry(self, limit_mb):
        return {
            "name": "t",
            "path": str(self.root),
            "pattern": "scoped_dir*",
            "limit_mb": limit_mb,
            "min_age_minutes": 60,
        }

    def test_under_limit_removes_nothing(self):
        make(self.root, "scoped_dirA", 1, 500)
        r = cache_trim.trim(self.entry(10))
        self.assertEqual(r["status"], "under limit")
        self.assertTrue((self.root / "scoped_dirA").exists())

    def test_over_limit_removes_oldest_until_half(self):
        for i, age in enumerate([400, 300, 200, 100]):
            make(self.root, f"scoped_dir{i}", 2, age)
        r = cache_trim.trim(self.entry(6))  # 8 MB > 6, target 3 MB
        self.assertEqual(r["removed"], 3)
        left = sorted(p.name for p in self.root.iterdir())
        self.assertEqual(left, ["scoped_dir3"])

    def test_recent_and_unmatched_entries_survive(self):
        make(self.root, "scoped_dirOld", 3, 500)
        make(self.root, "scoped_dirNew", 3, 5)
        make(self.root, "Default", 3, 500)
        r = cache_trim.trim(self.entry(2))
        self.assertEqual(r["removed"], 1)
        left = sorted(p.name for p in self.root.iterdir())
        self.assertEqual(left, ["Default", "scoped_dirNew"])

    def test_dry_run_deletes_nothing(self):
        make(self.root, "scoped_dirA", 3, 500)
        r = cache_trim.trim(self.entry(1), dry_run=True)
        self.assertEqual(r["removed"], 1)
        self.assertTrue((self.root / "scoped_dirA").exists())

    def test_missing_folder(self):
        r = cache_trim.trim({**self.entry(1), "path": str(self.root / "nope")})
        self.assertEqual(r["status"], "missing")


if __name__ == "__main__":
    unittest.main()
