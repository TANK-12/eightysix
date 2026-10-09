// The gravity engine. Run: node --test tests/js/

import { test } from "node:test";
import assert from "node:assert/strict";

import { World, applyGenerator } from "../../static/core/nbody.js";

function twoBody({ softening = 0, dt = 0.001 } = {}) {
  const w = new World({ G: 1, softening, merge: false });
  const M = 1;
  const m = 0.001;
  const v = Math.sqrt((M + m) / 1);
  // Centre-of-mass frame so nothing drifts.
  w.addBody({ id: "sun", m: M, r: 0.01, x: (-m / (M + m)) * 1, vy: (-m / (M + m)) * v });
  w.addBody({ id: "planet", m, r: 0.001, x: (M / (M + m)) * 1, vy: (M / (M + m)) * v });
  return { w, dt };
}

test("a two-body orbit keeps its energy over 10,000 steps", () => {
  const { w, dt } = twoBody();
  const e0 = w.energy();
  let worst = 0;
  for (let s = 0; s < 10000; s++) {
    w.step(dt);
    worst = Math.max(worst, Math.abs((w.energy() - e0) / e0));
  }
  assert.ok(worst < 1e-6, `relative energy error ${worst}`);
});

test("orbital period follows Kepler's third law", () => {
  const w = new World({ G: 1, softening: 0, merge: false });
  w.addBody({ id: "sun", m: 1, r: 0.01, fixed: true });
  const r = 2;
  const probe = w.addBody({ id: "probe", m: 1e-9, r: 1e-4, x: r, vy: Math.sqrt(1 / r) });
  const dt = 0.001;
  let prevAngle = 0;
  let turned = 0;
  let t = 0;
  while (t < 100) {
    w.step(dt);
    t += dt;
    const a = Math.atan2(probe.y, probe.x);
    let d = a - prevAngle;
    if (d < -Math.PI) d += 2 * Math.PI;
    turned += d;
    prevAngle = a;
    if (turned >= 2 * Math.PI) break;
  }
  const expected = 2 * Math.PI * Math.sqrt(r ** 3);
  assert.ok(Math.abs(t - expected) / expected < 1e-3, `period ${t} vs ${expected}`);
});

test("colliding bodies merge and keep mass and momentum", () => {
  const w = new World({ G: 1, softening: 0.1 });
  w.addBody({ id: "big", name: "Big", m: 30, r: 2, x: -5, vx: 1, vy: 0.2, color: "#fff" });
  w.addBody({ id: "small", name: "Small", m: 10, r: 1, x: 5, vx: -2, vy: -0.4 });
  const [px, py] = w.momentum();
  for (let s = 0; s < 2000 && w.bodies.length > 1; s++) w.step(0.01);
  assert.equal(w.bodies.length, 1);
  const [b] = w.bodies;
  assert.equal(b.name, "Big");
  assert.equal(b.m, 40);
  const [qx, qy] = w.momentum();
  assert.ok(Math.abs(qx - px) < 1e-9 && Math.abs(qy - py) < 1e-9, `${[px, py]} -> ${[qx, qy]}`);
  assert.ok(Math.abs(b.r - Math.cbrt(9)) < 1e-12);
  assert.equal(w.events[0].type, "merge");
});

test("a black hole that swallows a heavier star is still a black hole, grown by mass", () => {
  const w = new World({ G: 1, softening: 0.1 });
  w.addBody({ id: "hole", kind: "blackhole", m: 10, r: 1, x: 0 });
  w.addBody({ id: "star", kind: "star", m: 50, r: 5, x: 5.5 });
  w.step(0.001);
  assert.equal(w.bodies.length, 1);
  assert.equal(w.bodies[0].kind, "blackhole");
  assert.ok(Math.abs(w.bodies[0].r - 6) < 1e-12, `radius ${w.bodies[0].r}`);
});

