// node --test curios/attractors/ : the pure logic, checked against the same
// vectors.json the Python tests read, so JS and Python must agree.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { rng } from "../../_kit/rng.js";
import * as S from "../sprott.js";
import * as R from "../render.js";
import * as F from "../finds.js";

const here = new URL(".", import.meta.url);
const V = JSON.parse(readFileSync(new URL("vectors.json", here), "utf8"));
const close = (a, b, tol, msg) => {
  if (a === null || b === null) return assert.equal(a, b, msg);
  assert.ok(Math.abs(a - b) <= tol, `${msg}: ${a} vs ${b}`);
};

test("the kit's rng gives the same stream as Python's mulberry32", () => {
  const r = rng(1);
  for (const want of V.rng_seed_1) assert.equal(r(), want);
});

test("named cases agree with Python: status, exponent, dimension, words", () => {
  for (const c of V.cases) {
    const t = S.tryCode(c.code);
    assert.equal(t.result.status, c.status, c.code);
    assert.equal(t.result.at, c.at, `${c.code} at`);
    close(t.result.lyapunov, c.lyapunov, V.tolerance.lyapunov, `${c.code} lyapunov`);
    close(t.dimension, c.dimension, V.tolerance.dimension, `${c.code} dimension`);
    assert.deepEqual(S.describe(t.result.lyapunov, t.dimension), c.describe, c.code);
  }
});

test("Sprott's FIRCDERRPVLD is chaotic, all-zero settles, all-Y escapes", () => {
  const f = S.tryCode("FIRCDERRPVLD");
  assert.equal(f.result.status, "chaotic");
  assert.ok(f.result.lyapunov > S.CHAOS);
  assert.ok(f.accepted);
  assert.equal(S.tryCode("MMMMMMMMMMMM").result.status, "fixed");
  assert.equal(S.tryCode("MMMMMMMMMMMM").accepted, false);
  assert.equal(S.tryCode("YYYYYYYYYYYY").result.status, "escapes");
});

test("every status has an example and none of the rejects is accepted", () => {
  const kinds = new Set(V.cases.map((c) => c.status));
  for (const k of ["chaotic", "loop", "cycle", "fixed", "escapes"]) assert.ok(kinds.has(k), k);
  for (const c of V.cases.filter((c) => c.status !== "chaotic")) assert.equal(S.tryCode(c.code).accepted, false, c.code);
});

test("sweep of 400 random codes: JS matches Python on every one", () => {
  assert.equal(V.sweep.length, 400);
  for (const s of V.sweep) {
    const t = S.tryCode(s.code);
    assert.equal(t.result.status, s.status, s.code);
    assert.equal(t.accepted, s.accepted, `${s.code} accepted`);
    close(t.result.lyapunov, s.lyapunov, V.tolerance.lyapunov, `${s.code} lyapunov`);
    close(t.dimension, s.dimension, V.tolerance.dimension, `${s.code} dimension`);
    // the rule itself, on every case
    if (t.accepted) assert.ok(t.result.lyapunov > S.CHAOS && t.dimension >= S.MIN_DIMENSION);
    if (t.result.status === "chaotic") assert.ok(t.result.lyapunov > S.CHAOS);
    else if (t.result.lyapunov !== null) assert.ok(t.result.lyapunov <= S.CHAOS);
  }
});

test("hunt with a seed finds what Python's hunt finds", () => {
  for (const h of V.hunts) {
    const f = S.hunt(h.seed);
    assert.equal(f.code, h.code, `seed ${h.seed}`);
    assert.equal(f.tried, h.tried, `seed ${h.seed} tried`);
  }
});

test("hunt gives up with null when nothing qualifies", () => {
  assert.equal(S.hunt(1, { maxTries: 3, minDimension: 5 }), null);
});

test("codes: decode, encode, isCode, letters and grid", () => {
  assert.deepEqual(S.decode("AMY" + "M".repeat(9)).slice(0, 3), [-1.2, 0, 1.2]);
  assert.equal(S.encode(S.decode("FIRCDERRPVLD")), "FIRCDERRPVLD");
  assert.equal(S.encode(S.decode("fircderrpvld")), "FIRCDERRPVLD");
  assert.equal(S.encode([5, -5, 0.04, 0.06, -0.05, 0, 0, 0, 0, 0, 0, NaN]), "YAMNMMMMMMMM");
  for (const bad of ["", "ABC", "FIRCDERRPVLDX", "FIRCDERRPVLZ", "FIRCDERRPV1D", null, 12, undefined]) {
    assert.equal(S.isCode(bad), false, String(bad));
    assert.throws(() => S.decode(bad));
  }
  assert.ok(S.isCode(" FIRCDERRPVLD "));
  assert.equal(S.letterValue("M"), 0);
  assert.ok(Number.isNaN(S.letterValue("Z")));
  assert.ok(Number.isNaN(S.letterValue("AB")));
  assert.ok(S.onGrid(S.decode("FIRCDERRPVLD")));
  assert.equal(S.onGrid([0.05, ...Array(11).fill(0)]), false);
  assert.equal(S.onGrid([1.3, ...Array(11).fill(0)]), false);
});

