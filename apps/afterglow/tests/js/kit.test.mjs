import test from "node:test";
import assert from "node:assert/strict";

import { rng, hashString, randInt, pick } from "../../curios/_kit/rng.js";

test("the same seed gives the same stream, another seed another", () => {
  const a = rng(42), b = rng(42), c = rng(43);
  const sa = [a(), a(), a()], sb = [b(), b(), b()], sc = [c(), c(), c()];
  assert.deepEqual(sa, sb);
  assert.notDeepEqual(sa, sc);
  for (const v of sa) assert.ok(v >= 0 && v < 1);
});

test("the stream is roughly even", () => {
  const r = rng(7);
  const bins = new Array(10).fill(0);
  for (let i = 0; i < 20000; i++) bins[Math.floor(r() * 10)]++;
  for (const n of bins) assert.ok(n > 1700 && n < 2300, `bin ${n}`);
});

test("hashString is stable and spreads", () => {
  assert.equal(hashString("afterglow"), hashString("afterglow"));
  assert.notEqual(hashString("afterglow"), hashString("afterglom"));
  assert.ok(Number.isInteger(hashString("✨")) && hashString("✨") >= 0);
});

test("randInt covers both ends and pick stays in the list", () => {
  const r = rng(1);
  const seen = new Set();
  for (let i = 0; i < 500; i++) seen.add(randInt(r, 2, 4));
  assert.deepEqual([...seen].sort(), [2, 3, 4]);
  for (let i = 0; i < 50; i++) assert.ok(["a", "b"].includes(pick(r, ["a", "b"])));
});
