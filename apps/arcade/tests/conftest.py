"""Arcade tests run against a temp home and a Jan address nothing listens on,
so they never touch the real Hearsay save or ask the real Jan anything."""

import os
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
os.environ["HOME"] = tempfile.mkdtemp(prefix="arcade-test-home-")
os.environ["JAN_BASE_URL"] = "http://127.0.0.1:9/v1"
os.environ.pop("JAN_MODEL", None)
