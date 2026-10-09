"""The page's suit.js skin cover, run for real in node (tests/js/suit_skin.mjs):
the light suit's shorts band, the undersuit, and the covers it refuses."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from exolab.registry import SHARED_DIR

SCRIPT = Path(__file__).parent / "js" / "suit_skin.mjs"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_cover_skin_in_node() -> None:
    env = {**os.environ, "FORGE_SHARED_DIR": str(SHARED_DIR)}
    run = subprocess.run(
        ["node", str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert run.returncode == 0, run.stderr[-3000:]
    assert run.stdout.strip() == "ok 15", run.stdout[-1000:]
