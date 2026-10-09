"""The game's gamepad mapping (static/game/pad.js and controls.json), run for
real in node (tests/js/pad_map.mjs) on fake DualSense states, and fed into
the real sim to check a press does what the pause menu says; and main.js's
pad wiring run in a node vm (tests/js/main_pad.mjs)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "js" / "pad_map.mjs"
WIRING = Path(__file__).parent / "js" / "main_pad.mjs"
MAIN = SCRIPT.parents[2] / "static" / "game" / "main.js"
CHECKS = 54
WIRING_CHECKS = 19
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="no node")


@needs_node
def test_pad_mapping_in_node() -> None:
    run = subprocess.run(
        ["node", str(SCRIPT)], capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 0, run.stderr[-3000:]
    assert run.stdout.strip() == f"ok {CHECKS}", run.stdout[-1000:]


@needs_node
def test_main_pad_wiring_in_node() -> None:
    """main.js's real pollPad, menu, focus, mouse and hub messages on fake
    pads, a fake clock and a fake hub (critic 2's G1-G10)."""
    run = subprocess.run(
        ["node", str(WIRING)], capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 0, run.stderr[-3000:]
    assert run.stdout.strip() == f"ok {WIRING_CHECKS}", run.stdout[-1000:]


@needs_node
def test_main_parses(tmp_path: Path) -> None:
    """main.js imports three.js, so node cannot run it; it can parse it."""
    copy = tmp_path / "main.mjs"
    copy.write_text(MAIN.read_text())
    run = subprocess.run(
        ["node", "--check", str(copy)], capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 0, run.stderr[-3000:]


def test_main_wiring() -> None:
    """main.js reads pads only through pad.js: listPads (a refused
    getGamepads() becomes a reason, not a throw) and choosePad (the pad in
    use, not slot 0). It tells Forge it reads the pad only while it sees one,
    and posts that to window.parent even at the top level, where a pop-out's
    own script hears it, and takes it back on a page error. It hears the
    hub's "visible" and "focus", pauses pad play when the window loses
    focus, and keeps the mouse quiet for a moment after pad input (the
    DualSense touchpad is also a desktop touchpad)."""
    main = MAIN.read_text()
    assert "navigator.getGamepads" not in main
    assert "listPads(navigator)" in main
    assert "choosePad(gamepads(), controls, padState)" in main
    assert "firstPad" not in main
    assert 'postMessage({ forge: "pad", native }' in main
    assert "window.parent === window" not in main
    assert "padToHub(!!gp)" in main
    assert "padToHub(true)" not in main
    assert 'e.data.forge === "visible"' in main
    assert 'e.data.forge === "focus"' in main
    assert "if (e.data.focused === false) padAway();" in main
    assert "else padBack();" in main
    assert 'window.addEventListener("focus", padBack)' in main
    assert "lockMenu(padState, true)" in main
    assert 'window.addEventListener("error", () => padToHub(false))' in main
    assert "if (padQuiet()) return;" in main
    assert '(device === "pad" || padMoving()) && started && !paused' in main
    assert "lockMenu(padState)" in main
    assert "padState.menuLock" not in main
    assert "if (fromPad) return;" in main
    assert "menuMove(menuIdx, m, menuItems().length)" in main
