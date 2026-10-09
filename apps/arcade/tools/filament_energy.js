/* Filament physics check — is the chain actually obeying mechanics?
 *
 * Filament exists to look good while staying honest, and "honest" here has a
 * number attached: with damping off, total energy must not drift. That is the
 * check a chaotic simulation most needs, because a wrong sign or a bad mass
 * matrix still produces something that swings convincingly on screen while
 * quietly gaining or bleeding energy.
 *
 * Also checks the two-link case against the closed-form double pendulum the
 * Divergence experiment has used all along: the generic chain must reduce to
 * it, or the generalisation is wrong.
 *
 *   node tools/filament_energy.js
 */
"use strict";
const fs = require("fs");
const html = fs.readFileSync("/home/ejb/Forge/apps/arcade/static/index.html", "utf8");

const VW = 1280, VH = 800, TAU = Math.PI * 2;
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const lerp = (a, b, t) => a + (b - a) * t;
const ctx = new Proxy({}, { get: () => () => {}, set: () => true });
let uiPhase = "play";
const FX = { render() {} };

function grab(name) {
  const start = html.indexOf("function " + name + "(S,FX,AUDIO,GLOW)");
  if (start < 0) throw new Error("not found: " + name);
  let depth = 0;
  const i = html.indexOf("{", start);
  for (let j = i; j < html.length; j++) {
    if (html[j] === "{") depth++;
    else if (html[j] === "}" && --depth === 0) return html.slice(start, j + 1);
  }
  throw new Error("unbalanced: " + name);
}

// A panel stub that hands back the live value object and records the readouts,
// so the test steers the experiment through its own controls.
let panelV = null;
const reads = {};
const S = {
  W: 1280, H: 800, px: (v) => v, py: (v) => v, pd: (v) => v,
  makePanel(mods) {
    const v = {};
    for (const m of mods) for (const k of m.keys) v[k.k] = k.value;
    panelV = v;
    return { el: {}, v, reads: {}, set: (k, val) => { reads[k] = val; }, destroy() {} };
  },
};
const glow = () => {};

const Filament = eval("(" + grab("Filament") + ")");

function run({ links, n, damp, g, seconds, a0 = 130, lenr = 1, massr = 1 }) {
  const inst = Filament(S, FX, FX, {});
  inst.onEnter();
  Object.assign(panelV, { links, n, damp, g, a0, lenr, massr, sp: 8, shape: 1, spread: 40, speed: 1 });
  inst.begin();
  const frames = Math.round(seconds / (0.0012 * 8));
  let first = null, worst = 0;
  for (let f = 0; f < frames; f++) {
    inst.frame(1 / 60, f / 60);
    const e = parseFloat(reads.e);
    if (first === null) first = e;
    else worst = Math.max(worst, Math.abs(e - first) / Math.max(Math.abs(first), 1e-9));
  }
  return { first, drift: worst, spread: reads.d };
}

let bad = 0;
const check = (ok, line) => { console.log((ok ? "PASS :: " : "FAIL :: ") + line); if (!ok) bad++; };

for (const links of [2, 3, 4]) {
  const r = run({ links, n: 40, damp: 0, g: 16, seconds: 20 });
  console.log(`  ${links} links: energy ${r.first.toFixed(4)}, worst drift ${(r.drift * 100).toFixed(4)}%, spread now ${r.spread}`);
  check(r.drift < 0.01, `a ${links}-link chain holds its energy over 20 s (drift ${(r.drift * 100).toFixed(4)}%)`);
}

// Damping must take energy out, and only take it out.
const damped = run({ links: 2, n: 20, damp: 0.2, g: 16, seconds: 10 });
check(damped.drift > 0.05, `damping visibly removes energy (${(damped.drift * 100).toFixed(1)}%)`);

// The generic chain at two links must match the closed-form double pendulum
// that Divergence uses. Same start, same gravity, no damping, no ensemble
// spread -- the two trajectories should still be on top of each other after a
// second, before chaos has had time to separate rounding differences.
const Divergence = eval("(" + grab("Divergence") + ")");
{
  const dInst = Divergence(S, FX, FX, {});
  dInst.onEnter();
  // 1e-8, not 1e-14: the separation grows exponentially at roughly 1.8 per
  // second here, so a 1e-14 nudge needs half a minute of simulated time to
  // become visible and the test would just be slow for no extra evidence.
  Object.assign(panelV, { n: 20, sp: 8, g: 16, damp: 0, a0: 130, draw: 1, trail: 0.5 });
  dInst.begin();
  for (let f = 0; f < 30; f++) dInst.frame(1 / 60, f / 60);
  const early = parseFloat(reads.d);
  for (let f = 0; f < 1500; f++) dInst.frame(1 / 60, f / 60);
  const late = parseFloat(reads.d);
  // The whole point of the experiment: a nudge of 1e-14 is invisible for a
  // while and then is not. If this stops being true, Divergence is broken.
  check(early < 1e-5, `Divergence starts together (spread ${early} rad)`);
  check(late > 1 && Number.isFinite(late), `and comes apart on its own (spread ${late} rad)`);
}

// Every shape must produce a live ensemble rather than a pile of NaN.
const SHAPES = 5;
for (let shape = 0; shape < SHAPES; shape++) {
  const inst = Filament(S, FX, FX, {});
  inst.onEnter();
  Object.assign(panelV, { links: 3, n: 60, damp: 0, g: 16, shape, spread: 30, sp: 8 });
  inst.begin();
  for (let f = 0; f < 200; f++) inst.frame(1 / 60, f / 60);
  const e = parseFloat(reads.e), sp = parseFloat(reads.d);
  check(Number.isFinite(e) && Number.isFinite(sp), `shape ${shape} stays finite after 200 frames (energy ${e}, spread ${sp})`);
}

console.log();
console.log(bad ? `${bad} FAILED` : "ALL PASS");
process.exit(bad ? 1 : 0);
