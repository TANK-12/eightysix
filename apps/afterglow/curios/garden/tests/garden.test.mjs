// node --test curios/garden/ : the pure modules (lsys.js, words.js, sky.js and
// layoutGarden in draw.js). tests/test_agree.py checks Python against them.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { rng } from "../../_kit/rng.js";
import * as L from "../lsys.js";
import * as W from "../words.js";
import * as S from "../sky.js";
import { layoutGarden } from "../draw.js";

const here = new URL(".", import.meta.url);
const starters = JSON.parse(readFileSync(new URL("../starters.json", here), "utf8")).plants;
const HOUR = 3600000;
const T0 = Date.parse("2026-10-09T12:00:00+01:00");

/** A pleasant-or-odd genome from a seed, every field in the server's ranges. */
function randomGenome(seed) {
  const r = rng(seed);
  const pick = (xs) => xs[Math.floor(r() * xs.length)];
  const shapes = ["F[+X][-X]FX", "F[+X]F[-X]+X", "F-[[X]+X]+F[+FX]-X", "FF[+X][-X]F[+X]X", "F[+Y][-Y]FX", "FX", "[X]"];
  const rules = { X: [pick(shapes)] };
  if (r() < 0.6) rules.F = r() < 0.5 ? ["FF"] : ["FF", "F", "F[+F]F"];
  if (r() < 0.4) rules.Y = [pick(["F[-Y][+Y]FY", "FY", "F[+Y]FY"])];
  return {
    axiom: pick(["X", "FX", "F", "XY"]),
    rules,
    angle: 5 + r() * 55,
    len_decay: 0.5 + r() * 0.5,
    width_decay: 0.4 + r() * 0.6,
    jitter: r() * 20,
    bloom: r() * 0.6,
    hours_per_gen: 0.5 + r() * 47.5,
    hues: { stem: r() * 360, leaf: r() * 360, flower: r() * 360 },
    flower: pick(["star", "round", "bell", "spark"]),
    max_gen: 1 + Math.floor(r() * 7),
    seed: Math.floor(r() * 4294967296),
  };
}

const HOSTILE = [
  { axiom: "F", rules: { F: ["F".repeat(60)] }, max_gen: 7, seed: 1 },
  { axiom: "X".repeat(20), rules: { X: ["[X][X][X][X][X][X][X][X][X][X][X][X][X][X][X]"] }, max_gen: 50, seed: 2 },
  { axiom: "XYZ", rules: { X: ["XYZXYZXYZ"], Y: ["FZFZFZFZ", "ZZZZZZ"], Z: ["XFXFXF"] }, max_gen: 1000, seed: 3 },
  { axiom: "F", rules: { F: ["F+F-F[F]F"] }, max_gen: 1e9, seed: 4 },
];
const GENOMES = [...starters.map((p) => p.genome), ...Array.from({ length: 60 }, (_, i) => randomGenome(1000 + i))];

test("expand is deterministic and its fresh flags line up with the string", () => {
  for (const g of GENOMES) {
    for (let gen = 0; gen <= g.max_gen; gen++) {
      const a = L.expand(g, gen);
      const b = L.expand(structuredClone(g), gen);
      assert.equal(a.str, b.str);
      assert.deepEqual(a.fresh, b.fresh);
      assert.equal(a.fresh.length, a.str.length);
      assert.ok(a.gen <= gen);
    }
    assert.equal(L.expand(g, 0).str, g.axiom);
  }
});

test("expand never passes MAX_LEN or MAX_SEGMENTS, even for genomes built to explode", () => {
  for (const g of [...HOSTILE, ...GENOMES]) {
    const started = performance.now();
    const out = L.expand(g, Math.min(g.max_gen, 60));
    assert.ok(out.str.length <= L.MAX_LEN, `length ${out.str.length}`);
    assert.ok(L.countF(out.str) <= L.MAX_SEGMENTS, `segments ${L.countF(out.str)}`);
    assert.ok(performance.now() - started < 2000, "a hostile genome must stop quickly");
  }
  // the first hostile one: 1, 60, 3600 segments, then 216000 would pass the cap
  const f = L.expand(HOSTILE[0], 7);
  assert.equal(f.gen, 2);
  assert.equal(f.str.length, 3600);
});

test("effectiveMaxGen is the last generation within the caps, at most max_gen", () => {
  for (const g of [...HOSTILE, ...GENOMES]) {
    const top = L.effectiveMaxGen(g);
    assert.ok(top >= 0 && top <= g.max_gen);
    const at = L.expand(g, top);
    assert.equal(at.gen, top);
    if (top < g.max_gen) {
      // one more step would pass a cap: expand refuses it
      assert.equal(L.expand(g, top + 1).gen, top);
      // growing further than allowed just stays at the top generation
      assert.equal(L.expand(g, top + 3).str, at.str);
    }
  }
  for (const p of starters) assert.equal(L.effectiveMaxGen(p.genome), p.genome.max_gen, p.name);
  assert.equal(L.effectiveMaxGen({ ...GENOMES[0], max_gen: 0 }), 0);
});