test("step is the quadratic map", () => {
  const a = [1, 2, 3, 4, 5, 6, -1, -2, -3, -4, -5, -6];
  const [x, y] = S.step(a, 0.5, -1);
  assert.equal(x, 1 + 2 * 0.5 + 3 * 0.25 + 4 * -0.5 + 5 * -1 + 6 * 1);
  assert.equal(y, -(1 + 2 * 0.5 + 3 * 0.25 + 4 * -0.5 + 5 * -1 + 6 * 1));
});

test("analyse catches NaN and Infinity as escapes", () => {
  assert.equal(S.analyse([NaN, ...Array(11).fill(0)]).status, "escapes");
  assert.equal(S.analyse([Infinity, ...Array(11).fill(0)]).status, "escapes");
});

test("dimension is null on too few points or a flat set", () => {
  assert.equal(S.dimension([[0, 0]], [0, 1, 0, 1]), null);
  assert.equal(S.dimension(Array(100).fill([1, 1]), [1, 1, 1, 1]), null);
  assert.equal(S.dimension([], null), null);
  // points on a line measure close to 1
  const line = Array.from({ length: 800 }, (_, i) => [i / 799, 0.5]);
  close(S.dimension(line, [0, 1, 0.5, 0.5]), 1, 0.05, "line");
});

test("palettes in JS match palettes.json that Python reads", () => {
  const json = JSON.parse(readFileSync(new URL("../palettes.json", here), "utf8"));
  assert.deepEqual(R.PALETTES, json);
  assert.equal(R.paletteOf("nope"), R.PALETTES.ember);
});

test("ramp and lut: ends are the first and last stops, packed little-endian", () => {
  const stops = R.PALETTES.ice.stops;
  assert.deepEqual(R.ramp(stops, 0), stops[0]);
  assert.deepEqual(R.ramp(stops, 1), stops[stops.length - 1]);
  assert.deepEqual(R.ramp(stops, -3), stops[0]);
  assert.deepEqual(R.ramp(stops, 7), stops[stops.length - 1]);
  const lut = R.paletteLut("ice");
  const bytes = new Uint8Array(lut.buffer);
  assert.deepEqual([...bytes.slice(0, 4)], [...stops[0], 255]);
  assert.equal(R.background("ink"), "rgb(240, 232, 216)");
});

test("toneIndex: zero is background, the peak is full, it never goes down", () => {
  assert.equal(R.toneIndex(0, 100), 0);
  assert.equal(R.toneIndex(5, 0), 0);
  assert.equal(R.toneIndex(100, 100, { exposure: 1, gamma: 1 }), 255);
  assert.equal(R.toneIndex(1e9, 100), 255);
  let prev = 0;
  for (let c = 1; c <= 1000; c++) {
    const v = R.toneIndex(c, 1000, { exposure: 0.8, gamma: 1.7 });
    assert.ok(v >= prev && v <= 255);
    prev = v;
  }
  assert.ok(R.toneIndex(10, 1000, { fade: 0.2 }) < R.toneIndex(10, 1000));
});

test("fitView puts the bounds inside the rectangle, centred, y up", () => {
  const rect = { x: 100, y: 0, w: 400, h: 200 };
  const v = R.fitView([-1, 1, -2, 2], rect, 0.1);
  const px = (x) => v.ox + x * v.s;
  const py = (y) => v.oy - y * v.s;
  assert.ok(px(-1) >= rect.x && px(1) <= rect.x + rect.w);
  assert.ok(py(2) >= rect.y && py(-2) <= rect.y + rect.h);
  close(px(0), 300, 1e-9, "centre x");
  close(py(0), 100, 1e-9, "centre y");
  assert.ok(py(1) < py(0), "y points up");
  const flat = R.fitView([0.3, 0.3, 0.3, 0.3], rect);
  assert.ok(Number.isFinite(flat.s) && flat.s > 0);
});

