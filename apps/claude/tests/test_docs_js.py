"""Runs the Docs page's node tests (tests/docs_text.test.js) inside the app's
pytest suite, so one command checks both."""

import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_docs_text_under_node():
    done = subprocess.run(
        ["node", "--test", str(HERE / "docs_text.test.js")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-2000:]
