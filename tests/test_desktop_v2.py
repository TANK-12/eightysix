"""Desktop v2 (2026-10-07): particles, visualiser and widgets.

The shared scripts run under node with a recording 2D context
(tests/desktop_v2_node.js). Checked here:
- every particle kind draws at 60, 30 and 12 frames a second without throwing
  and without a NaN or infinite coordinate;
- motion is per second: a second at 20 fps moves the dots as far as a second
  at 60 fps (board note #931: they crawled at low frame caps);
- hidden, no frame is asked for; shown again, one is, and the first frame
  after the rest counts as an ordinary one (no jump);
- the visualiser styles batch their drawing (draw calls per frame);
- the power tier (theme.power_tier): reduced caps the rate at 30, paused
  draws nothing, full again draws.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

import forge_theme  # noqa: E402

node = pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")


def run(check: str) -> dict:
    out = subprocess.run(
        ["node", str(ROOT / "tests" / "desktop_v2_node.js"), check],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(out.stdout)


@node
def test_every_kind_draws_at_every_frame_rate():
    res = run("kinds")
    kinds = set(forge_theme.PARTICLE_LABELS) - {"off", "auto"}
    assert {k.split("@")[0] for k in res} == kinds
    bad = {k: v for k, v in res.items() if v["err"] or v["nonFinite"] or not v["draws"]}
    assert not bad


@node
def test_a_second_is_a_second_at_any_frame_rate():
    for kind, r in run("speed").items():
        assert r["at60"] > 1, kind
        assert abs(r["at20"] - r["at60"]) / r["at60"] < 0.08, (kind, r)
        # a 5 fps battery cap still moves them in real time (critic, 2026-10-07)
        assert abs(r["at5"] - r["at60"]) / r["at60"] < 0.2, (kind, r)


@node
def test_nothing_to_draw_asks_for_no_frames():
    assert run("amount0") == {"dots": 0, "running": "0"}


@node
def test_hidden_asks_for_no_frames_and_comes_back_without_a_jump():
    r = run("hidden")
    assert r == {
        "before": True,
        "whileHidden": False,
        "running": "0",
        "after": True,
        "kAfterRest": 1,
    }


@node
def test_the_visualiser_batches_its_drawing():
    res = run("visual")
    assert set(res) == set(forge_theme.VISUALISER_LABELS)
    assert all(r["ok"] for r in res.values())
    calls = {k: r["calls"] for k, r in res.items()}
    # one gradient and two fills for 64 bars (was 64 gradients and 64 fills)
    assert calls["bars"].get("createLinearGradient") == 1
    assert calls["bars"]["fill"] <= 2
    # spokes in opacity steps: at most 12 strokes for 96 spokes
    assert calls["ring"]["stroke"] <= 12
    # orbit stamps a sprite; no radial gradient per light
    assert "createRadialGradient" not in calls["orbit"]
    assert calls["mirror"]["fill"] <= 12


@node
def test_power_tier_reduces_and_pauses():  # also "reduced: GPU busy" text
    r = run("tier")
    assert r["fullDots"] > 0
    # the amount is eased in the theme by forge_power.js, not again here
    assert r["reducedDots"] == r["fullDots"]
    assert r["reducedFrames"] <= 31  # one second at a 30 cap
    assert r["fullFrames"] >= 59
    assert r["pausedRunning"] == "0" and r["pausedRaf"] is False
    assert r["backRunning"] == "1"


def test_new_kinds_and_styles_are_one_entry_each():
    js = (ROOT / "shared" / "forge_particles.js").read_text()
    for kind in ("wisps", "galaxy"):
        assert re.search(rf"^    {kind}: \{{ count:", js, re.M)
        assert kind in forge_theme.PARTICLE_LABELS
    for style in ("spectrum", "nebula"):
        assert style in forge_theme.VISUALISER_LABELS
    # the widget's style menu is ForgeVisual's own list, not a copy
    widgets = (ROOT / "shared" / "forge_widgets.js").read_text()
    assert "get choices() { return visStyles(); }" in widgets


def test_galaxy_photos_still_get_twinkling_stars():
    assert forge_theme.ambience("galaxy_space.jpg", [], {})[0] == "stars"
    assert forge_theme.ambience("milky-way-spiral.jpg", [], {})[0] == "galaxy"
    assert forge_theme.ambience("forest-spirit-ghibli.png", [], {})[0] == "wisps"