test("Density counts every point that lands, tracks max, and decays to nothing", () => {
  const d = new R.Density(64, 40);
  const a = S.decode("FIRCDERRPVLD");
  const info = S.analyse(a);
  d.setMap(a, info.sample.at(-1));
  d.setView(R.fitView(info.bounds, { x: 0, y: 0, w: 64, h: 40 }));
  assert.equal(d.accumulate(50000), 50000);
  const sum = d.hist.reduce((s, c) => s + c, 0);
  assert.ok(sum > 49000 && sum <= 50000, `landed ${sum}`);
  assert.equal(d.max, Math.max(...d.hist));
  assert.equal(d.total, 50000);
  for (let i = 0; i < 40; i++) d.decay(2);
  assert.equal(d.max, 0);
  assert.equal(d.hist.reduce((s, c) => s + c, 0), 0);
  d.clear();
  assert.equal(d.total, 0);
});

test("Density stops and says so when the orbit escapes", () => {
  const d = new R.Density(10, 10);
  d.setMap(S.decode("YYYYYYYYYYYY"));
  const n = d.accumulate(1000);
  assert.ok(d.lost);
  assert.ok(n < 1000);
});

test("toneMap: empty pixels are background, LUT path and direct path agree past 65535", () => {
  const d = new R.Density(4, 1);
  d.hist.set([0, 1, 70000, 100000]);
  d.max = 100000;
  const lut = R.paletteLut("ember");
  const out = new Uint32Array(4);
  R.toneMap(d, lut, out, { exposure: 1, gamma: 1 });
  assert.equal(out[0], lut[0]);
  assert.equal(out[3], lut[255]);
  assert.equal(out[2], lut[R.toneIndex(70000, 100000, { exposure: 1, gamma: 1 })]);
});

test("still fills the whole size with a picture that is not flat, under 30 ms", () => {
  const a = S.decode("JCFHLVWNJDLG");
  const info = S.analyse(a);
  const t0 = performance.now();
  const s = R.still(a, info.bounds, info.sample.at(-1), 640, 360, { points: 250000, palette: "dusk" });
  const ms = performance.now() - t0;
  assert.equal(s.pixels.length, 640 * 360 * 4);
  const seen = new Set();
  for (let i = 0; i < s.pixels.length; i += 4 * 97) seen.add(s.pixels[i] * 65536 + s.pixels[i + 1] * 256 + s.pixels[i + 2]);
  assert.ok(seen.size > 20, `only ${seen.size} colours`);
  assert.ok(ms < 30, `${ms} ms`);
});

test("recent finds: newest first, no repeats, capped; neighbour wraps", () => {
  let list = [];
  const codes = ["FIRCDERRPVLD", "JCFHLVWNJDLG", "HDWKWTHJNSEP", "FIRCDERRPVLD"];
  for (const c of codes) list = F.addRecent(list, { coeffs: S.decode(c) }, 3);
  assert.deepEqual(list.map((f) => S.encode(f.coeffs)), ["FIRCDERRPVLD", "HDWKWTHJNSEP", "JCFHLVWNJDLG"]);
  for (let i = 0; i < 10; i++) list = F.addRecent(list, { coeffs: [i / 10, ...Array(11).fill(0)] }, 3);
  assert.equal(list.length, 3);
  assert.equal(F.neighbour([], [0], 1), null);
  const l2 = codes.slice(0, 3).map((c) => ({ coeffs: S.decode(c) }));
  assert.equal(S.encode(F.neighbour(l2, l2[2].coeffs, 1).coeffs), codes[0]);
  assert.equal(S.encode(F.neighbour(l2, l2[0].coeffs, -1).coeffs), codes[2]);
  assert.equal(F.neighbour(l2, S.decode("MMMMMMMMMMMM"), 1), l2[0]);
});

test("codeLabel marks codes that are off the letter grid", () => {
  assert.equal(F.codeLabel(S.decode("FIRCDERRPVLD")), "FIRCDERRPVLD");
  const nudged = S.decode("FIRCDERRPVLD");
  nudged[0] += 0.03;
  assert.equal(F.codeLabel(nudged), "≈FIRCDERRPVLD");
});

