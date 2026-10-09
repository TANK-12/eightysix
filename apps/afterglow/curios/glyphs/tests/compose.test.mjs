// node --test curios/glyphs/ : Compose writes formulas that always parse.
import { test } from "node:test";
import assert from "node:assert/strict";
import { compose, RECIPE_NAMES } from "../compose.js";
import { parse, frame } from "../lang.js";

test("the same seed gives the same piece", () => {
  for (let seed = 0; seed < 200; seed++) assert.deepEqual(compose(seed), compose(seed));
  assert.notDeepEqual(compose(1), compose(2));
  assert.equal(compose(-1).seed, 4294967295);
  assert.deepEqual(compose(2 ** 32 + 5), compose(5));
});

test("every piece parses, has a title, and every recipe turns up", () => {
  const seen = new Set();
  for (let seed = 0; seed < 600; seed++) {
    const p = compose(seed * 7919);
    parse(p.formula);
    assert.match(p.title, /^[A-Z][A-Za-z-]+ [a-z]+$/, p.title);
    assert.ok(p.formula.length < 400);
    seen.add(p.recipe);
  }
  assert.deepEqual([...seen].sort(), [...RECIPE_NAMES].sort());
});

test("composed pieces give finite values that move", () => {
  for (let seed = 0; seed < 120; seed++) {
    const { formula } = compose(seed);
    const a = frame(formula, 0.4, 12);
    const b = frame(formula, 3.1, 12);
    assert.ok(a.every(Number.isFinite) && b.every(Number.isFinite), formula);
    assert.ok(a.some((v) => Math.abs(v) > 0.05) || b.some((v) => Math.abs(v) > 0.05), formula);
  }
});
