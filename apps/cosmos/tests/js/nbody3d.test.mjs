// The 3D rails-and-probe engine. Run: node --test tests/js/

import { test } from "node:test";
import assert from "node:assert/strict";

import { RailSystem, makeProbe, predict, railState, specificEnergy, stepProbe } from "../../static/core/nbody3d.js";

const close = (a, b, tol, what) => assert.ok(Math.abs(a - b) <= tol, `${what}: ${a} vs ${b}`);

test("a circular probe orbit keeps its energy over 10,000 steps", () => {
  const sys = new RailSystem({ bodies: [{ id: "star", m: 1, r: 0.01 }] });
  const s = makeProbe([1, 0, 0], [0, 1, 0]);
  const e0 = specificEnergy(sys, s);
  let worst = 0;
  for (let k = 0; k < 10000; k++) {
    stepProbe(sys, s, 0.001);
    worst = Math.max(worst, Math.abs((specificEnergy(sys, s) - e0) / e0));
  }
  assert.ok(worst < 1e-6, `relative energy error ${worst}`);
  close(Math.hypot(s.x, s.y, s.z), 1, 1e-5, "radius");
});

test("a body on rails comes back after one period, which follows Kepler's third law", () => {
  const sys = new RailSystem({
    bodies: [
      { id: "sun", m: 10, r: 1 },
      { id: "p", m: 0.5, r: 0.2, orbit: { parent: "sun", a: 4, e: 0.3, i: 20, node: 40, peri: 70, M0: 15 } },
    ],
  });
  const T = sys.period("p");
  close(T, 2 * Math.PI * Math.sqrt(64 / 10.5), 1e-12, "period");
  const start = sys.position("p", 0);
  const after = sys.position("p", T);
  for (let k = 0; k < 3; k++) close(after[k], start[k], 1e-9, `axis ${k}`);
});

test("a rail velocity is the rate of change of its position", () => {
  const orbit = { parent: "sun", a: 3, e: 0.6, i: 35, node: 10, peri: 200, M0: 80, direction: -1 };
  const h = 1e-6;
  for (const t of [0, 1.3, 7.9]) {
    const a = railState(orbit, 5, t - h);
    const b = railState(orbit, 5, t + h);
    const s = railState(orbit, 5, t);
    for (let k = 0; k < 3; k++) close(s[3 + k], (b[k] - a[k]) / (2 * h), 1e-6, `t=${t} axis ${k}`);
  }
});

test("a moon rides along with its planet", () => {
  const sys = new RailSystem({
    bodies: [
      { id: "moon", m: 0.001, r: 0.05, orbit: { parent: "planet", a: 0.5 } },
      { id: "planet", m: 0.1, r: 0.1, orbit: { parent: "sun", a: 10 } },
      { id: "sun", m: 100, r: 1 },
    ],
  });
  assert.deepEqual(
    sys.bodies.map((b) => b.id),
    ["sun", "planet", "moon"],
  );
  for (const t of [0, 3, 11]) {
    const p = sys.position("planet", t);
    const m = sys.position("moon", t);
    close(Math.hypot(m[0] - p[0], m[1] - p[1], m[2] - p[2]), 0.5, 1e-12, `moon distance at ${t}`);
    close(Math.hypot(...p), 10, 1e-12, `planet distance at ${t}`);
  }
});

test("a missing parent or a loop of parents is refused with a reason", () => {
  assert.throws(() => new RailSystem({ bodies: [{ id: "a", orbit: { parent: "nope", a: 1 } }] }), /does not exist/);
  assert.throws(
    () =>
      new RailSystem({
        bodies: [
          { id: "a", orbit: { parent: "b", a: 1 } },
          { id: "b", orbit: { parent: "a", a: 1 } },
        ],
      }),
    /orbits itself/,
  );
});

test("a tilted probe orbit stays in its plane", () => {
  const sys = new RailSystem({ bodies: [{ id: "star", m: 1, r: 0.01 }] });
  const tilt = 0.7;
  const s = makeProbe([1.5, 0, 0], [0, 0.9 * Math.cos(tilt), 0.9 * Math.sin(tilt)]);
  const normal = (q) => {
    const h = [q.y * q.vz - q.z * q.vy, q.z * q.vx - q.x * q.vz, q.x * q.vy - q.y * q.vx];
    const l = Math.hypot(...h);
    return h.map((c) => c / l);
  };
  const n0 = normal(s);
  for (let k = 0; k < 20000; k++) stepProbe(sys, s, 0.002);
  const n1 = normal(s);
  for (let k = 0; k < 3; k++) close(n1[k], n0[k], 1e-9, `normal axis ${k}`);
});

test("a prediction reports what it would hit and changes nothing", () => {
  const sys = new RailSystem({
    bodies: [
      { id: "sun", m: 100, r: 2 },
      { id: "p", m: 1, r: 0.5, orbit: { parent: "sun", a: 20 } },
    ],
  });
  const probe = makeProbe([30, 0, 0], [-3, 0, 0], 0.5);
  const before = JSON.stringify(probe);
  const { points, hit, t } = predict(sys, probe, { duration: 50, dt: 0.01 });
  assert.equal(JSON.stringify(probe), before);
  assert.ok(hit >= 0, "should hit something");
  assert.ok(points.length >= 6 && points.length % 3 === 0);
  assert.ok(t > 0.5 && t < 50.5);
  const miss = predict(sys, makeProbe([0, 60, 0], [Math.sqrt(100 / 60), 0, 0]), { duration: 5, dt: 0.01 });
  assert.equal(miss.hit, -1);
  const gone = predict(sys, makeProbe([0, 60, 0], [0, 50, 0]), { duration: 50, dt: 0.01, bounds: 100 });
  assert.equal(gone.hit, -1);
  assert.ok(gone.t < 2, `stopped at bounds by ${gone.t}`);
});
