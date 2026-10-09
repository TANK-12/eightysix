// node --test curios/crucible/ : the world, its chemistry, the picture and the keepsake format.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import * as S from "../sim.js";
import * as R from "../render.js";
import * as C from "../codec.js";
import * as SC from "../scenes.js";
import { picture } from "../tools/play.mjs";

const { M } = S;
const SEED_DIR = new URL("../seeds/", import.meta.url);

/** A small world filled with stone at temperature t (no air, so no heat leaves). */
function box(w, h, t, m = M.STONE) {
  const s = S.createWorld(5, w, h);
  S.fillRect(s, 0, 0, w - 1, h - 1, m, t);
  return s;
}

function sameWorld(a, b, msg) {
  assert.equal(a.tick, b.tick, `${msg}: tick`);
  assert.deepEqual(a.mat, b.mat, `${msg}: materials`);
  assert.deepEqual(a.temp, b.temp, `${msg}: heat`);
  assert.deepEqual(a.life, b.life, `${msg}: life`);
}

function count(s, m) {
  return S.census(s)[m];
}

test("same seed and same strokes give the same world", () => {
  const strokes = (s) => {
    S.stroke(s, 10, 10, 200, 40, 5, M.SAND);
    S.paint(s, 83, 100, 6, S.TOOLS.TORCH);
    S.stroke(s, 150, 60, 170, 80, 3, M.MOLTEN);
    S.stroke(s, 20, 120, 60, 110, 4, S.TOOLS.ERASE);
    S.paint(s, 220, 115, 5, S.TOOLS.FROST);
  };
  const a = SC.starter();
  const b = SC.starter();
  for (let k = 0; k < 6; k++) {
    strokes(a);
    strokes(b);
    S.stepN(a, 40);
    S.stepN(b, 40);
  }
  sameWorld(a, b, "two runs");
  const c = SC.starter(12345);
  strokes(c);
  S.stepN(c, 40);
  assert.notDeepEqual(c.mat, a.mat, "a different seed gives a different world");
});

test("a closed box with no reactions keeps its heat", () => {
  // solids that never react below their points: stone, iron, glass; no air anywhere
  const s = box(48, 32, 20);
  S.fillRect(s, 10, 8, 20, 18, M.IRON, 900);
  S.fillRect(s, 30, 4, 40, 28, M.GLASS, 400);
  S.fillRect(s, 2, 24, 8, 30, M.STONE, -40);
  const e0 = S.energy(s);
  const peak0 = Math.max(...s.temp);
  const before = S.census(s);
  S.stepN(s, 400);
  assert.deepEqual(S.census(s), before, "nothing changed state");
  const e1 = S.energy(s);
  assert.ok(Math.abs(e1 - e0) / Math.abs(e0) < 1e-4, `energy ${e0} -> ${e1}`);
  assert.ok(Math.max(...s.temp) < peak0 - 100, "and the heat did spread out");
});

test("ore melts above its point and only above it (sweep)", () => {
  for (let t = 900; t <= 1080; t += 10) {
    const s = box(9, 9, t);
    S.setCell(s, 4, 4, M.ORE, t);
    S.stepN(s, 3);
    const melted = s.mat[4 * 9 + 4] === M.MOLTEN;
    assert.equal(melted, t > S.POINTS.oreMelt, `ore at ${t} C`);
  }
});

test("sand fuses to glass above its point and only above it (sweep)", () => {
  for (let t = 1380; t <= 1520; t += 10) {
    const s = box(9, 9, t);
    S.setCell(s, 4, 4, M.SAND, t);
    S.stepN(s, 3);
    assert.equal(s.mat[4 * 9 + 4] === M.GLASS, t > S.POINTS.sandFuse, `sand at ${t} C`);
  }
});

test("molten iron poured into water gives iron and steam", () => {
  const s = S.createWorld(9, 60, 50);
  S.fillRect(s, 0, 46, 59, 49, M.STONE);
  S.fillRect(s, 0, 20, 1, 45, M.STONE);
  S.fillRect(s, 58, 20, 59, 45, M.STONE);
  S.fillRect(s, 2, 30, 57, 45, M.WATER);
  S.fillRect(s, 25, 4, 34, 9, M.MOLTEN, 1500);
  const poured = count(s, M.MOLTEN);
  let steamSeen = 0;
  for (let k = 0; k < 1500 && count(s, M.MOLTEN) > 0; k++) {
    S.step(s);
    steamSeen = Math.max(steamSeen, count(s, M.STEAM));
  }
  assert.equal(count(s, M.MOLTEN), 0, "all the iron set");
  assert.equal(count(s, M.IRON) + count(s, M.SHOT), poured, "not a cell of iron lost");
  assert.ok(count(s, M.SHOT) > 0, "drips quenched into iron shot");
  assert.ok(s.events.quenched > 0 && steamSeen > 0, "and the water hissed into steam");
});

