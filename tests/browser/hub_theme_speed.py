"""How long a theme or effect change takes in the hub (2026-10-08).

    apps/dossier/.venv/bin/python tests/browser/hub_theme_speed.py [runs] [reps] [page]

Emerson: "the theme and effects reload, like all the app pills on the home
screen; see if you can make that faster". This loads a copy of the hub with
a snapshot of the real status.js and theme.js (the fixtures when those are
missing), then times applyTheme() for the changes the home screen and
Settings make: the whole theme sent again unchanged (what Settings and the
Wallpapers app post), one accent, one effect, the look, the icon style, the
text size. For each it reports the median of:

  js_ms      applyTheme itself
  style_ms   the style and layout it leaves for the browser (forced at once)
  frame_ms   from the call to the next painted frame
  mutations  DOM nodes and attributes changed (the home tiles and pills
             re-rendered show up here)
  steps      the slowest parts of applyTheme, ms each

then the home screen's entrance (Emerson: "the app icon and text bars, the
effect load in kind of thing"): ms from going home to the last pane settled,
and how opaque a tile is on the first frame. Last, a pass/fail check that
every change still reached the page and that no theme change replays the
entrance. Headless
Chrome draws in software, so the numbers compare a before and an after on
this laptop; they are not how Forge feels on screen. Prints one JSON object.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FORGE = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))

from cdp_driver import chrome_page, free_port, wait_http  # noqa: E402

WALLS = Path.home() / ".cache" / "forge" / "wallpaper"

MEASURE = r"""
(async (reps) => {
  window.webkit = { messageHandlers: { forge: { postMessage: () => {} } } };
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const frame = () => new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)));
  selectWorkspace(null, { instant: true });
  await wait(300);
  // the parts of applyTheme, timed each call
  const spent = {};
  const wrap = (owner, name, label) => {
    if (!owner || typeof owner[name] !== "function") return;
    const real = owner[name];
    owner[name] = function (...a) {
      const t = performance.now();
      try { return real.apply(this, a); } finally { spent[label] = (spent[label] || 0) + performance.now() - t; }
    };
  };
  const g = { applyPower, applyLook, applyChrome, fitDock, applyAppFlags, broadcastTheme, tick };
  // global function declarations are window properties, so these wrappers are what applyTheme calls
  for (const k of Object.keys(g)) wrap(window, k, k);
  wrap(window.ForgeGlass, "apply", "ForgeGlass.apply");
  wrap(window.ForgeText, "apply", "ForgeText.apply");
  wrap(window.ForgeWidgets, "apply", "ForgeWidgets.apply");
  wrap(window.ForgeIcons, "setStyle", "ForgeIcons.setStyle");
  wrap(Particles, "apply", "Particles.apply");
  wrap(Depth3D, "apply", "Depth3D.apply");
  wrap(WallFx, "apply", "WallFx.apply");
  wrap(Music, "apply", "Music.apply");
  wrap(Visual, "apply", "Visual.apply");
  let mutations = 0;
  const mo = new MutationObserver((list) => { for (const m of list) mutations += m.type === "childList" ? m.addedNodes.length + m.removedNodes.length : 1; });
  mo.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
  const base = JSON.parse(JSON.stringify(theme));
  const flip = (key, a, b) => (n) => ({ [key]: n % 2 ? b : a });
  const looks = Array.isArray(base.looks) && base.looks.length > 1 ? base.looks.map((l) => l.id || l) : ["classic", "glass"];
  const otherLook = looks.find((l) => l !== (base.look || "classic")) || "classic";
  const scenarios = {
    // Settings and the Wallpapers app post the whole theme back after a save
    whole_theme_same: () => base,
    whole_theme_accent: (n) => Object.assign({}, base, { accent: n % 2 ? "#ff7a59" : base.accent || "#6ea8fe" }),
    accent: (n) => ({ accent: n % 2 ? "#ff7a59" : base.accent || "#6ea8fe" }),
    particles: flip("particles", "soft", "off"),
    look: flip("look", base.look || "classic", otherLook),
    icon_style: flip("icon_style", "new", "classic"),
    text_scale: flip("text_scale", base.text_scale || 1, 1.3),
  };
  const med = (a) => { const s = a.slice().sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : 0; };
  const out = {};
  for (const [name, make] of Object.entries(scenarios)) {
    const js = [], style = [], fr = [], mut = [], steps = [];
    for (let n = 0; n < reps; n++) {
      const change = make(n);
      await frame();
      for (const k in spent) delete spent[k];
      mutations = 0;
      mo.takeRecords();
      const t0 = performance.now();
      applyTheme(change);
      const t1 = performance.now();
      document.body.getBoundingClientRect(); void document.body.offsetHeight;
      const t2 = performance.now();
      await frame();
      const t3 = performance.now();
      for (const m of mo.takeRecords()) mutations += m.type === "childList" ? m.addedNodes.length + m.removedNodes.length : 1;
      await wait(0);
      js.push(t1 - t0); style.push(t2 - t1); fr.push(t3 - t0); mut.push(mutations);
      steps.push(Object.assign({}, spent));
    }
    const keys = new Set(steps.flatMap((s) => Object.keys(s)));
    const stepMed = {};
    for (const k of keys) stepMed[k] = +med(steps.map((s) => s[k] || 0)).toFixed(3);
    const top = Object.fromEntries(Object.entries(stepMed).sort((a, b) => b[1] - a[1]).slice(0, 5));
    out[name] = { js_ms: +med(js).toFixed(2), style_ms: +med(style).toFixed(2), frame_ms: +med(fr).toFixed(2), mutations: med(mut), steps: top };
    applyTheme(base);
    await frame();
  }
  // every change still reaches the page
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const checks = {};
  applyTheme({ accent: "#123456" }); checks.accent = css("--accent") === "#123456";
  applyTheme({ look: otherLook }); checks.look = document.body.classList.contains(`look-${otherLook}`) && $("look-css").dataset.look === otherLook;
  applyTheme({ particles: "off" }); checks.particles_off = document.body.classList.contains("no-particles");
  applyTheme({ particles: "soft", animations: true }); checks.particles_on = !document.body.classList.contains("no-particles");
  applyTheme({ icon_style: "classic" }); checks.icons_classic = ForgeIcons.style() === "classic";
  applyTheme({ icon_style: "new" }); checks.icons_new = ForgeIcons.style() === "new";
  applyTheme({ text_scale: 1.3 }); checks.text_scale = css("--forge-text") === "1.3";
  applyTheme({ radius: 3 }); checks.radius = css("--radius") === "3px";
  applyTheme({ dock_size: 60 }); checks.dock_size = css("--dock-size") === "60px";
  applyTheme({ border: "none" }); checks.border = document.body.classList.contains("border-none");
  applyTheme({ shadows: false }); checks.shadows = document.body.classList.contains("no-shadow");
  applyTheme({ glass_style: "frosted" }); checks.glass = document.body.classList.contains("glass-frosted");
  applyTheme({ widgets: false }); checks.widgets_off = !!(window.ForgeWidgets && ForgeWidgets.on === false);
  applyTheme({ widgets: true }); checks.widgets_on = !!(window.ForgeWidgets && ForgeWidgets.on === true);
  applyTheme({ greeting: false }); checks.greeting = $("greet").hidden === true;
  applyTheme({ wall_3d: false, wallpaper: "/wall/none-a.jpg" }); checks.wallpaper = $("wall").style.backgroundImage.includes("none-a.jpg");
  applyTheme({ wallpaper: "/wall/none-b.jpg" }); checks.wallpaper_again = $("wall").style.backgroundImage.includes("none-b.jpg");
  const key = order.find((k) => parts[k] && !(theme.hidden_apps || []).includes(k));
  const hidden = (theme.hidden_apps || []).slice();
  applyTheme({ hidden_apps: hidden.concat([key]) }); checks.hide_app = parts[key].tile.classList.contains("is-hidden");
  applyTheme({ hidden_apps: hidden }); checks.show_app = !parts[key].tile.classList.contains("is-hidden");
  applyTheme({ dock: "always", auto_fullscreen: "off" }); checks.dock_always = document.body.classList.contains("dock-always");
  applyTheme({ dock: "hidden" }); checks.dock_hidden = !document.body.classList.contains("dock-always") && document.body.classList.contains("dock-hidden");
  applyTheme({ clock_24h: false }); checks.clock_12h = /am|pm/i.test($("clock").textContent);
  applyTheme({ clock_24h: true }); checks.clock_24h = !/am|pm/i.test($("clock").textContent);
  let sent = 0;
  const realSend = window.sendTheme;
  window.sendTheme = () => { sent++; };
  const frameEl = document.createElement("iframe");
  frameEl.src = "about:blank";
  const ws = document.createElement("div");
  ws.className = "workspace";
  ws.style.display = "none";
  ws.appendChild(frameEl);
  document.body.appendChild(ws);
  await wait(120);
  sent = 0; // a send queued by the checks above may land in that wait
  applyTheme({ accent: "#654321" });
  await wait(120);
  checks.broadcast_on_change = sent === 1;
  applyTheme(JSON.parse(JSON.stringify(theme)));
  await wait(120);
  checks.no_broadcast_when_same = sent === 1;
  ws.remove();
  window.sendTheme = realSend;
  applyTheme({ dim: 0.5 }); checks.dim = css("--dim") === "0.5";
  applyTheme({ animations: false }); checks.no_anim = document.body.classList.contains("no-anim");
  applyTheme({ animations: true }); checks.anim = !document.body.classList.contains("no-anim");
  // the home screen's entrance: from going home to the last pane settled
  const home = $("home");
  const entering = () => home.getAnimations({ subtree: true }).filter((a) => ["rise", "home-in"].includes(a.animationName));
  const settle = [], startOpacity = [];
  for (let n = 0; n < 5; n++) {
    await wait(900);
    const t0 = performance.now();
    playEntrance();
    await frame();
    const tile = home.querySelector(".section .tile:not(.grouped)");
    startOpacity.push(tile ? Number(getComputedStyle(tile).opacity) : 1);
    while (entering().some((a) => a.playState !== "finished") && performance.now() - t0 < 5000) await frame();
    settle.push(performance.now() - t0);
  }
  out.entrance = { settled_ms: +med(settle).toFixed(1), first_frame_tile_opacity: +med(startOpacity).toFixed(2), panes: entering().length };
  await wait(900);
  applyTheme({ accent: "#2468ac" }); applyTheme(JSON.parse(JSON.stringify(theme))); applyTheme({ particles: "off" });
  await frame();
  checks.theme_change_starts_no_entrance = entering().filter((a) => a.playState === "running").length === 0;
  out.checks = checks;
  out.all_checks_pass = Object.values(checks).every(Boolean);
  mo.disconnect();
  return JSON.stringify(out);
})
"""


def build(site: Path, page: Path) -> None:
    hub = site / "hub"
    hub.mkdir(parents=True)
    shutil.copy(page, hub / "index.html")
    if (FORGE / "hub" / "looks").is_dir():
        shutil.copytree(FORGE / "hub" / "looks", hub / "looks")
    real_status, real_theme = FORGE / "hub" / "status.js", FORGE / "hub" / "theme.js"
    shutil.copy(
        real_status if real_status.exists() else HERE / "hub_sections_status.js",
        hub / "status.js",
    )
    if real_theme.exists():
        # the wallpapers are served from /wall so the page can load them
        text = real_theme.read_text(encoding="utf-8")
        (hub / "theme.js").write_text(
            text.replace(WALLS.as_uri() + "/", "/wall/"), encoding="utf-8"
        )
    else:
        shutil.copy(HERE / "hub_immersive_theme.js", hub / "theme.js")
    (site / "shared").symlink_to(FORGE / "shared")
    if WALLS.is_dir():
        (site / "wall").symlink_to(WALLS)


async def one_run(site: Path, port: int, reps: int) -> dict:
    async with chrome_page(site, size="1400,900") as page:
        await page.go(f"http://127.0.0.1:{port}/hub/index.html")
        await page.wait(
            "typeof Particles === 'object' && typeof theme === 'object'", 10
        )
        await asyncio.sleep(1.0)
        return json.loads(await page.js(f"({MEASURE})({reps})"))


def main() -> None:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    # a third argument measures another copy of the page (a backup: the before)
    page = Path(sys.argv[3]) if len(sys.argv) > 3 else FORGE / "hub" / "index.html"
    with tempfile.TemporaryDirectory(prefix="hub-theme-speed-") as tmp:
        site = Path(tmp)
        build(site, page)
        port = free_port()
        server = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            cwd=site,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_http(f"http://127.0.0.1:{port}/hub/index.html")
            results = [asyncio.run(one_run(site, port, reps)) for _ in range(runs)]
        finally:
            server.terminate()
            server.wait(timeout=5)
    out: dict = {}
    for name, first in results[0].items():
        if not isinstance(first, dict) or "js_ms" not in first:
            continue
        out[name] = {
            k: round(statistics.median(r[name][k] for r in results), 2)
            for k in ("js_ms", "style_ms", "frame_ms", "mutations")
        }
        out[name]["steps"] = first["steps"]
    out["entrance"] = {
        k: round(statistics.median(r["entrance"][k] for r in results), 2)
        for k in results[0]["entrance"]
    }
    out["checks"] = {
        k: all(r["checks"][k] for r in results) for k in results[0]["checks"]
    }
    out["all_checks_pass"] = all(r["all_checks_pass"] for r in results)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
