// The ephemeris against JPL Horizons. Run: node --test tests/js/

import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";

import { Ephemeris, solveKepler } from "../../static/core/ephemeris.js";
import { AU_KM } from "../../static/core/units.js";
import { angleBetween, cross, distance, length, sub } from "../../static/core/vec.js";

const bodiesDir = new URL("../../data/bodies/", import.meta.url);
const bodies = readdirSync(bodiesDir)
  .filter((f) => f.endsWith(".json"))
  .map((f) => JSON.parse(readFileSync(new URL(f, bodiesDir), "utf8")));
const ref = JSON.parse(readFileSync(new URL("horizons-2026-09-15.json", import.meta.url), "utf8"));
const eph = new Ephemeris(bodies);

test("Kepler's equation is solved for gentle and very eccentric orbits", () => {
  for (const e of [0, 0.0167, 0.2, 0.6, 0.95, 0.999]) {
    for (let M = -7; M <= 7; M += 0.37) {
      const E = solveKepler(M, e);
      const back = E - e * Math.sin(E);
      assert.ok(Math.abs(Math.sin(back) - Math.sin(M)) < 1e-9, `e=${e} M=${M}`);
      assert.ok(Math.abs(Math.cos(back) - Math.cos(M)) < 1e-9, `e=${e} M=${M}`);
    }
  }
});

test("planet positions match JPL Horizons for 2026-09-15", () => {
  for (const [id, truth] of Object.entries(ref.positions_au)) {
    const p = eph.position(id, ref.jd);
    const angle = angleBetween(p, truth);
    const radial = Math.abs(length(p) / length(truth) - 1);
    assert.ok(angle < 0.5, `${id} is ${angle.toFixed(3)} degrees off`);
    assert.ok(radial < 0.01, `${id} distance is ${(radial * 100).toFixed(2)}% off`);
  }
});

test("the Moon is at a real lunar distance and Earth sits off the barycentre", () => {
  const km = distance(eph.position("moon", ref.jd), eph.position("earth", ref.jd)) * AU_KM;
  assert.ok(km > 356000 && km < 407000, `Moon at ${km} km`);
  const offset = distance(eph.orbitalOffset("earth", ref.jd), eph.position("earth", ref.jd)) * AU_KM;
  assert.ok(offset > 4200 && offset < 5000, `barycentre offset ${offset} km`);
});

test("every body has a finite position across the whole valid window", () => {
  for (const jd of [2378496.5, ref.jd, 2469807.5]) {
    for (const b of bodies) {
      const p = eph.position(b.id, jd);
      assert.ok(p.every(Number.isFinite), `${b.id} at ${jd}`);
    }
  }
});

test("Uranus's moons orbit on their side and Triton orbits backwards", () => {
  const normal = (id) => {
    const path = eph.orbitPath(id, ref.jd, 64);
    return cross(Array.from(path.slice(0, 3)), Array.from(path.slice(48, 51)));
  };
  const tilt = (id) => angleBetween(normal(id), [0, 0, 1]);
  assert.ok(tilt("titania") > 75 && tilt("titania") < 105, `Titania tilt ${tilt("titania")}`);
  assert.ok(tilt("triton") > 90, `Triton tilt ${tilt("triton")}`);
  assert.ok(tilt("io") < 5, `Io tilt ${tilt("io")}`);
});

test("orbital periods come out right", () => {
  assert.ok(Math.abs(eph.periodDays("earth", ref.jd) - 365.256) < 0.1);
  assert.ok(Math.abs(eph.periodDays("moon", ref.jd) - 27.322) < 0.01);
  assert.ok(Math.abs(eph.periodDays("jupiter", ref.jd) / 365.25 - 11.86) < 0.02);
});

test("an orbit path closes and sits around its parent", () => {
  const path = eph.orbitPath("mars", ref.jd, 128);
  const first = Array.from(path.slice(0, 3));
  const last = Array.from(path.slice(-3));
  assert.ok(length(sub(first, last)) < 1e-6);
  const r = length(first);
  assert.ok(r > 1.38 && r < 1.67, `Mars path radius ${r}`);
});
