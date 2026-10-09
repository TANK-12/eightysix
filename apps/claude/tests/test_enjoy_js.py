"""Runs the Enjoy layout's node tests (tests/enjoy_logic.test.js) inside the
app's pytest suite, so one command checks both."""

import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_enjoy_logic_under_node():
    done = subprocess.run(
        ["node", "--test", str(HERE / "enjoy_logic.test.js")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-2000:]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_markdown_under_node():
    done = subprocess.run(
        ["node", "--test", str(HERE / "markdown.test.js")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-2000:]
