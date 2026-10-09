"""Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y in text boxes (shared/forge_undo.js)."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
FORGE = HERE.parent
# WebKitGTK comes through PyGObject, which only the system Python has
SYSTEM_PYTHON = "/usr/bin/python3"


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_key_rules():
    run = subprocess.run(
        ["node", "--test", str(HERE / "forge_undo.test.js")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stdout + run.stderr


def test_every_page_with_forge_chrome_loads_it():
    chrome = (FORGE / "shared" / "forge_chrome.js").read_text()
    assert 'new URL("forge_undo.js"' in chrome


def webkit(bare=False):
    env = dict(os.environ, WEBKIT_DISABLE_COMPOSITING_MODE="1")
    env["WEBKIT_DISABLE_DMABUF_RENDERER"] = "1"
    if bare:
        env["FORGE_UNDO_BARE"] = "1"
    try:
        run = subprocess.run(
            ["timeout", "-s", "KILL", "40", SYSTEM_PYTHON, "-u"]
            + [str(HERE / "forge_undo_webkit.py")],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("WebKitGTK did not answer")
    lines = [x for x in run.stdout.splitlines() if x.startswith("{")]
    if not lines:
        pytest.skip(f"no WebKitGTK here: {run.stderr[-300:]}")
    return json.loads(lines[-1])


@pytest.mark.skipif(
    not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")),
    reason="needs a display for WebKitGTK",
)
def test_real_webkit_key_presses_undo_and_redo():
    got = webkit()
    for where in ("page", "iframe"):
        assert got[f"{where} typed"] == "ab"
        assert got[f"{where} ctrl+z"] == ""
        assert got[f"{where} ctrl+shift+z"] == "ab"
        assert got[f"{where} ctrl+z again"] == ""
        assert got[f"{where} ctrl+y"] == "ab"
    # without the script the keys do nothing: the bug this file fixes
    bare = webkit(bare=True)
    assert bare["page typed"] == "ab" and bare["page ctrl+z"] == "ab"
