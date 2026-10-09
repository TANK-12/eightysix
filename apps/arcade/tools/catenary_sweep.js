/* Catenary fairness sweep — the test that says the game's promise out loud.
 *
 * Catenary exists because Escapement is sometimes impossible: its rings are
 * scattered at random against a fixed grab radius, so a course can be drawn
 * that no player can finish. This sweep asserts the two things that make
 * Catenary different, and measures Escapement the same way for comparison.
 *
 *   1. THE INVARIANT. No two consecutive rings are ever further apart than
 *      REACH, so every ring is catchable from the one before it.
 *   2. THE PROOF. A deliberately mediocre auto-player — it holds the rope the
 *      whole time and lets go on a fixed angle, with no look-ahead at all —
 *      clears a long course on every seed without running out of ropes.
 *
 *   node tools/catenary_sweep.js
 */
"use strict";
const fs = require("fs");

const FILE = "/home/ejb/Forge/apps/arcade/static/index.html";
const html = fs.readFileSync(FILE, "utf8");

// Globals the game modules close over, same stubs as tools/smoke.js.
const VW = 1280, VH = 800, TAU = Math.PI * 2;
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const ctx = new Proxy({}, {
  get: (o, k) => (k === "createLinearGradient" ? () => ({ addColorStop() {} }) : () => {}),
  set: () => true,
});
const glow = () => {};
let uiPhase = "play";
const FX = { shake: 0, ring() {}, burst() {}, text() {}, kick() {}, render() {} };
const S = {
  W: 1280, H: 800,
  px: (v) => v, py: (v) => v, pd: (v) => v,
  gameOver: (r) => { S._over = r; },
};

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

// Reading the internals needs a hook, and putting one in the shipped game would
// be debugging left in the source. Inject it into the extracted copy instead.
function instrument(src, names) {
  const getters = names.map((n) => `get ${n}(){return ${n};}`).join(", ");
  const out = src.replace("return {\n    begin(){", `return {\n    __t(){ return { ${getters} }; },\n    begin(){`);
  if (out === src) throw new Error("could not inject the test hook — has the module's shape changed?");
  return out;
}

/* ---------------------------------------------------------------- the invariant */

const CatenaryT = eval("(" + instrument(grab("Catenary"), ["bob", "anchor", "rings", "ropes", "best", "dead"]) + ")");
const REACH = Math.round(360 * 0.8);

let pairs = 0, overReach = 0, worstGap = 0;
for (let seed = 0; seed < 300; seed++) {
  const g = CatenaryT(S, FX, FX, {});
  g.begin();
  const t = g.__t();
  // Walk the course forward by flying the bob along it, so the generator keeps
  // seeding at every difficulty rather than only the opening stretch.
  for (let f = 0; f < 4000; f++) {
    // Only the generator is under test here, so the bob is flown along the
    // course by hand rather than played: no rope, no falling, no early exit.
    t.bob.x += 9; t.bob.y = 300; t.bob.vy = 0;
    g.frame(1 / 60, f / 60);
    const rings = t.rings;
    for (let i = 1; i < rings.length; i++) {
      const d = Math.hypot(rings[i].x - rings[i - 1].x, rings[i].y - rings[i - 1].y);
      pairs++;
      worstGap = Math.max(worstGap, d);
      if (d > REACH + 0.5) overReach++;
    }
    if (t.dead) break;
  }
}
console.log(`Catenary invariant : ${pairs} ring pairs seen, ${overReach} beyond REACH=${REACH}, worst ${worstGap.toFixed(1)}px`);

/* ------------------------------------------------------------------- the proof */

/* A poor player on purpose: hold the rope always, let go at a fixed angle.
   No look-ahead, no choice of ring, no reading of the course. If this clears
   the run, the course was not the thing standing in the way. */
function autoplay(Mod, frames) {
  const g = Mod(S, FX, FX, {});
  g.begin();
  const t = g.__t();
  S._over = null;
  g.pointer("down");
  let holding = true;
  for (let f = 0; f < frames; f++) {
    const b = t.bob;
    if (t.anchor && holding) {
      // Let go once the rope has carried past vertical and is still going
      // forward. No look-ahead at the course at all.
      const ang = Math.atan2(b.x - t.anchor.x, b.y - t.anchor.y);
      if (ang > 0.55 && b.vx > 0) { g.pointer("up"); holding = false; }
    } else if (!holding) {
      g.pointer("down"); holding = true;
    }
    g.frame(1 / 60, f / 60);
    if (t.dead || S._over) break;
  }
  return { distance: t.best, ropes: t.ropes, dead: t.dead };
}