test("hoursGrown follows a fixed clock: zero at planting, head start added, never negative", () => {
  const plant = { planted: new Date(T0).toISOString(), genome: { hours_per_gen: 8 } };
  assert.equal(L.hoursGrown(plant, T0), 0);
  assert.equal(L.hoursGrown(plant, T0 + 5 * HOUR), 5);
  assert.equal(L.hoursGrown({ ...plant, head_start_hours: 30 }, T0), 30);
  assert.equal(L.hoursGrown(plant, T0, 12), 12, "the days-ahead slider");
  assert.equal(L.hoursGrown(plant, T0 - 10 * HOUR), 0, "a clock behind the planting");
  assert.equal(L.hoursGrown({ ...plant, planted: "not a date" }, T0), 0);
  assert.ok(Number.isFinite(L.hoursGrown(plant, 8.64e15)));
  // an offset in the planting time is honoured
  assert.equal(L.hoursGrown({ ...plant, planted: "2026-10-09T12:00:00+03:00" }, T0), 2);
  assert.equal(L.hoursGrown({ ...plant, planted: "2026-10-09T10:00:00+00:00" }, T0), 1);
});

test("growthStage over real hours is monotonic, clamped and sensible at both ends", () => {
  for (const g of GENOMES.slice(0, 20)) {
    const top = L.effectiveMaxGen(g);
    const plant = { planted: new Date(T0).toISOString(), head_start_hours: 0, genome: g };
    assert.equal(L.growthStage(plant, T0, top), 0);
    let last = -1;
    for (let h = -24; h <= 24 * 60; h += 1.5) {
      const s = L.growthStage(plant, T0 + h * HOUR, top);
      assert.ok(s >= last, `stage went back at hour ${h}`);
      assert.ok(s >= 0 && s <= top);
      last = s;
    }
    assert.equal(L.growthStage(plant, T0 + 1e6 * HOUR, top), top, "far future is full grown");
    const hpg = Math.max(0.1, g.hours_per_gen);
    if (top >= 1) assert.ok(Math.abs(L.growthStage(plant, T0 + hpg * HOUR, top) - 1) < 1e-9);
  }
  const zero = { planted: new Date(T0).toISOString(), genome: { hours_per_gen: 0 } };
  assert.equal(L.growthStage(zero, T0 + 6 * HOUR, 5), 1, "a missing rate falls back to 6 hours");
});

test("stageParts and bloomOpen stay in range", () => {
  for (let max = 1; max <= 7; max++) {
    for (let s = 0; s <= max; s += 0.05) {
      const { gen, grow } = L.stageParts(s, max);
      assert.ok(gen >= 0 && gen <= max && grow > 0 && grow <= 1);
      const b = L.bloomOpen(s, max);
      assert.ok(b >= 0 && b <= 1);
    }
    assert.deepEqual(L.stageParts(max, max), { gen: max, grow: 1 });
  }
  assert.equal(L.bloomOpen(3, 0), 0);
});

function finiteAll(list) {
  for (const v of list) if (!Number.isFinite(v)) return false;
  return true;
}

test("turtle and plantGeometry give finite numbers, and the bounds hold the geometry", () => {
  for (const g of [...GENOMES, ...HOSTILE.map((h) => ({ ...randomGenome(7), ...h, max_gen: 7 }))]) {
    const top = Math.max(1, L.effectiveMaxGen(g));
    for (let s = 0; s <= top; s += 0.5) {
      const geo = L.plantGeometry(g, s, top);
      assert.ok(finiteAll([geo.minX, geo.maxX, geo.maxY, geo.maxSteps, geo.grow, geo.bloom]));
      assert.ok(geo.minX <= 0 && geo.maxX >= 0 && geo.maxY >= 0);
      for (const seg of geo.segs) {
        assert.ok(finiteAll(seg));
        for (let i = 0; i < seg.length; i += 5) {
          for (const [x, y] of [[seg[i], seg[i + 1]], [seg[i + 2], seg[i + 3]]]) {
            assert.ok(x >= geo.minX - 1e-9 && x <= geo.maxX + 1e-9 && y <= geo.maxY + 1e-9);
          }
        }
      }
      assert.ok(finiteAll(geo.buds));
      assert.equal(geo.buds.length % L.BUD, 0);
      for (let i = 0; i < geo.buds.length; i += L.BUD) {
        const [x, y] = [geo.buds[i], geo.buds[i + 1]];
        assert.ok(x >= geo.minX - 1e-9 && x <= geo.maxX + 1e-9 && y <= geo.maxY + 1e-9);
        assert.ok(geo.buds[i + 5] === 0 || geo.buds[i + 5] === 1);
      }
    }
    const fb = L.fullBounds(g, top);
    assert.ok(finiteAll([fb.minX, fb.maxX, fb.maxY]) && fb.maxY >= 1);
  }
});

