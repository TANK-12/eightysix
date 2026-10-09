"""Task 56 (2026-10-07): the hub and the desktop cost less GPU, and the
visualiser no longer trails the music.

The JS parts run under node: ForgeVisual.follow's easing, which styles may
idle in silence, and the 3D wallpaper's drift cap. The CSS and the wiring are
checked in the page sources.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HUB = (ROOT / "hub" / "index.html").read_text()
DESKTOP = (ROOT / "desktop" / "forge_desktop.js").read_text()
WIDGETS_CSS = (ROOT / "shared" / "forge_widgets.css").read_text()

node = pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")


def run_node(script: str) -> dict:
    out = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, check=True, cwd=ROOT
    )
    return json.loads(out.stdout)


@node
def test_follow_rises_at_once_falls_slowly_and_ignores_the_frame_rate():
    r = run_node("""
      global.window = global; require("./shared/forge_visual.js"); const V = window.ForgeVisual;
      const step = (n, dt, target, start) => {
        const s = new Float32Array([start]);
        for (let i = 0; i < n; i++) V.follow(s, [target], dt);
        return s[0];
      };
      console.log(JSON.stringify({
        rise: step(1, 1 / 60, 1, 0),
        fall: step(1, 1 / 60, 0, 1),
        fall60: step(30, 1 / 60, 0, 1),
        fall30: step(15, 1 / 30, 0, 1),
        same: step(5, 0, 1, 0.5),
      }));
    """)
    assert r["rise"] > 0.7  # a beat is drawn within a frame
    assert r["fall"] > 0.85  # and falls away gently
    assert abs(r["fall60"] - r["fall30"]) < 0.01  # same half second at 60 or 30 fps
    assert r["fall60"] < 0.1
    assert r["same"] == 0.5  # a second caller in the same frame changes nothing


@node
def test_only_still_styles_idle_in_silence():
    r = run_node("""
      global.window = global; require("./shared/forge_visual.js"); const V = window.ForgeVisual;
      const out = {};
      for (const s of V.names()) out[s] = V.stillInSilence(s, "neon");
      out.rainbow = V.stillInSilence("bars", "rainbow");
      console.log(JSON.stringify(out));
    """)
    assert r["bars"] and r["ring"] and r["wave"] and r["mirror"]
    assert not (r["orbit"] or r["terrain"] or r["aurora"] or r["rainbow"])


@node
def test_the_3d_drift_alone_draws_at_24_fps_and_the_pointer_wakes_it():
    r = run_node("""
      const rafs = [];
      global.requestAnimationFrame = (cb) => { rafs.push(cb); return rafs.length; };
      global.cancelAnimationFrame = () => {};
      const D = require("./shared/forge_depth.js");
      Object.assign(D, { ready: true, gl: {}, draw() {}, strength: 1, drift: () => true });
      D.frame(1000);
      const drifting = { raf: D.raf, timer: !!D.timer, rafs: rafs.length };
      D.point(0.5, 0);  // the pointer moves: back to full rate at once
      const woke = { raf: D.raf, timer: D.timer, rafs: rafs.length };
      D.stop();
      console.log(JSON.stringify({ drifting, woke }));
    """)
    assert r["drifting"] == {"raf": 0, "timer": True, "rafs": 0}
    assert r["woke"]["raf"] == 1 and r["woke"]["timer"] == 0


def test_the_hub_steps_its_slow_animations_and_pauses_hidden_ones():
    clock_rule = re.search(r"\.hero \.clock \{[^}]*\}", HUB)
    assert clock_rule
    clock = clock_rule.group(0)
    assert "steps(" in clock and "ease-in-out infinite" not in clock
    assert "body:not(.zen) #zen *" in HUB
    assert "body.ambient #home *" in HUB
    assert "animationTimingFunction = `steps(" in HUB
    orb_rule = re.search(r"\.wg-orb \{[^}]*\}", WIDGETS_CSS)
    assert orb_rule
    orb = orb_rule.group(0)
    assert "steps(" in orb


def test_the_visualisers_use_the_quick_easing_and_ask_60_levels_a_second():
    visual = HUB.split("const Visual = {")[1].split("/* --- background music")[0]
    assert "* 0.35" not in visual
    assert "ForgeVisual.follow(" in visual
    assert "fps: 60, fast" in visual
    assert "smoothingTimeConstant = 0.5" in visual
    assert "* 0.35" not in DESKTOP.split("levels() {")[1].split("ctx() {")[0]
    assert "ForgeVisual.follow(" in DESKTOP