test("wood burns and burns out", () => {
  const s = S.createWorld(3, 60, 40);
  S.fillRect(s, 0, 36, 59, 39, M.STONE);
  S.fillRect(s, 20, 30, 40, 31, M.WOOD);
  const wood = count(s, M.WOOD);
  S.paint(s, 30, 30, 3, S.TOOLS.TORCH);
  for (let k = 0; k < 8; k++) S.paint(s, 30, 30, 3, S.TOOLS.TORCH);
  let fireSeen = 0;
  let k = 0;
  for (; k < 6000; k++) {
    S.step(s);
    fireSeen = Math.max(fireSeen, count(s, M.FIRE));
    if (!count(s, M.WOOD) && !count(s, M.FIRE) && !count(s, M.EMBER)) break;
  }
  assert.ok(wood > 0 && fireSeen > 0, "it caught");
  assert.equal(count(s, M.WOOD), 0, "every bit of wood went");
  assert.equal(count(s, M.EMBER) + count(s, M.FIRE), 0, `and the fire went out (step ${k})`);
});

test("ice thaws and water boils", () => {
  const s = box(9, 9, 60);
  S.setCell(s, 4, 4, M.ICE, 60);
  S.stepN(s, 400);
  assert.notEqual(s.mat[40], M.ICE, "ice in a warm box melts");
  const t = box(9, 9, 150);
  S.setCell(t, 4, 4, M.WATER, 150);
  S.step(t);
  assert.equal(t.mat[40], M.STEAM);
});

test("a fast stroke leaves no gaps", () => {
  for (const radius of [1, 2, 5, 9]) {
    const s = S.createWorld(1);
    S.paint(s, 3, 3, radius, M.STONE);
    S.stroke(s, 3, 3, 236, 131, radius, M.STONE);
    // every column the line crosses holds stone near the line
    for (let x = 3; x <= 236; x++) {
      const y = Math.round(3 + ((x - 3) * 128) / 233);
      let hit = false;
      for (let dy = -radius - 1; dy <= radius + 1 && !hit; dy++) {
        if (S.inside(s, x, y + dy) && s.mat[(y + dy) * s.w + x] === M.STONE) hit = true;
      }
      assert.ok(hit, `radius ${radius}: gap at column ${x}`);
    }
  }
});

test("paint stays inside the grid at every edge (sweep)", () => {
  const tools = [S.TOOLS.TORCH, S.TOOLS.FROST, S.TOOLS.ERASE, M.SAND, M.WATER, M.STONE, M.MOLTEN, M.FIRE];
  const xs = [-20, -1, -0.4, 0, 0.5, 3, 119.5, 236, 239, 239.6, 240, 260];
  const ys = [-20, -1, 0, 0.5, 67, 133, 134, 134.7, 135, 150];
  for (const tool of tools) {
    for (const radius of [0, 1, 4, 13]) {
      const s = S.createWorld(2);
      const n = s.mat.length;
      for (const x of xs) {
        for (const y of ys) {
          const changed = S.paint(s, x, y, radius, tool);
          // a dab can only touch cells within reach that exist
          let room = 0;
          const rr = radius * radius + radius * 0.6;
          for (let cy = 0; cy < s.h; cy++) {
            for (let cx = 0; cx < s.w; cx++) if ((cx - x) ** 2 + (cy - y) ** 2 <= rr) room++;
          }
          assert.ok(changed <= room, `${tool} r${radius} at ${x},${y}: ${changed} > ${room}`);
        }
      }
      assert.equal(s.mat.length, n);
      assert.ok(s.temp.every(Number.isFinite), "no broken heat");
      assert.ok(Math.min(...s.temp) >= S.T_MIN && Math.max(...s.temp) <= S.T_MAX);
      S.stepN(s, 5);
    }
  }
});

test("render writes no NaN for any material at any temperature, and hot cells glow", () => {
  const temps = [];
  for (let t = S.T_MIN; t <= S.T_MAX; t += 20) temps.push(t);
  const s = S.createWorld(4, S.MAT_COUNT * 4, temps.length);
  for (let y = 0; y < s.h; y++) {
    for (let x = 0; x < s.w; x++) S.setCell(s, x, y, x >> 2, temps[y]);
  }
  s.flash.fill(0.5, 0, 200);
  const { bw, bh } = R.bloomSize(s.w, s.h);
  for (const heat of [false, true]) {
    const out = new Float32Array(s.w * s.h * 4); // keeps a NaN where a clamped array would hide it
    const glow = new Float32Array(bw * bh * 3);
    R.render(s, out, glow, { heat, time: 77 });
    assert.ok(out.every(Number.isFinite), `pixels finite (heat view ${heat})`);
    assert.ok(glow.every(Number.isFinite), "glow finite");
    const b = new Float32Array(bw * bh * 4);
    R.bloom(glow, bw, bh, b, 1.5);
    assert.ok(b.every(Number.isFinite), "bloom finite");
  }
  // iron at 20 C against iron at 1300 C
  const cold = box(16, 16, 20, M.IRON);
  const hot = box(16, 16, 1300, M.IRON);
  const px = (w) => {
    const rgba = new Uint8ClampedArray(w.w * w.h * 4);
    const g = new Float32Array(16 * 3);
    R.render(w, rgba, g);
    return { rgba, glow: g.reduce((a, v) => a + v, 0) };
  };
  const c = px(cold);
  const h = px(hot);
  assert.equal(c.glow, 0, "cold iron gives no light");
  assert.ok(h.glow > 0, "hot iron lights the glow buffer");
  assert.ok(h.rgba[0] > 240 && h.rgba[0] > c.rgba[0] + 60, "and looks orange-white");
  const bb = R.blackbody(1300);
  assert.ok(bb[0] >= bb[1] && bb[1] >= bb[2] && bb[3] > 0.9, "blackbody: red over green over blue");
  assert.deepEqual(R.blackbody(300), [0, 0, 0, 0], "nothing glows below a dull red");
});

