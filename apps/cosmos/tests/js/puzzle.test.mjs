// The rules of the orbit puzzles, on small made-up levels. Run: node --test tests/js/

import { test } from "node:test";
import assert from "node:assert/strict";

import { Run, aimDirection, checkLevel, discoverableIds, launchState, playReference, prepareLevel, score } from "../../static/core/puzzle.js";
import { RailSystem } from "../../static/core/nbody3d.js";

function level(overrides = {}) {
  return {
    name: "Test",
    bodies: [
      { id: "star", name: "Star", kind: "star", m: 0, r: 1, pos: [0, 0, 0] },
      { id: "target", name: "Target", kind: "planet", m: 0, r: 1, pos: [20, 0, 0] },
    ],
    launch: { pos: [0, -10, 0], speed: [0, 20] },
    goal: { type: "reach", target: "target", radius: 1 },
    dt: 0.01,
    ...overrides,
  };
}

const fly = (L, aim, maxTime = 200) => {
  const run = new Run(prepareLevel(L), aim);
  while (run.status === "flying" && run.time < maxTime) run.step();
  return run;
};

test("a good level passes the check and broken ones are refused with reasons", () => {
  assert.deepEqual(checkLevel(level()), []);
  const cases = [
    [{ goal: { type: "teleport" } }, /goal type/],
    [{ goal: { type: "reach", target: "nowhere" } }, /does not exist/],
    [{ launch: { speed: [0, 5] } }, /launch body or a pos|body to launch from/],
    [{ launch: { pos: [0, 0, 0], speed: [5, 1] } }, /launch\.speed/],
    [{ bodies: [{ id: "a", m: 1, r: 1, orbit: { parent: "ghost", a: 2 } }] }, /does not exist/],
    [{ bodies: [{ id: "a", m: -1, r: 1 }] }, /m must be/],
    [{ goal: { type: "waypoints", points: [] } }, /at least one point/],
    [{ fields: [{ type: "belt", around: "star", r_min: 5, r_max: 2, count: 10 }] }, /r_min < r_max/],
    [{ bonus: { type: "close_pass", body: "ghost" } }, /bonus body/],
  ];
  for (const [bad, reason] of cases) {
    const problems = checkLevel(level(bad));
    assert.ok(problems.some((p) => reason.test(p)), `${JSON.stringify(bad)} gave ${JSON.stringify(problems)}`);
  }
});

test("the default edge of space is fifty times the level's size", () => {
  const L = prepareLevel(level());
  assert.equal(L.bounds, 20 * 50);
  assert.equal(prepareLevel(level({ bounds: 7 })).bounds, 7);
});

test("heading and elevation point where they say", () => {
  const close = (a, b) => a.forEach((v, k) => assert.ok(Math.abs(v - b[k]) < 1e-12, `${a} vs ${b}`));
  close(aimDirection({ heading: 0 }), [1, 0, 0]);
  close(aimDirection({ heading: 90 }), [0, 1, 0]);
  close(aimDirection({ heading: 0, elevation: 90 }), [0, 0, 1]);
});

test("a launch from a body starts above its surface and keeps its orbital velocity", () => {
  const L = prepareLevel({
    ...level(),
    bodies: [
      { id: "star", m: 100, r: 2 },
      { id: "home", m: 1, r: 1, orbit: { parent: "star", a: 30 } },
    ],
    launch: { from: "home", speed: [0, 5], altitude: 0.5 },
    goal: { type: "explore" },
  });
  const sys = new RailSystem({ bodies: L.bodies });
  const { p, v } = launchState(L, sys, { speed: 2, heading: 90, elevation: 0 });
  const hp = sys.position("home", 0);
  const hv = sys.velocity("home", 0);
  assert.ok(Math.abs(Math.hypot(p[0] - hp[0], p[1] - hp[1], p[2] - hp[2]) - 1.5) < 1e-12);
  assert.ok(Math.abs(v[1] - hv[1] - 2) < 1e-12 && Math.abs(v[0] - hv[0]) < 1e-12);
  const clamped = launchState(L, sys, { speed: 99, heading: 0 });
  assert.equal(clamped.aim.speed, 5);
});