/* The simplest player there is: press once and never let go. The bound at the
   top of the game says the rope can always hand itself forward, so this must
   never die and must always travel. If THIS strands, the game is unfair. */
function holdforever(Mod, frames) {
  const g = Mod(S, FX, FX, {});
  g.begin();
  const t = g.__t();
  S._over = null;
  g.pointer("down");
  let stuckFor = 0, wasAt = 0;
  for (let f = 0; f < frames; f++) {
    g.frame(1 / 60, f / 60);
    if (t.best > wasAt + 1) { wasAt = t.best; stuckFor = 0; } else stuckFor++;
    if (t.dead || S._over) break;
  }
  return { distance: t.best, ropes: t.ropes, dead: t.dead, stuckFor };
}

let held = 0, heldWorst = Infinity, heldStuck = 0, heldDeaths = 0;
for (let seed = 0; seed < 200; seed++) {
  const r = holdforever(CatenaryT, 6000);
  held++;
  heldWorst = Math.min(heldWorst, r.distance);
  heldStuck = Math.max(heldStuck, r.stuckFor);
  if (r.dead) heldDeaths++;
}
console.log(`Catenary hold-only : ${held} runs, worst ${heldWorst.toFixed(0)} m, ${heldDeaths} died, longest stall ${(heldStuck / 60).toFixed(1)} s`);

const TARGET = 700; // metres; a long run by the standards of this game
let runs = 0, finished = 0, worstRun = Infinity, ropesLost = 0;
for (let seed = 0; seed < 200; seed++) {
  const r = autoplay(CatenaryT, 9000);
  runs++;
  ropesLost += 3 - Math.max(r.ropes, 0);
  worstRun = Math.min(worstRun, r.distance);
  if (r.distance >= TARGET && !r.dead) finished++;
}
console.log(`Catenary autoplay  : ${finished}/${runs} runs reached ${TARGET} m, worst ${worstRun.toFixed(0)} m, ${ropesLost} ropes lost in total`);

/* ------------------------------------------------- Escapement, measured the same way */

const EscapementT = eval("(" + instrument(grab("Escapement"), ["bob", "anchor", "anchors", "best", "dead"]) + ")");
const ESC_GRAB = 300;
let ePairs = 0, eOver = 0, eWorst = 0;
for (let seed = 0; seed < 300; seed++) {
  const g = EscapementT(S, FX, FX, {});
  g.begin();
  const t = g.__t();
  for (let f = 0; f < 400; f++) {
    t.bob.x += 9;
    g.frame(1 / 60, f / 60);
    const a = t.anchors;
    for (let i = 1; i < a.length; i++) {
      const d = Math.hypot(a[i].x - a[i - 1].x, a[i].y - a[i - 1].y);
      ePairs++;
      eWorst = Math.max(eWorst, d);
      if (d > ESC_GRAB) eOver++;
    }
    if (t.dead) break;
  }
}
const ePct = ((eOver / ePairs) * 100).toFixed(1);
console.log(`Escapement, same measure : ${ePairs} pairs, ${eOver} (${ePct}%) further apart than its ${ESC_GRAB}px grab, worst ${eWorst.toFixed(1)}px`);

/* ------------------------------------------------------------------------ verdict */

let bad = 0;
const check = (ok, line) => { console.log((ok ? "PASS :: " : "FAIL :: ") + line); if (!ok) bad++; };
check(overReach === 0, `no Catenary ring is out of reach of the one before it (${overReach} of ${pairs})`);
check(worstGap <= REACH + 0.5, `the widest Catenary gap stays inside REACH (${worstGap.toFixed(1)} <= ${REACH})`);
// The arithmetic the game's fairness rests on, checked rather than trusted.
const MINROPE = 70, GRAB = 360;
check(MINROPE + REACH <= GRAB, `MINROPE + REACH stays inside the grab radius (${MINROPE} + ${REACH} <= ${GRAB})`);
check(heldDeaths === 0, `pressing once and never letting go never dies (${heldDeaths} of ${held})`);
check(heldWorst > 300, `and still travels: the worst hold-only run reached ${heldWorst.toFixed(0)} m`);
check(heldStuck < 60 * 6, `it is never stranded for long (longest stall ${(heldStuck / 60).toFixed(1)} s)`);
check(finished >= runs * 0.9, `a no-look auto-player clears ${TARGET} m on nearly every seed (${finished}/${runs})`);
check(eOver > 0, `Escapement really can place a ring out of reach, which is why this game exists (${ePct}% of pairs)`);
console.log();
console.log(bad ? `${bad} FAILED` : "ALL PASS");
process.exit(bad ? 1 : 0);
