// node --test curios/glyphs/ : the drawing rules, with a recording context.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as R from "../render.js";

test("cleanPiece turns junk keepsake data into a safe piece", () => {
  const dflt = { formula: "sin(t - r)", grid: 16, speed: 1, palette: "ember", shape: "circle" };
  for (const junk of [null, undefined, 3, "x", [], {}, { formula: 5 }]) {
    assert.deepEqual(R.cleanPiece(junk), dflt, JSON.stringify(junk));
  }
  const odd = R.cleanPiece({
    formula: "x".repeat(5000),
    grid: 1e9,
    speed: Infinity,
    palette: "__proto__",
    shape: "toString",
  });
  assert.equal(odd.formula.length, 400);
  assert.equal(odd.grid, R.GRID_MAX);
  assert.equal(odd.speed, 1);
  assert.equal(odd.palette, "ember");
  assert.equal(odd.shape, "circle");
  assert.equal(R.cleanPiece({ grid: -5, speed: -2 }).grid, R.GRID_MIN);
  assert.equal(R.cleanPiece({ speed: -2 }).speed, 0);
  assert.equal(R.cleanPiece({ grid: "12.4" }).grid, 12);
  assert.equal(R.cleanPiece({ grid: NaN }).grid, 16);
  assert.equal(R.cleanPiece({ palette: "constructor" }).palette, "ember");
  const good = { formula: "x & y", grid: 32, speed: 2.5, palette: "paper", shape: "diamond" };
  assert.deepEqual(R.cleanPiece(good), good);
});

test("fieldBox fits a square inside the canvas, dotAt finds every dot again", () => {
  for (const [w, h, free] of [
    [800, 600, {}],
    [1400, 900, { left: 300, right: 1100, top: 60, bottom: 840 }],
    [500, 900, { left: 200, right: 300 }],
    [10, 10, {}],
  ]) {
    const box = R.fieldBox(w, h, free);
    assert.ok(box.size >= 16);
    if (w >= 16 && h >= 16) {
      assert.ok(box.x >= 0 && box.y >= 0 && box.x + box.size <= w && box.y + box.size <= h, `${w}x${h}`);
    }
    for (const n of [4, 16, 64]) {
      const cell = box.size / n;
      for (let k = 0; k < n * n; k++) {
        const cx = box.x + ((k % n) + 0.5) * cell;
        const cy = box.y + (Math.floor(k / n) + 0.5) * cell;
        assert.equal(R.dotAt(box, n, cx, cy), k);
      }
      assert.equal(R.dotAt(box, n, box.x - 1, box.y + 1), -1);
      assert.equal(R.dotAt(box, n, box.x + box.size + 1, box.y + 1), -1);
      assert.equal(R.dotAt(box, n, NaN, 5), -1);
    }
  }
});

test("ease converges, never overshoots, and ignores a negative dt", () => {
  const target = [1, -1, 0.5, 0];
  const shown = [0, 0, 0, 0];
  let left = Infinity;
  for (let k = 0; k < 120; k++) {
    const next = R.ease(shown, target, 1 / 60);
    assert.ok(next <= left);
    left = next;
    shown.forEach((v, i) => assert.ok(Math.abs(v) <= Math.abs(target[i]) + 1e-12));
  }
  assert.ok(left < 1e-6, `left ${left}`);
  const still = [0.2];
  assert.equal(R.ease(still, [1], -5), 0.8);
  assert.deepEqual(still, [0.2]);
  const jump = [0];
  R.ease(jump, [1], 100);
  assert.equal(jump[0], 1);
});

function recorder() {
  const log = { fills: 0, shapes: 0 };
  const path = () => ({
    moveTo() {},
    lineTo() {},
    closePath() {},
    rect() { log.shapes++; },
    arc() { log.shapes++; },
  });
  const g = {
    fillRect() {},
    createRadialGradient: () => ({ addColorStop() {} }),
    fill() { log.fills++; },
  };
  return { g, path, log };
}

test("drawField uses a fixed number of fills for any grid, palette and shape", () => {
  for (const palette of Object.keys(R.PALETTES)) {
    for (const shape of R.SHAPES) {
      for (const n of [4, 64]) {
        const { g, path, log } = recorder();
        const values = Array.from({ length: n * n }, (_, k) => Math.sin(k));
        R.drawField(g, { w: 400, h: 300, box: { x: 50, y: 0, size: 300 }, n, values, palette, shape, makePath: path });
        const glow = R.PALETTES[palette].halo ? 2 : 0;
        assert.equal(log.fills, 1 + glow + 8, `${palette} ${shape}`);
        assert.ok(log.shapes > 0);
      }
    }
  }
});