test("the codec round trip is exact", () => {
  for (const make of [SC.starter, SC.showcase, ...SC.SEEDS.map((x) => x.build)]) {
    const s = make();
    S.stepN(s, 30);
    const data = C.encode(s);
    const back = C.decode(JSON.parse(JSON.stringify(data)));
    assert.deepEqual(back.mat, s.mat);
    assert.deepEqual(back.life, s.life);
    for (let i = 0; i < s.temp.length; i++) assert.ok(back.temp[i] === Math.round(s.temp[i]), `heat at ${i}`);
    assert.equal(back.tick, s.tick);
    assert.equal(back.seed, s.seed);
    assert.deepEqual(C.encode(back), data, "encode(decode(x)) is x");
    // a decoded world runs on deterministically
    const again = C.decode(data);
    S.stepN(back, 25);
    S.stepN(again, 25);
    sameWorld(back, again, "two decodes");
  }
});

test("junk keepsakes throw a plain SceneError, never a TypeError (sweep)", () => {
  const good = C.encode(SC.starter());
  const junk = [
    undefined,
    null,
    0,
    "scene",
    [],
    true,
    {},
    { v: 2 },
    { v: "1" },
    { ...good, w: "240" },
    { ...good, w: 4, h: 4 },
    { ...good, w: 1e6, h: 1e6 },
    { ...good, w: -240 },
    { ...good, mat: undefined },
    { ...good, mat: 12 },
    { ...good, mat: "%%%not base64%%%" },
    { ...good, mat: good.mat.slice(0, 40) },
    { ...good, heat: good.heat.slice(0, -8) },
    { ...good, life: btoa("\u0000\u0001") },
    { ...good, mat: btoa("\u00ff\u0063".repeat(130)) }, // material 99
    { ...good, mat: good.heat },
    { ...good, h: 134 },
    Object.create(null),
  ];
  for (const [n, data] of junk.entries()) {
    assert.throws(
      () => C.decode(data),
      (e) => e instanceof C.SceneError && e.constructor !== TypeError && e.message.length > 5,
      `junk ${n}`,
    );
  }
  // odd but readable fields are tolerated
  const odd = C.decode({ ...good, tick: -3, ambient: 1e9, seed: "x" });
  assert.equal(odd.tick, 0);
  assert.equal(odd.ambient, S.T_MAX);
});

test("scenes are deterministic", () => {
  for (const make of [SC.starter, SC.showcase, ...SC.SEEDS.map((x) => x.build)]) {
    const a = make();
    const b = make();
    sameWorld(a, b, make.name);
    S.stepN(a, 20);
    S.stepN(b, 20);
    sameWorld(a, b, `${make.name} after 20 steps`);
  }
});

test("the starter forge melts its ore and quenches some of it", () => {
  const s = SC.starter();
  S.stepN(s, 700);
  assert.ok(s.events.melted > 300, `melted ${s.events.melted}`);
  assert.ok(s.events.quenched > 0, "some reached the water");
  assert.ok(s.events.lit > 0, "the coal bed is burning");
});

test("every seed file decodes, matches its scene and stays small", () => {
  const files = readdirSync(SEED_DIR).filter((f) => f.endsWith(".json"));
  assert.deepEqual(files.sort(), SC.SEEDS.map((x) => `${x.slug}.json`).sort(), "one file per seed");
  for (const seed of SC.SEEDS) {
    const text = readFileSync(new URL(`${seed.slug}.json`, SEED_DIR), "utf8");
    const row = JSON.parse(text);
    assert.equal(row.name, seed.name);
    assert.equal(row.note, seed.note);
    assert.equal(row.author, "Claude");
    assert.match(row.made, /^2026-10-09T\d\d:\d\d:\d\d$/);
    assert.ok(JSON.stringify(row.data).length < 100_000, `${seed.slug} is small`);
    const s = C.decode(row.data);
    sameWorld(s, C.decode(C.encode(seed.build())), `${seed.slug} is what make_seeds writes`);
  }
});

test("the text picture for play.py shows the forge", () => {
  const lines = picture(SC.starter(), 80);
  assert.ok(lines.length > 10 && lines.every((l) => l.length <= 80));
  const all = lines.join("\n");
  for (const ch of ["#", "~", "o", ":", "="]) assert.ok(all.includes(ch), `has ${ch}`);
});