test("a plant with no flowers to give blooms none, and bloom 0.6 gives some", () => {
  const g = { ...starters[1].genome };
  const none = L.plantGeometry({ ...g, bloom: 0 }, g.max_gen, g.max_gen);
  for (let i = 0; i < none.buds.length; i += L.BUD) assert.equal(none.buds[i + 5], 0);
  const many = L.plantGeometry({ ...g, bloom: 0.6 }, g.max_gen, g.max_gen);
  let flowers = 0;
  for (let i = 0; i < many.buds.length; i += L.BUD) flowers += many.buds[i + 5];
  assert.ok(flowers > 0);
});

test("crossName mixes the parents and stays a usable name for any input", () => {
  assert.equal(W.crossName("Ember fern", "Dusk willow"), "Ember willow");
  assert.equal(W.crossName("Moss", "moss"), "Moss the younger");
  assert.equal(W.crossName("Lantern", "Comet"), "Lantmet");
  assert.equal(W.crossName("", "  "), "Seedling");
  assert.equal(W.crossName("", "Wick tuft"), "Wick tuft");
  assert.equal(W.crossName("Spark", null), "Spark");
  const r = rng(125);
  const bits = ["Ember", "🌱", "a/b", 'say "hi"', "Ünïcode", "x".repeat(40), "🔥🔥🔥", "o'neil", "  ", "\\"];
  for (let i = 0; i < 2000; i++) {
    const make = () => Array.from({ length: 1 + Math.floor(r() * 4) }, () => bits[Math.floor(r() * bits.length)]).join(" ");
    const name = W.crossName(make(), make());
    const chars = Array.from(name);
    assert.ok(chars.length >= 1 && chars.length <= W.MAX_NAME, name);
    assert.equal(name, name.trim());
    assert.doesNotThrow(() => encodeURIComponent(name), "no half emoji left behind");
  }
});

test("suggestName is fixed by its seed", () => {
  assert.equal(W.suggestName(42), W.suggestName(42));
  assert.match(W.suggestName(7), /^[A-Z][a-z]+ [a-z]+$/);
});

test("genomeOk takes L-system strings with paired brackets and nothing else", () => {
  for (const ok of ["F", "X", "F[+X]F[-X]+X", "[[F]]", "+-"]) assert.equal(W.genomeOk(ok), true, ok);
  for (const bad of ["", "f", "F[", "]F[", "F ]", "F\n", "F1", "F{}", "Fé", "[]]["]) assert.equal(W.genomeOk(bad), false, bad);
});

test("parseRules and rulesText round trip, and junk gets a plain message", () => {
  const text = "X = F[+X]FX | F[-X]FX\nF = FF";
  const rules = W.parseRules(text);
  assert.deepEqual(rules, { X: ["F[+X]FX", "F[-X]FX"], F: ["FF"] });
  assert.equal(W.rulesText(rules), text);
  assert.deepEqual(W.parseRules(W.rulesText(rules)), rules);
  for (const p of starters) assert.deepEqual(W.parseRules(W.rulesText(p.genome.rules)), p.genome.rules, p.name);
  assert.deepEqual(W.parseRules("  X=F [+X] FX  \n\n"), { X: ["F[+X]FX"] });
  for (const junk of ["", "hello", "X = ", "x = F", "X = F[", "X = a|b", "X = F|F|F|F", `X = ${"F".repeat(61)}`, "W = F\nX = F\nY = F\nZ = F", "XY = F"]) {
    const out = W.parseRules(junk);
    assert.equal(typeof out, "string", `${JSON.stringify(junk)} should be refused`);
    assert.ok(out.length > 5 && out === out.trim());
  }
});

test("ageText and nextGrowthText read like plain words", () => {
  const cases = [
    [0, "just now"], [-5, "just now"], [NaN, "just now"], [Infinity, "just now"],
    [0.5, "30 minutes"], [1 / 60, "1 minute"], [0.999, "1 hour"], [1, "1 hour"],
    [5.5, "5 hours"], [24, "1 day"], [25, "1 day 1 hour"], [49, "2 days 1 hour"], [72, "3 days"],
  ];
  for (const [h, want] of cases) assert.equal(W.ageText(h), want, `ageText(${h})`);
  for (let h = 0; h < 24 * 10; h += 0.013) assert.match(W.ageText(h), /^(just now|\d+ minutes?|(\d+ days?)?( ?\d+ hours?)?)$/);
  assert.equal(W.nextGrowthText(5, 5, 8), null);
  assert.equal(W.nextGrowthText(2.5, 5, 8), "next generation in 4 hours");
  assert.equal(W.nextGrowthText(2, 5, 8), "next generation in 8 hours");
  assert.equal(W.nextGrowthText(0.98, 5, 1), "next generation in 1 minute");
  assert.equal(W.nextGrowthText(0.995, 5, 1), "next generation any minute now");
  for (let s = 0; s < 5; s += 0.001) assert.doesNotMatch(W.nextGrowthText(s, 5, 1), /just now|\b0 minutes/);
});

