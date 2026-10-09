// The mountain and the rider, driven without a screen.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { World, DX, PX_PER_M, FEATURES, ropeY } from "../../static/js/world.js";
import { newRider, step, DEFAULTS, countFlips, landable, recover } from "../../static/js/rider.js";

const dir = new URL("../../data/shapes/", import.meta.url);
const shapes = {};
for (const f of readdirSync(dir)) shapes[f.replace(".json", "")] = { ...JSON.parse(readFileSync(new URL(f, dir))), id: f.replace(".json", "") };

const P = { ...DEFAULTS };
const DT = 1 / 60;

function ride(world, rider, frames, input = () => ({ pressed: false, held: false })) {
  const all = [];
  for (let i = 0; i < frames; i++) {
    world.ensure(rider.x + 3000);
    all.push(...step(rider, world, input(i), P, DT));
  }
  return all;
}

test("the same seed grows the same mountain", () => {
  const a = new World(7, shapes), b = new World(7, shapes);
  a.ensure(40000); b.ensure(40000);
  assert.deepEqual(a.ys.slice(0, 2000), b.ys.slice(0, 2000));
  assert.equal(a.items.length, b.items.length);
});

test("the mountain always goes downhill overall, and has no chasm in the first 400 m", () => {
  const w = new World(3, shapes);
  w.ensure(400 * PX_PER_M);
  assert.ok(w.chasms.length === 0);
  w.ensure(60000);
  assert.ok(w.y > 60000 * 0.15, "net descent");
  assert.ok(w.chasms.length > 0, "chasms appear later");
});

test("every rope hangs above ground and every coin is above the snow", () => {
  const w = new World(11, shapes);
  w.ensure(60000);
  assert.ok(w.ropes.length > 3);
  for (const r of w.ropes) {
    for (let x = r.x1; x <= r.x2; x += DX) {
      const g = w.groundAt(x);
      if (g !== null) assert.ok(ropeY(r, x) < g - 20, `rope clears ground at ${x}`);
    }
  }
  for (const c of w.items.filter((i) => i.type === "coin")) {
    const g = w.groundAt(c.x);
    if (g !== null) assert.ok(c.y < g, "coin above ground");
  }
});

test("every feature can be built", () => {
  for (const f of FEATURES) {
    const w = new World(5, shapes);
    for (let i = 0; i < 20; i++) f.build(w);
    assert.ok(w.ys.every(Number.isFinite), f.id);
  }
});

test("riding without input never crashes on the opening run and keeps speed", () => {
  const w = new World(1, shapes), r = newRider(w);
  const events = ride(w, r, 240);
  assert.ok(!events.some((e) => e.type === "crash"));
  assert.ok(r.speed >= P.min_speed);
  assert.ok(r.x > 200 + 240 * DT * P.min_speed * 0.9);
});

test("a held jump turns a backflip that lands and counts", () => {
  const w = new World(1, shapes), r = newRider(w);
  ride(w, r, 30);
  const flipFrames = Math.round((2 * Math.PI) / P.flip_speed / DT);
  let landed = null;
  for (let i = 0; i < 400 && !landed; i++) {
    const input = { pressed: i === 0, held: i > 0 && i <= flipFrames };
    const ev = step(r, w, input, { ...P, jump: 900 }, DT);
    landed = ev.find((e) => e.type === "land" || e.type === "crash");
  }
  assert.equal(landed.type, "land");
  assert.equal(landed.flips, 1);
});

test("half a flip is a crash", () => {
  const w = new World(1, shapes), r = newRider(w);
  ride(w, r, 30);
  const half = Math.round(Math.PI / P.flip_speed / DT);
  let end = null;
  for (let i = 0; i < 400 && !end; i++) {
    const ev = step(r, w, { pressed: i === 0, held: i > 0 && i <= half }, { ...P, jump: 900 }, DT);
    end = ev.find((e) => e.type === "land" || e.type === "crash");
  }
  assert.equal(end.type, "crash");
});

test("flip counting and the landing window", () => {
  assert.equal(countFlips(0.3), 0);
  assert.equal(countFlips(2 * Math.PI - 0.5), 1);
  assert.equal(countFlips(4 * Math.PI + 0.3), 2);
  const r = { angle: 0.2 };
  assert.ok(landable(r, 0, { forgiveness: 45 }));
  assert.ok(!landable(r, 1.2, { forgiveness: 45 }));
});

test("falling onto a rope from above starts a grind that runs to its end", () => {
  const w = new World(1, shapes);
  const rope = { x1: 400, y1: w.groundAt(400) - 63, x2: 900, y2: w.groundAt(900) - 63, sag: 20 };
  w.ropes.push(rope);
  const r = newRider(w);
  Object.assign(r, { x: 500, y: ropeY(rope, 500) - 30, vx: 400, vy: 100, state: "air", angle: 0.3, rot: 0 });
  const events = ride(w, r, 120);
  assert.ok(events.some((e) => e.type === "land" && e.on === "rope"));
  assert.ok(events.some((e) => e.type === "grinding"));
  assert.ok(events.some((e) => e.type === "rope-end"));
});

test("zen recovery puts the rider back on solid ground", () => {
  const w = new World(9, shapes);
  w.ensure(60000);
  const c = w.chasms[0];
  const r = newRider(w);
  Object.assign(r, { x: (c.x1 + c.x2) / 2, state: "crashed" });
  recover(r, w);
  assert.equal(r.state, "ground");
  assert.ok(w.groundAt(r.x) !== null);
});

import { newStats, currentLevel, newlyMet, goalKey } from "../../static/js/goals.js";

test("goals: met once, and the level moves on when all three are done", () => {
  const levels = JSON.parse(readFileSync(new URL("../../data/levels.json", import.meta.url))).levels;
  const types = new Set(Object.keys(newStats()));
  for (const l of levels) for (const g of l.goals) assert.ok(types.has(g.type), `known goal type ${g.type}`);
  const done = {};
  assert.equal(currentLevel(levels, done), 0);
  const st = { ...newStats(), distance: 600, flips: 1, coins: 25 };
  const met = newlyMet(levels, 0, st, done);
  assert.deepEqual(met, [goalKey(0, 0), goalKey(0, 1), goalKey(0, 2)]);
  for (const k of met) done[k] = true;
  assert.deepEqual(newlyMet(levels, 0, st, done), []);
  assert.equal(currentLevel(levels, done), 1);
});
