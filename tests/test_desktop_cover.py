"""How much of a screen or Forge window still shows under other windows
(task 60). The GNOME extension rests the desktop and Forge when less than a
tenth shows; desktop/gnome-extension/.../cover.js does the sums and has no
GNOME imports, so gjs runs it here."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

COVER = (
    Path(__file__).resolve().parents[1]
    / "desktop"
    / "gnome-extension"
    / "forge-desktop-particles@forge"
    / "cover.js"
)

pytestmark = pytest.mark.skipif(not shutil.which("gjs"), reason="needs gjs")


def run(expr):
    script = (
        f"import {{SHOWN_LEAST, clip, shownShare}} from '{COVER.as_uri()}';\n"
        f"print(JSON.stringify({expr}));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".mjs") as f:
        f.write(script)
        f.flush()
        out = subprocess.run(
            ["gjs", "-m", f.name],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
    return json.loads(out.stdout)


SCREEN = "{x: 0, y: 32, width: 1920, height: 1048}"


def r(x, y, w, h):
    return f"{{x: {x}, y: {y}, width: {w}, height: {h}}}"


def test_nothing_above_shows_all():
    assert run(f"shownShare({SCREEN}, [])") == 1


def test_maximised_window_hides_the_screen():
    assert run(f"shownShare({SCREEN}, [{r(0, 32, 1920, 1048)}])") == 0


def test_window_bigger_than_the_screen_hides_it():
    assert run(f"shownShare({SCREEN}, [{r(-50, 0, 2100, 1200)}])") == 0


def test_big_window_that_is_not_maximised_counts_as_cover():
    # a 1800x1000 window leaves about 10.5 % of the work area, two strips
    share = run(f"shownShare({SCREEN}, [{r(60, 56, 1800, 1000)}])")
    assert share == pytest.approx(1 - 1800 * 1000 / (1920 * 1048))
    assert share > run("SHOWN_LEAST")
    # 1860x1020 leaves about 5.7 %: hidden
    assert run(f"shownShare({SCREEN}, [{r(30, 46, 1860, 1020)}])") < run("SHOWN_LEAST")


def test_half_screen_window_leaves_half():
    assert run(f"shownShare({SCREEN}, [{r(0, 32, 960, 1048)}])") == 0.5


def test_two_tiled_halves_hide_it_and_overlaps_count_once():
    halves = (
        f"[{r(0, 32, 960, 1048)}, {r(960, 32, 960, 1048)}, {r(500, 300, 900, 400)}]"
    )
    assert run(f"shownShare({SCREEN}, {halves})") == 0


def test_window_on_another_monitor_does_not_cover():
    assert run(f"shownShare({SCREEN}, [{r(1920, 0, 1920, 1080)}])") == 1


def test_clip_to_monitor_and_empty_rects():
    assert run(f"clip({r(1800, 0, 400, 400)}, {r(0, 0, 1920, 1080)})") == {
        "x": 1800,
        "y": 0,
        "width": 120,
        "height": 400,
    }
    assert run(f"clip({r(1920, 0, 10, 10)}, {r(0, 0, 1920, 1080)})") is None
    assert run("shownShare(null, [])") == 0


def test_many_small_windows_stay_bounded():
    many = ", ".join(r(i * 37 % 1900, i * 53 % 1000, 40, 30) for i in range(300))
    share = run(f"shownShare({SCREEN}, [{many}])")
    assert 0 < share <= 1
