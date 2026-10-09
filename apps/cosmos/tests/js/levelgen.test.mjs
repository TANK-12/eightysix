// Endless levels and the solver. Run: node --test tests/js/

import { test } from "node:test";
import assert from "node:assert/strict";

import { generateLevel, solveLevel } from "../../static/core/levelgen.js";
import { checkLevel, playReference, prepareLevel, score } from "../../static/core/puzzle.js";

const SEEDS = Number(process.env.COSMOS_LEVELGEN_SEEDS || 100);

test(`every generated level is valid and its own launch wins it (${SEEDS} seeds)`, () => {
  let fallbacks = 0;
  for (let seed = 1; seed <= SEEDS; seed++) {
    const difficulty = 1 + ((seed - 1) % 10);
    const level = generateLevel(seed, difficulty);
    assert.deepEqual(checkLevel(level), [], `seed ${seed}`);
    const run = playReference(level, level.reference, { maxTime: level.preview_time * 2 + 10 });
    assert.equal(run.status, "won", `seed ${seed} difficulty ${difficulty}: ${run.reason}`);
    assert.ok(score(level, run).par, `seed ${seed}: the reference launch should beat par`);
    if (level.fallback) fallbacks++;
  }
  assert.ok(fallbacks <= SEEDS * 0.1, `${fallbacks} of ${SEEDS} levels fell back to the simple layout`);
});

test("the same seed always builds the same level", () => {
  assert.equal(JSON.stringify(generateLevel(42, 6)), JSON.stringify(generateLevel(42, 6)));
  assert.notEqual(JSON.stringify(generateLevel(42, 6)), JSON.stringify(generateLevel(43, 6)));
});

test("harder levels bring more hazards and a shorter preview", () => {
  const easy = generateLevel(7, 1);
  const hard = generateLevel(7, 9);
  assert.ok(hard.bodies.length > easy.bodies.length || hard.fields.length > easy.fields.length);
  assert.ok(hard.preview < easy.preview);
});

test("the solver finds a launch for a reach level", () => {
  const found = solveLevel(
    {
      name: "Reach",
      bodies: [
        { id: "sun", m: 1000, r: 3 },
        { id: "home", m: 1, r: 1, orbit: { parent: "sun", a: 40 } },
        { id: "far", name: "Far", m: 0.5, r: 1.5, orbit: { parent: "sun", a: 80, M0: 120 } },
      ],
      launch: { from: "home", speed: [0, 5] },
      goal: { type: "reach", target: "far", radius: 2 },
      dt: 0.02,
      preview_time: 80,
    },
    { coarse: 36, speeds: 10, refine: 150 },
  );
  assert.ok(found.solved, `closest ${found.closest}`);
});

test("the solver brakes into orbit and down to a gentle landing", () => {
  const base = {
    bodies: [{ id: "moon", name: "Moon", m: 20, r: 2 }],
    launch: { pos: [30, 0, 0], speed: [0, 2], heading: [90, 270] },
    fuel: 5,
    dt: 0.005,
    preview_time: 40,
  };
  const orbit = solveLevel({ ...base, name: "Orbit", goal: { type: "orbit", target: "moon", hold: 3, max_apoapsis: 20 } }, { coarse: 24, speeds: 8, refine: 60 });
  assert.ok(orbit.solved, `orbit closest ${orbit.closest}`);
  assert.ok(orbit.reference.burns.length === 1 && orbit.reference.burns[0].dir === "retrograde");
  const replay = playReference(prepareLevel({ ...base, name: "Orbit", goal: { type: "orbit", target: "moon", hold: 3, max_apoapsis: 20 } }), orbit.reference);
  assert.equal(replay.status, "won", replay.reason);

  const landLevel = { ...base, name: "Land", goal: { type: "land", target: "moon", max_speed: 0.8 } };
  const land = solveLevel(landLevel, { coarse: 24, speeds: 8, refine: 60 });
  assert.ok(land.solved, `land closest ${land.closest}`);
  const touchdown = playReference(prepareLevel(landLevel), land.reference);
  assert.equal(touchdown.status, "won", `the stored landing replays: ${touchdown.reason}`);
});
