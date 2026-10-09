// The shipped puzzle levels in ~/ForgeGameData/cosmos/levels. Run: node --test tests/js/
// COSMOS_LEVEL_DIR points it at another folder; with no folder the tests skip.

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

import { RailSystem } from "../../static/core/nbody3d.js";
import { checkLevel, playReference, prepareLevel, score } from "../../static/core/puzzle.js";

const DIR = process.env.COSMOS_LEVEL_DIR || join(homedir(), "ForgeGameData", "cosmos", "levels");
const files = existsSync(DIR) ? readdirSync(DIR).filter((f) => f.endsWith(".json")).sort() : [];
const load = (f) => JSON.parse(readFileSync(join(DIR, f), "utf8"));
const skip = files.length ? false : `no levels in ${DIR}`;

test("ten puzzles and an explore level are shipped", { skip }, () => {
  const goals = files.map((f) => load(f).goal.type);
  assert.equal(goals.filter((g) => g !== "explore").length, 10);
  assert.ok(goals.includes("explore"));
  for (const type of ["reach", "orbit", "waypoints", "land"]) assert.ok(goals.includes(type), `a ${type} level`);
});

for (const f of files) {
  test(`${f} is valid and its stored solution earns three stars`, () => {
    const raw = load(f);
    assert.deepEqual(checkLevel(raw), []);
    if (raw.goal.type === "explore") return;
    const level = prepareLevel(raw);
    const run = playReference(level, level.reference);
    assert.equal(run.status, "won", run.reason);
    assert.equal(score(level, run).stars, 3);
  });
}

test("the galaxy playground is huge, and every star can be saved as found", { skip }, () => {
  const galaxy = files.map(load).find((l) => l.goal.type === "explore");
  const stars = galaxy.bodies.filter((b) => b.kind === "star");
  assert.ok(stars.length >= 30, `${stars.length} stars`);
  const span = Math.max(...stars.map((s) => s.orbit?.a ?? 0));
  assert.ok(span >= 3000, `the farthest star circles at ${span}`);
  const ids = galaxy.bodies.map((b) => b.id);
  assert.equal(new Set(ids).size, ids.length, "body ids are unique");
  for (const id of ids) assert.match(id, /^[a-z0-9][a-z0-9_-]{0,79}$/, "the server accepts it as a found id");
});

/* The farthest a probe could coast from its home planet's star with the
 * fastest launch and no help: twice the semi-major axis of the most energetic
 * orbit available. Any other planet's pull is what has to make up the rest. */
function farthestUnaided(level, homeId) {
  const sys = new RailSystem({ G: level.G ?? 1, bodies: level.bodies });
  const home = sys.body(homeId);
  const mu = (level.G ?? 1) * sys.bodies[home.parentIndex].m;
  const v = Math.hypot(...sys.velocity(homeId, 0)) + level.launch.speed[1];
  const energy = (v * v) / 2 - mu / home.orbit.a;
  return energy >= 0 ? Infinity : -mu / energy;
}

test("the slingshot levels cannot be won without the gravity assist", { skip }, () => {
  for (const [file, target] of [
    ["04-slingshot.json", "beacon"],
    ["10-grand-tour.json", "saturn"],
  ]) {
    const level = load(file);
    const goal = level.bodies.find((b) => b.id === target);
    const reach = farthestUnaided(level, level.launch.from);
    assert.ok(reach < goal.orbit.a, `${file}: unaided reach ${reach.toFixed(1)} vs target orbit ${goal.orbit.a}`);
  }
});
