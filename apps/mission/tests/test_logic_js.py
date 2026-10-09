"""Runs the page logic tests (tests/logic.test.js, tests/chat_logic.test.js)
under node, when node is here."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
@pytest.mark.parametrize("name", ["logic.test.js", "chat_logic.test.js"])
def test_page_logic_under_node(name):
    here = Path(__file__).parent
    run = subprocess.run(
        ["node", "--test", str(here / name)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stdout + run.stderr
