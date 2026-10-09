// Node stand-ins for a page, so tests/test_desktop_v2.py can run the shared
// particles, visualiser and widget code without a browser:
//   node tests/desktop_v2_node.js <check>   prints one JSON result
// The 2D context records its calls; Math.random is seeded, so two runs agree.
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
let seed = 7;
Math.random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const calls = {};
const ctx2d = () => new Proxy({}, {
  get(o, k) {
    if (k in o) return o[k];
    if (typeof k !== "string") return undefined;
    if (k === "roundRect") return undefined; // the fallback path
    return (...a) => {
      calls[k] = (calls[k] || 0) + 1;
      for (const x of a) if (typeof x === "number" && !Number.isFinite(x)) calls.nonFinite = (calls.nonFinite || 0) + 1;
      return { addColorStop() {} };
    };
  },
  set(o, k, v) { o[k] = v; return true; },
});
const canvas = () => ({ width: 0, height: 0, dataset: {}, getContext: () => ctx2d(), clientWidth: 400, clientHeight: 200 });
global.innerWidth = 1920; global.innerHeight = 1080;
global.window = global;
global.addEventListener = () => {};
const listeners = {};
global.document = {
  hidden: false,
  body: { classList: { toggle() {}, contains() { return false; } } },
  getElementById: () => global.__canvas || (global.__canvas = canvas()),
  createElement: () => canvas(),
  addEventListener: (type, fn) => (listeners[type] = listeners[type] || []).push(fn),
  dispatchEvent: (e) => (listeners[e.type] || []).forEach((fn) => fn(e)),
};
let rafs = 0;
global.requestAnimationFrame = () => ++rafs;
global.cancelAnimationFrame = () => {};
global.performance = require("perf_hooks").performance;
const src = require("fs").readFileSync(path.join(ROOT, "shared/forge_particles.js"), "utf8");
new Function(src + "\nglobal.Particles = Particles;")();
require(path.join(ROOT, "shared/forge_visual.js"));
const P = global.Particles;
const theme = { accent: "#8ab4ff", particle_fps: 60 };
P.look = () => theme;

// run `kind` for `seconds` at `fps`, the frames fed by hand
function run(kind, fps, seconds) {
  seed = 7;
  theme.particles = kind;
  P.built = ""; P.last = 0; P.drawn = 0;
  P.init(); P.apply();
  const start = P.dots.map((d) => [d.x, d.y]);
  let t = 1000;
  for (let i = 0; i < fps * seconds; i++) { t += 1000 / fps; P.frame(t); }
  return { start, dots: P.dots };
}
const checks = {
  // every kind draws without throwing and without NaN coordinates, at 60, 30 and 12 fps
  kinds() {
    const out = {};
    for (const kind of Object.keys(P.KINDS)) {
      for (const fps of [60, 30, 12]) {
        for (const k in calls) delete calls[k];
        let err = "";
        try { run(kind, fps, 2); } catch (e) { err = String(e); }
        out[`${kind}@${fps}`] = { err, nonFinite: calls.nonFinite || 0, draws: (calls.drawImage || 0) + (calls.stroke || 0) + (calls.fill || 0) };
      }
    }
    return out;
  },
  // the same second of motion at 60 and at 20 frames a second: how far the
  // dots travel on average (soft drift, which is never respawned in 1 s)
  speed() {
    const out = {};
    for (const kind of ["soft", "embers", "snow", "dust", "petals", "fireflies"]) {
      const far = (fps) => {
        const r = run(kind, fps, 1);
        let sum = 0, n = 0;
        r.dots.forEach((d, i) => { const [x, y] = r.start[i]; const m = Math.hypot(d.x - x, d.y - y); if (m < 400) { sum += m; n++; } });
        return sum / Math.max(1, n);
      };
      out[kind] = { at60: far(60), at20: far(20), at5: far(5) };
    }
    return out;
  },
  // draw calls in a steady frame for every visualiser style
  visual() {
    const out = {}, v = new Float32Array(32).fill(0.5);
    for (const s of ForgeVisual.names()) {
      // a first frame makes the cached sprites; the second is the steady cost
      ForgeVisual.draw(ctx2d(), 1920, 1080, s, v, { accent: "#8ab4ff", accent2: "#ff9ad5", st: {} });
      for (const k in calls) delete calls[k];
      const ok = ForgeVisual.draw(ctx2d(), 1920, 1080, s, v, { accent: "#8ab4ff", accent2: "#ff9ad5", st: {} });
      out[s] = { ok, calls: Object.assign({}, calls) };
    }
    return out;
  },
  // hidden: no frame is asked for; shown again: one is, and the first frame after counts as an ordinary one
  hidden() {
    theme.particles = "embers";
    P.init(); P.apply();
    const before = P.raf;
    document.hidden = true;
    document.dispatchEvent({ type: "visibilitychange" });
    const whileHidden = P.raf, running = P.canvas.dataset.running;
    document.hidden = false;
    document.dispatchEvent({ type: "visibilitychange" });
    const after = P.raf;
    P.frame(999999);
    return { before: !!before, whileHidden: !!whileHidden, running, after: !!after, kAfterRest: P.k };
  },
  // a particle amount of 0 asks for no frames
  amount0() {
    theme.particles = "embers"; theme.particle_amount = 0;
    P.built = ""; P.init(); P.apply();
    const r = { dots: P.dots.length, running: P.canvas.dataset.running };
    delete theme.particle_amount;
    return r;
  },
  // the shared power tier: reduced = 60% of the dots at 30 fps at most; paused = nothing
  tier() {
    theme.particles = "embers"; theme.particle_fps = 60; delete theme.power_tier;
    P.built = ""; P.init(); P.apply();
    const frames = () => { let n = 0, t = 50000; P.drawn = 0; P.last = 0; for (let i = 0; i < 60; i++) { t += 1000 / 60; const d = P.drawn; P.frame(t); if (P.drawn !== d) n++; } return n; };
    const fullDots = P.dots.length, fullFrames = frames();
    theme.power_tier = "reduced: GPU busy"; document.dispatchEvent({ type: "forge-power" });
    const reducedDots = P.dots.length, reducedFrames = frames();
    theme.power_tier = "paused: hidden"; document.dispatchEvent({ type: "forge-power" });
    const pausedRunning = P.canvas.dataset.running, pausedRaf = !!P.raf;
    theme.power_tier = "full"; document.dispatchEvent({ type: "forge-power" });
    const backRunning = P.canvas.dataset.running;
    delete theme.power_tier;
    return { fullDots, fullFrames, reducedDots, reducedFrames, pausedRunning, pausedRaf, backRunning };
  },
};
console.log(JSON.stringify(checks[process.argv[2]]()));
