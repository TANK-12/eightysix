// The galaxy model's frame and colours. Run: node --test tests/js/

import { test } from "node:test";
import assert from "node:assert/strict";

import { bvToTemperature, temperatureToRgb } from "../../static/core/color.js";
import { prettyStarName } from "../../static/core/constellations.js";
import {
  ARMS,
  armAzimuth,
  buildGalaxyModel,
  galacticCenterEcliptic,
  galacticToEcliptic,
} from "../../static/core/galaxy.js";
import { angleBetween, length, raDecToEclipticUnit } from "../../static/core/vec.js";

test("the galactic centre and pole point where they are on the real sky", () => {
  const centre = galacticToEcliptic([1, 0, 0]);
  assert.ok(angleBetween(centre, raDecToEclipticUnit(266.40499, -28.93617)) < 0.05);
  const pole = galacticToEcliptic([0, 0, 1]);
  assert.ok(angleBetween(pole, raDecToEclipticUnit(192.85948, 27.12825)) < 0.05);
  const gc = galacticCenterEcliptic();
  assert.ok(Math.abs(length(gc) - 8200) < 1);
});

test("the arms cross the Sun's side of the galaxy at their measured radii, in order", () => {
  for (const arm of ARMS) {
    assert.ok(Math.abs(armAzimuth(arm, arm.radius_at_sun_pc) - Math.PI) < 1e-12);
  }
  const radii = ARMS.map((a) => a.radius_at_sun_pc);
  assert.deepEqual(radii, [...radii].sort((a, b) => a - b));
});

test("the model is deterministic and fills the arrays it returns", () => {
  const a = buildGalaxyModel({ count: 2000, seed: 5 });
  const b = buildGalaxyModel({ count: 2000, seed: 5 });
  assert.deepEqual(a.positions, b.positions);
  assert.equal(a.positions.length, 6000);
  assert.ok(a.positions.every(Number.isFinite) && a.colors.every(Number.isFinite));
  assert.ok(a.labels.length === ARMS.length + 1);
});

test("star colours run from red to blue with the colour index", () => {
  assert.ok(Math.abs(bvToTemperature(0.656) - 5800) < 150, "the Sun is about 5,800 K");
  const red = temperatureToRgb(bvToTemperature(1.8));
  const blue = temperatureToRgb(bvToTemperature(-0.3));
  assert.ok(red[0] > red[2] && blue[2] > blue[0]);
});

test("Bayer names are written with Greek letters and full constellation names", () => {
  assert.equal(prettyStarName("Alp Cen"), "α Centauri");
  assert.equal(prettyStarName("Kap-1 Scl"), "κ¹ Sculptoris");
  assert.equal(prettyStarName("61 Cyg"), "61 Cygni");
  assert.equal(prettyStarName("Sirius"), "Sirius");
  assert.equal(prettyStarName("96 G. Psc"), "96 G. Psc");
});