test("a generated disc stays on its orbits, and particles that fall in vanish", () => {
  const w = new World({ G: 1, softening: 0.01 });
  w.addBody({ id: "core", m: 1000, r: 1, fixed: true });
  applyGenerator(w, { type: "disc", around: "core", count: 200, r_min: 20, r_max: 40, seed: 4 });
  assert.equal(w.particles.count, 200);
  const radius = (i) => Math.hypot(w.particles.x[i], w.particles.y[i]);
  const before = Array.from({ length: 200 }, (_, i) => radius(i));
  const period = 2 * Math.PI * Math.sqrt(40 ** 3 / 1000);
  for (let t = 0; t < period; t += 0.01) w.step(0.01);
  for (let i = 0; i < 200; i++) {
    assert.ok(Math.abs(radius(i) / before[i] - 1) < 0.01, `particle ${i} drifted`);
  }
  w.addParticle(0.5, 0, 0, 0);
  w.step(0.01);
  assert.equal(w.particles.count, 200);
});

test("a prediction reports what it would hit and changes nothing", () => {
  const w = new World({ G: 1, softening: 0.01 });
  const planet = w.addBody({ id: "planet", m: 100, r: 2, x: 0, y: 0 });
  const snapshot = JSON.stringify(w.bodies);
  const { points, hit } = w.predict(30, 0, -3, 0, { steps: 2000, dt: 0.01 });
  assert.equal(hit, "planet");
  assert.ok(points.length >= 4 && points.length % 2 === 0);
  assert.equal(JSON.stringify(w.bodies), snapshot);
  assert.equal(planet.x, 0);
  const miss = w.predict(30, 0, 0, Math.sqrt(100 / 30), { steps: 500, dt: 0.01 });
  assert.equal(miss.hit, null);
});

test("a circular-orbit velocity really is circular", () => {
  const w = new World({ G: 1, softening: 0.5 });
  w.addBody({ id: "star", m: 500, r: 3, fixed: true });
  const { vx, vy, attractor } = w.circularVelocity(0, 60);
  assert.equal(attractor.id, "star");
  const p = w.addBody({ id: "p", m: 1e-6, r: 0.1, x: 0, y: 60, vx, vy });
  for (let s = 0; s < 5000; s++) w.step(0.01);
  assert.ok(Math.abs(Math.hypot(p.x, p.y) - 60) < 0.05);
});

test("the figure-eight comes back to where it started after one period", () => {
  const v3 = [-0.93240737, -0.86473146];
  const w = new World({ G: 1, softening: 0, merge: false });
  w.addBody({ id: "a", m: 1, r: 0.01, x: 0.97000436, y: -0.24308753, vx: -v3[0] / 2, vy: -v3[1] / 2 });
  w.addBody({ id: "b", m: 1, r: 0.01, x: -0.97000436, y: 0.24308753, vx: -v3[0] / 2, vy: -v3[1] / 2 });
  w.addBody({ id: "c", m: 1, r: 0.01, x: 0, y: 0, vx: v3[0], vy: v3[1] });
  const period = 6.32591398;
  const dt = 1e-4;
  for (let s = 0, n = Math.round(period / dt); s < n; s++) w.step(dt);
  const c = w.bodyById("c");
  assert.ok(Math.hypot(c.x, c.y) < 1e-3, `c is ${Math.hypot(c.x, c.y)} from its start`);
});

test("a world saved as a scenario loads back the same", () => {
  const w = new World({ G: 2, softening: 0.3 });
  w.addBody({ id: "s", name: "Star", kind: "star", m: 50, r: 4, x: 1, y: 2, vx: 0.5, vy: -0.5, fixed: true });
  w.addParticle(10, 0, 0, 1, "#abcdef");
  w.addParticle(-10, 0, 0, -1, "#123456");
  const again = World.fromScenario(JSON.parse(JSON.stringify(w.toScenario({ name: "t" }))));
  assert.equal(again.G, 2);
  assert.deepEqual(
    again.bodies.map(({ ax, ay, ...b }) => b),
    w.bodies.map(({ ax, ay, ...b }) => b),
  );
  assert.equal(again.particles.count, 2);
  assert.equal(again.particles.palette[again.particles.color[1]], "#123456");
});
