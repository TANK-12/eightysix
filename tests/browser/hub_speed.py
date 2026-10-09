"""Speed numbers for the hub (B18): first paint, frame rate and the cost of
the home screen's animation loops, measured in headless Chrome.

    apps/dossier/.venv/bin/python tests/browser/hub_speed.py [runs]

Prints one JSON line of medians. Headless Chrome draws in software with no
GPU, so the numbers are for comparing before and after a change on this
laptop, not for how Forge feels on screen. Needs `websockets` in the venv.
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
sys.path.insert(0, str(HERE.parent))

from cdp_driver import chrome_page, free_port, wait_http  # noqa: E402

# Runs in the page after load: counts animation frames for two seconds and
# times each Particles and Visual frame, with each effect on its own.
MEASURE = """
(async () => {
  window.webkit = { messageHandlers: { forge: { postMessage: () => {} } } };
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const fcp = (performance.getEntriesByName("first-contentful-paint")[0] || {}).startTime || -1;
  const nav = performance.getEntriesByType("navigation")[0] || {};
  const timed = (obj, name) => {
    const real = obj[name], spent = [];
    obj[name] = function (...a) { const t = performance.now(); const r = real.apply(this, a); spent.push(performance.now() - t); return r; };
    return () => { obj[name] = real; return spent; };
  };
  const fps = async (ms) => {
    let n = 0, on = true;
    const f = () => { n++; if (on) requestAnimationFrame(f); };
    requestAnimationFrame(f);
    await wait(ms);
    on = false;
    return (n * 1000) / ms;
  };
  const avg = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);
  const out = { fcp_ms: fcp, dom_ready_ms: nav.domContentLoadedEventEnd || -1, load_ms: nav.loadEventEnd || -1 };
  selectWorkspace(null, { instant: true });
  for (const kind of ["soft", "emberstorm"]) {
    applyTheme(Object.assign({}, theme, { animations: true, particles: kind, particle_amount: 1, visualiser: "off" }));
    await wait(300);
    const stop = timed(Particles, "frame");
    out[`fps_${kind}`] = await fps(2000);
    const spent = stop();
    out[`particles_${kind}_ms`] = avg(spent);
  }
  applyTheme(Object.assign({}, theme, { animations: true, particles: "off", visualiser: "bars", visualiser_source: "system" }));
  Visual.levelsIn(Array.from({ length: 32 }, (_, i) => 0.3 + 0.5 * Math.abs(Math.sin(i))));
  await wait(300);
  const stopV = timed(Visual, "frame");
  out.fps_visualiser = await fps(2000);
  out.visualiser_ms = avg(stopV());
  applyTheme(Object.assign({}, theme, { animations: true, particles: "off", visualiser: "off" }));
  await wait(300);
  out.fps_idle = await fps(2000);
  return JSON.stringify(out);
})()
"""


def build(site: Path) -> None:
    hub = site / "hub"
    hub.mkdir(parents=True)
    shutil.copy(HERE.parent.parent / "hub" / "index.html", hub / "index.html")
    shutil.copy(HERE / "hub_sections_status.js", hub / "status.js")
    shutil.copy(HERE / "hub_immersive_theme.js", hub / "theme.js")
    # the hub loads ../shared/forge_particles.js (and friends)
    (site / "shared").symlink_to(HERE.parent.parent / "shared")


async def one_run(site: Path, port: int) -> dict:
    async with chrome_page(site, size="1400,900") as page:
        await page.go(f"http://127.0.0.1:{port}/hub/index.html")
        await page.wait(
            "typeof Particles === 'object' && typeof theme === 'object'", 10
        )
        await asyncio.sleep(0.5)
        return json.loads(await page.js(MEASURE))


def main() -> None:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    with tempfile.TemporaryDirectory(prefix="hub-speed-") as tmp:
        site = Path(tmp)
        build(site)
        port = free_port()
        server = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            cwd=site,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_http(f"http://127.0.0.1:{port}/hub/index.html")
            results = [asyncio.run(one_run(site, port)) for _ in range(runs)]
        finally:
            server.terminate()
            server.wait(timeout=5)
    medians = {
        k: round(statistics.median(r[k] for r in results), 2) for k in results[0]
    }
    print(json.dumps(medians))


if __name__ == "__main__":
    main()