test("keepsake data round-trips, and bad data falls back sensibly", () => {
  const coeffs = S.decode("HDWKWTHJNSEP");
  coeffs[4] += 0.013;
  const data = F.keepData({ coeffs, palette: "ice", exposure: 0.9, gamma: 2, lyapunov: 0.2, dimension: 1.3 });
  const json = JSON.parse(JSON.stringify(data));
  const back = F.settingsFrom(json);
  assert.deepEqual(back.coeffs, coeffs.map((v) => Number(v.toFixed(6))));
  assert.equal(back.palette, "ice");
  assert.equal(back.exposure, 0.9);
  assert.equal(back.gamma, 2);
  const fromCode = F.settingsFrom({ code: "FIRCDERRPVLD", palette: "nope", exposure: 99, gamma: "x" });
  assert.deepEqual(fromCode.coeffs, S.decode("FIRCDERRPVLD"));
  assert.equal(fromCode.palette, "ember");
  assert.equal(fromCode.exposure, F.LIMITS.exposure[1]);
  assert.equal(fromCode.gamma, F.DEFAULTS.gamma);
  assert.throws(() => F.settingsFrom(null));
  assert.throws(() => F.settingsFrom({ coeffs: [1, 2], code: "nope" }));
  assert.throws(() => F.settingsFrom({ coeffs: Array(12).fill(NaN) }));
  assert.equal(F.settingsFrom({ code: "FIRCDERRPVLD", palette: "constructor" }).palette, "ember");
});

test("every shipped seed opens and is chaotic with the exponent its note says", () => {
  const dir = new URL("../seeds/", here);
  const names = ["starburst-under-glass", "ice-halo", "clockwork-tent", "violet-boomerangs", "paper-lantern"];
  for (const n of names) {
    const raw = readFileSync(new URL(`${n}.json`, dir), "utf8");
    assert.ok(raw.length < 100000);
    const seed = JSON.parse(raw);
    assert.equal(seed.author, "Claude");
    assert.ok(seed.made.startsWith("2026-10-09T"));
    assert.ok(seed.name && seed.note);
    const s = F.settingsFrom(seed.data);
    const t = S.tryCode(S.encode(s.coeffs));
    assert.ok(t.accepted, n);
    close(t.result.lyapunov, seed.data.lyapunov, 1e-6, `${n} lyapunov`);
    assert.ok(seed.note.includes(t.result.lyapunov.toFixed(2)), `${n} note quotes the exponent`);
  }
});

test("drift moves while chaotic, turns back when not, hands over after 3 bounces", () => {
  const coeffs = S.decode("JCFHLVWNJDLG");
  let d = F.startDrift(coeffs, 2);
  let r = F.driftStep(d, coeffs, 0.5, 1, () => true);
  assert.ok(r.moved);
  assert.notEqual(r.coeffs[2], coeffs[2]);
  assert.deepEqual(r.coeffs.filter((_, i) => i !== 2), coeffs.filter((_, i) => i !== 2));
  assert.ok(Math.abs(r.coeffs[2] - coeffs[2]) <= d.amp + 1e-12);
  d = r.drift;
  r = F.driftStep(d, r.coeffs, 0.5, 1, () => false);
  assert.equal(r.moved, false);
  assert.equal(r.drift.dir, -d.dir);
  r = F.driftStep(r.drift, r.coeffs, 0.5, 1, () => false);
  r = F.driftStep(r.drift, r.coeffs, 0.5, 1, () => false);
  assert.equal(r.drift.k, 7);
  assert.equal(r.drift.bounces, 0);
  // with the real test, a long drift only ever shows chaotic maps
  let c = coeffs;
  d = F.startDrift(c, 4);
  const chaotic = (x) => S.analyse(x, { iterations: 4000, transient: 600, sample: 0 }).status === "chaotic";
  for (let i = 0; i < 200; i++) {
    r = F.driftStep(d, c, 0.05, 2, chaotic);
    d = r.drift;
    c = r.coeffs;
    assert.ok(chaotic(c));
    for (const v of c) assert.ok(v >= -1.2 && v <= 1.2);
  }
});

test("huntSlice tallies every try and stops at a find, a code cap or the clock", () => {
  const h = S.hunter(1);
  const tally = F.newTally();
  let found = null;
  let slices = 0;
  while (!found) {
    found = F.huntSlice(h, tally, { maxCodes: 4 }).found;
    slices += 1;
  }
  assert.equal(found.code, V.hunts[0].code);
  assert.equal(tally.tried, V.hunts[0].tried);
  assert.equal(tally.escapes + tally.fixed + tally.cycle + tally.loop + tally.chaotic, tally.tried);
  assert.ok(slices >= Math.ceil(tally.tried / 4));
  let clock = 0;
  const t2 = F.newTally();
  F.huntSlice(S.hunter(2), t2, { maxCodes: 100, budgetMs: 3, now: () => (clock += 2) });
  assert.equal(t2.tried, 2);
  assert.ok(F.tallyText(tally).startsWith(`Tried ${V.hunts[0].tried} codes: `));
  assert.equal(F.tallyText(F.newTally()), "");
  assert.equal(F.tallyText({ ...F.newTally(), tried: 1, escapes: 1 }), "Tried 1 code: 1 flew off.");
});