test("reaching the target wins, and flying off loses at the edge of space", () => {
  const aimAt = Math.atan2(10, 20) * (180 / Math.PI);
  const won = fly(level(), { speed: 10, heading: aimAt });
  assert.equal(won.status, "won");
  assert.match(won.reason, /Reached Target/);
  const lost = fly(level({ bounds: 40 }), { speed: 10, heading: 180 });
  assert.equal(lost.status, "lost");
  assert.match(lost.reason, /out of bounds/);
});

test("hitting a body crashes, and a black hole says so", () => {
  const base = level({ goal: { type: "explore" } });
  const crash = fly(base, { speed: 10, heading: 90 });
  assert.match(crash.reason, /Crashed into Star/);
  base.bodies[0].kind = "blackhole";
  base.bodies[0].name = "the hole";
  assert.match(fly(base, { speed: 10, heading: 90 }).reason, /Fell into the hole/);
});

test("a gentle touchdown lands and a fast one crashes", () => {
  // Dropped from rest at height 3 above a planet of radius 1 and GM 4:
  // impact speed is sqrt(2 * 4 * (1/1 - 1/4)) = sqrt(6), about 2.45.
  const drop = (maxSpeed) =>
    fly(
      {
        name: "Drop",
        bodies: [{ id: "moon", name: "Moon", m: 4, r: 1 }],
        launch: { pos: [0, 4, 0], speed: [0, 0] },
        goal: { type: "land", target: "moon", max_speed: maxSpeed },
        dt: 0.0005,
      },
      { speed: 0, heading: 0 },
      20,
    );
  const soft = drop(2.6);
  assert.equal(soft.status, "won", soft.reason);
  assert.ok(Math.abs(soft.touchdownSpeed - Math.sqrt(6)) < 0.02, `touchdown at ${soft.touchdownSpeed}`);
  const hard = drop(2.2);
  assert.equal(hard.status, "lost");
  assert.match(hard.reason, /2\.2 or slower/);
});

test("a steady orbit is captured after the hold time, and an escape never is", () => {
  const orbitLevel = {
    name: "Orbit",
    bodies: [{ id: "p", name: "Planet", m: 1, r: 1 }],
    launch: { pos: [3, 0, 0], speed: [0, 5] },
    goal: { type: "orbit", target: "p", hold: 2, max_apoapsis: 10 },
    dt: 0.005,
  };
  const inOrbit = fly(orbitLevel, { speed: Math.sqrt(1 / 3), heading: 90 }, 30);
  assert.equal(inOrbit.status, "won", inOrbit.reason);
  assert.ok(Math.abs(inOrbit.time - 2) < 0.05, `won at ${inOrbit.time}`);
  const escaping = new Run(prepareLevel(orbitLevel), { speed: 1.2, heading: 90 });
  for (let k = 0; k < 2000; k++) escaping.step();
  assert.equal(escaping.status, "flying");
  assert.equal(escaping.holdTime, 0);
});

test("waypoints only count in order", () => {
  const rings = (points) =>
    level({
      bodies: [{ id: "star", m: 0, r: 0.1, pos: [0, 50, 0] }],
      launch: { pos: [0, 0, 0], speed: [0, 20] },
      goal: { type: "waypoints", points },
      bounds: 30,
    });
  const inOrder = fly(rings([{ pos: [5, 0, 0], radius: 0.5 }, { pos: [10, 0, 0], radius: 0.5 }]), { speed: 5, heading: 0 });
  assert.equal(inOrder.status, "won");
  assert.deepEqual(
    inOrder.events.filter((e) => e.type === "waypoint").map((e) => e.index),
    [0, 1],
  );
  const backwards = fly(rings([{ pos: [10, 0, 0], radius: 0.5 }, { pos: [5, 0, 0], radius: 0.5 }]), { speed: 5, heading: 0 });
  assert.equal(backwards.status, "lost");
  assert.equal(backwards.waypoint, 1);
});