test("wrapHour folds any hour into 0-24", () => {
  const cases = [[0, 0], [-1, 23], [25, 1], [48, 0], [-24.5, 23.5], [23.75, 23.75], [NaN, 0], [Infinity, 0], ["7", 7]];
  for (const [h, want] of cases) assert.equal(S.wrapHour(h), want, `wrapHour(${h})`);
});

test("the sky changes smoothly all day, midnight included", () => {
  const step = 1 / 120; // half a minute
  let prev = S.skyAt(-step);
  for (let h = 0; h <= 24 + 1e-9; h += step) {
    const s = S.skyAt(h);
    for (const k of ["top", "mid", "low"]) {
      for (let i = 0; i < 3; i++) assert.ok(Math.abs(s[k][i] - prev[k][i]) <= 4, `${k} jumps at ${h.toFixed(3)}`);
      for (const v of s[k]) assert.ok(Number.isInteger(v) && v >= 0 && v <= 255);
    }
    for (const k of ["stars", "light", "glow"]) {
      assert.ok(Math.abs(s[k] - prev[k]) < 0.02, `${k} jumps at ${h.toFixed(3)}`);
      assert.ok(s[k] >= 0 && s[k] <= 1);
    }
    prev = s;
  }
  assert.deepEqual(S.skyAt(0), S.skyAt(24));
  assert.deepEqual(S.skyAt(-0.5), S.skyAt(23.5));
});

test("sun and moon rise and set smoothly and never both sit high", () => {
  const step = 1 / 60;
  let ps = S.sunAt(-step);
  let pm = S.sunAt(12 - step);
  for (let h = 0; h <= 24; h += step) {
    const sun = S.sunAt(h);
    const moon = S.sunAt(h + 12);
    for (const [now, before] of [[sun, ps], [moon, pm]]) {
      assert.ok(now.y >= 0 && now.y <= 1);
      assert.ok(Math.abs(now.y - before.y) < 0.01, `height jumps at ${h}`);
      if (now.up && before.up) assert.ok(Math.abs(now.x - before.x) < 0.01);
      if (now.up) assert.ok(now.x >= 0.08 - 1e-9 && now.x <= 0.92 + 1e-9);
    }
    assert.ok(!(sun.y > 0.5 && moon.y > 0.5));
    ps = sun;
    pm = moon;
  }
  assert.equal(S.sunAt(12.75).y, 1, "noon is the top of the arc");
  assert.equal(S.sunAt(2).up, false);
});

test("phaseName covers the whole day with the seven phases in order", () => {
  const seen = [];
  for (let h = 0; h < 24; h += 0.05) {
    const name = S.phaseName(h);
    assert.ok(name && name === S.phaseName(h + 24) && name === S.phaseName(h - 48));
    if (seen[seen.length - 1] !== name) seen.push(name);
  }
  assert.deepEqual(seen, [
    "Night, the garden asleep", "Dawn", "Morning", "Afternoon", "Evening", "Dusk, the afterglow hour", "Night, fireflies out",
  ]);
  assert.equal(S.skyAt(19.5).phase, "Dusk, the afterglow hour");
  assert.equal(S.skyAt(2).night, true);
  assert.equal(S.skyAt(12).night, false);
});

test("layoutGarden gives every plant its own slot and fits it under the sky", () => {
  const plants = GENOMES.slice(0, 12).map((genome) => ({ genome, bounds: L.fullBounds(genome, Math.max(1, L.effectiveMaxGen(genome))) }));
  for (const [w, h, n] of [[1400, 700, 4], [800, 500, 12], [320, 400, 3], [1400, 700, 1]]) {
    const lay = layoutGarden(plants.slice(0, n), w, h);
    assert.ok(lay.ground > 0 && lay.ground < h);
    assert.equal(lay.spots.length, n);
    lay.spots.forEach((s, i) => {
      assert.ok(Number.isFinite(s.scale) && s.scale > 0);
      assert.ok(s.height <= lay.tall + 1e-6);
      assert.ok(s.x1 - s.x0 >= 150 - 1e-9);
      if (i) assert.ok(Math.abs(s.x0 - lay.spots[i - 1].x1) < 1e-9, "slots touch, never overlap");
    });
    assert.ok(lay.rowWidth >= w);
  }
  assert.deepEqual(layoutGarden([], 800, 500).spots, []);
});