test("burns spend fuel, never more than there is, in the direction asked", () => {
  const L = prepareLevel({
    name: "Burns",
    bodies: [{ id: "p", m: 1, r: 1 }],
    launch: { pos: [4, 0, 0], speed: [0, 5] },
    goal: { type: "explore" },
    fuel: 1,
  });
  const run = new Run(L, { speed: 0.5, heading: 90 });
  const speed = () => Math.hypot(run.probe.vx, run.probe.vy, run.probe.vz);
  assert.equal(run.burn("prograde", 0.25), 0.25);
  assert.ok(Math.abs(speed() - 0.75) < 1e-12);
  run.burn("normal", 0.25);
  assert.ok(Math.abs(run.probe.vz - 0.25) < 1e-12, `vz ${run.probe.vz}`);
  assert.equal(run.burn("retrograde", 5), 0.5);
  assert.equal(run.fuelLeft, 0);
  assert.equal(run.burn("prograde", 1), 0);
  assert.equal(run.dvUsed, 1);
});

test("an asteroid belt is a hazard", () => {
  const L = {
    name: "Belt",
    bodies: [{ id: "star", m: 100, r: 1 }],
    fields: [{ type: "belt", around: "star", r_min: 9.9, r_max: 10.1, count: 2000, size: 0.2, thickness_deg: 0 }],
    launch: { pos: [5, 0, 0], speed: [0, 30] },
    goal: { type: "explore" },
    dt: 0.002,
  };
  const run = fly(L, { speed: 20, heading: 0 }, 5);
  assert.equal(run.status, "lost");
  assert.match(run.reason, /asteroid/);
});

test("stars come from finishing, par and the bonus", () => {
  const aimAt = Math.atan2(10, 20) * (180 / Math.PI);
  const L = prepareLevel(level({ par: 10, bonus: { type: "no_burns" } }));
  const run = playReference(L, { speed: 10, heading: aimAt });
  assert.deepEqual(
    { ...score(L, run), cost: undefined },
    { won: true, finish: true, par: true, bonus: true, stars: 3, cost: undefined },
  );
  const pricey = playReference(L, { speed: 12, heading: aimAt });
  assert.equal(score(L, pricey).stars, 2);
  const slow = prepareLevel(level({ par: 10, bonus: { type: "time_under", value: 0.1 } }));
  assert.equal(score(slow, playReference(slow, { speed: 10, heading: aimAt })).stars, 2);
  const missed = playReference(prepareLevel(level({ bounds: 40 })), { speed: 10, heading: 180 });
  assert.equal(score(prepareLevel(level()), missed).stars, 0);
});

test("an explore flight discovers the stars it passes close to, once each", () => {
  const raw = {
    name: "Explore",
    bodies: [
      { id: "alpha", name: "Alpha", kind: "star", m: 0, r: 1, pos: [20, 0, 0] },
      { id: "beta", name: "Beta", kind: "star", m: 0, r: 1, pos: [0, 200, 0] },
      { id: "rock", name: "Rock", kind: "planet", m: 0, r: 1, pos: [40, 6, 0] },
    ],
    launch: { pos: [0, 3, 0], speed: [0, 20] },
    goal: { type: "explore" },
    discover_radius: 5,
    bounds: 100,
  };
  assert.deepEqual(discoverableIds(raw), ["alpha", "beta"]);
  const run = new Run(prepareLevel(raw), { speed: 10, heading: 0 });
  while (run.status === "flying") run.step();
  assert.match(run.reason, /out of bounds/);
  assert.deepEqual([...run.discovered], ["alpha"]);
  assert.equal(run.events.filter((e) => e.type === "discover").length, 1);
  assert.ok(run.farthest > 95, `farthest ${run.farthest}`);
  const goalLevel = new Run(prepareLevel(level()), { speed: 10, heading: 26.57 });
  assert.equal(goalLevel.discoverables.length, 0);
});

test("a long flight's trail stays bounded", () => {
  const L = prepareLevel({
    name: "Long",
    bodies: [{ id: "star", m: 1, r: 0.1 }],
    launch: { pos: [1, 0, 0], speed: [0, 2] },
    goal: { type: "explore" },
    dt: 0.001,
  });
  const run = new Run(L, { speed: 1, heading: 90 });
  for (let k = 0; k < 200000; k++) run.step();
  assert.ok(run.trail.length <= 24000 + 3, `trail ${run.trail.length}`);
  assert.ok(run.trail.length % 3 === 0);
});
