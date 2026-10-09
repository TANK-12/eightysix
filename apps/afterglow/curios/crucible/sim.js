/* Crucible's world: a falling-sand grid with a temperature field.
 *
 * One cell holds a material (mat), a temperature in degrees C (temp), a
 * counter for things that burn out (life) and a shade byte so grains keep
 * their own tint as they move. Everything lives in typed arrays, and every
 * random choice comes from the kit's seeded rng, so the same seed and the
 * same strokes always give the same world. No DOM: node tests import this.
 *
 * One step: move (powders fall, liquids flow and level, gases rise), then
 * heat (pairwise exchange between neighbours, so a closed box keeps its
 * energy), then react (melting, freezing, burning, quenching).
 */

import { rng, hashString } from "../_kit/rng.js";

export const W = 240;
export const H = 135;
export const AMBIENT = 20;
export const T_MIN = -60;
export const T_MAX = 2400;

export const M = {
  EMPTY: 0,
  STONE: 1,
  SAND: 2,
  WATER: 3,
  ORE: 4,
  MOLTEN: 5,
  IRON: 6,
  COAL: 7,
  EMBER: 8,
  FIRE: 9,
  STEAM: 10,
  ICE: 11,
  WOOD: 12,
  GLASS: 13,
  SHOT: 14,
};
export const MAT_COUNT = 15;

export const KIND = { AIR: 0, SOLID: 1, POWDER: 2, LIQUID: 3, GAS: 4 };

/** Where each change of state happens, in degrees C. */
export const POINTS = {
  oreMelt: 980,
  ironMelt: 1150,
  ironFreeze: 640,
  superheat: 1320,
  boil: 100,
  condense: 92,
  freeze: -3,
  thaw: 1,
  coalIgnite: 340,
  woodIgnite: 280,
  sandFuse: 1450,
  emberHeat: 1700,
};

// id, label, kind, density, conductivity, heat capacity, colour, start temp, tip
const TABLE = [
  [M.EMPTY, "air", KIND.AIR, 0, 0.025, 0.6, [12, 10, 20], AMBIENT, "Empty air"],
  [M.STONE, "stone", KIND.SOLID, 0, 0.05, 1.2, [96, 90, 100], AMBIENT, "Stone: a fixed wall that warms up slowly"],
  [M.SAND, "sand", KIND.POWDER, 15, 0.04, 1.0, [214, 180, 118], AMBIENT, "Sand: falls and piles; fuses to glass if you get it hot enough"],
  [M.WATER, "water", KIND.LIQUID, 10, 0.08, 4.0, [48, 108, 206], AMBIENT, "Water: flows and levels out, soaks up heat, boils to steam"],
  [M.ORE, "ore", KIND.POWDER, 30, 0.1, 1.0, [128, 70, 56], AMBIENT, "Iron ore: heavy grains that melt into molten iron past 1100 C"],
  [M.MOLTEN, "molten iron", KIND.LIQUID, 70, 0.1, 3.0, [255, 120, 30], 1500, "Molten iron: a glowing heavy liquid; touch it to water for a hiss"],
  [M.IRON, "iron", KIND.SOLID, 0, 0.22, 1.0, [150, 162, 184], AMBIENT, "Iron: a solid ingot that conducts heat well and melts again past 1150 C"],
  [M.COAL, "coal", KIND.POWDER, 13, 0.05, 1.0, [36, 33, 38], AMBIENT, "Coal: catches past 340 C when it can breathe, then burns long and hot"],
  [M.EMBER, "live coal", KIND.POWDER, 13, 0.08, 1.0, [70, 30, 22], 1300, "Live coal: already burning"],
  [M.FIRE, "fire", KIND.GAS, -2, 0.15, 1.0, [255, 140, 40], 1150, "Fire: rises, flickers and dies, heating what it touches"],
  [M.STEAM, "steam", KIND.GAS, -1, 0.04, 1.5, [196, 206, 222], 115, "Steam: rises, cools and condenses back to water"],
  [M.ICE, "ice", KIND.SOLID, 0, 0.12, 2.0, [168, 214, 240], -30, "Ice: a cold solid that melts into water"],
  [M.WOOD, "wood", KIND.SOLID, 0, 0.03, 1.2, [124, 84, 50], AMBIENT, "Wood: a fixed beam that chars into fire and live coal"],
  [M.GLASS, "glass", KIND.SOLID, 0, 0.04, 1.0, [118, 196, 186], AMBIENT, "Glass: what sand becomes in a fierce heat"],
  [M.SHOT, "iron shot", KIND.POWDER, 60, 0.18, 1.0, [116, 124, 140], AMBIENT, "Iron shot: the beads molten iron makes when it drips into water; they sink and melt again past 1150 C"],
];

export const MATERIALS = TABLE.map(([id, label, kind, density, cond, cap, color, start, tip]) => ({
  id,
  label,
  kind,
  density,
  cond,
  cap,
  color,
  start,
  tip,
}));

const KINDS = new Uint8Array(MAT_COUNT);
const DENS = new Int8Array(MAT_COUNT);
const INV_CAP = new Float32Array(MAT_COUNT);
const PAIR = new Float32Array(MAT_COUNT * MAT_COUNT); // conductance between two materials
for (const m of MATERIALS) {
  KINDS[m.id] = m.kind;
  DENS[m.id] = m.density;
  INV_CAP[m.id] = 1 / m.cap;
}
for (const a of MATERIALS) {
  for (const b of MATERIALS) {
    PAIR[a.id * MAT_COUNT + b.id] = (2 * a.cond * b.cond) / (a.cond + b.cond);
  }
}
// How readily a powder slides off a pile: sand runs, ore is lumpy.
const SLIDE = new Float32Array(MAT_COUNT);
SLIDE[M.SAND] = 1;
SLIDE[M.ORE] = 0.45;
SLIDE[M.COAL] = 0.7;
SLIDE[M.EMBER] = 0.7;
SLIDE[M.SHOT] = 0.9;
// How far a liquid looks sideways in one step.
const SPREAD = new Uint8Array(MAT_COUNT);
SPREAD[M.WATER] = 5;
SPREAD[M.MOLTEN] = 3;

export const kindOf = (m) => KINDS[m];

/** A fresh, empty world at room temperature. */
export function createWorld(seed = 1, w = W, h = H, ambient = AMBIENT) {
  const n = w * h;
  const s = {
    w,
    h,
    seed: seed >>> 0,
    tick: 0,
    ambient,
    mat: new Uint8Array(n),
    temp: new Float32Array(n).fill(ambient),
    life: new Uint16Array(n),
    shade: new Uint8Array(n),
    flash: new Float32Array(n),
    moved: new Uint8Array(n),
    delta: new Float32Array(n),
    rand: rng(seed >>> 0),
    events: { melted: 0, quenched: 0, glassed: 0, lit: 0, boiled: 0 },
  };
  const r = rng(hashString(`shade:${s.seed}`));
  for (let i = 0; i < n; i++) s.shade[i] = (r() * 256) | 0;
  return s;
}

/** Restart the random stream as a function of seed and tick (used after loading). */
export function reseed(s) {
  s.rand = rng(hashString(`${s.seed}:${s.tick}`));
}

function lifeFor(m, r) {
  if (m === M.FIRE) return 18 + ((r() * 34) | 0);
  if (m === M.EMBER) return 1400 + ((r() * 900) | 0);
  return 0;
}

/** Put material m into cell i, at temperature t (default: the material's own). */
export function place(s, i, m, t) {
  s.mat[i] = m;
  s.temp[i] = t === undefined ? (MATERIALS[m].start === AMBIENT ? s.ambient : MATERIALS[m].start) : t;
  s.life[i] = lifeFor(m, s.rand);
  s.shade[i] = (s.rand() * 256) | 0;
}

export function inside(s, x, y) {
  return x >= 0 && y >= 0 && x < s.w && y < s.h;
}

function swap(s, i, j) {
  const { mat, temp, life, shade, moved } = s;
  let t = mat[i];
  mat[i] = mat[j];
  mat[j] = t;
  const tt = temp[i];
  temp[i] = temp[j];
  temp[j] = tt;
  t = life[i];
  life[i] = life[j];
  life[j] = t;
  t = shade[i];
  shade[i] = shade[j];
  shade[j] = t;
  moved[i] = 1;
  moved[j] = 1;
}

/** Can a falling m move into a cell holding t (and should it, this step)? */
function sinksInto(m, t, r) {
  const k = KINDS[t];
  if (k === KIND.AIR || k === KIND.GAS) return true;
  if (k === KIND.LIQUID && DENS[t] < DENS[m]) return r() < 0.5;
  // a heavy liquid trickles down through lighter grains (molten iron through coal)
  if (k === KIND.POWDER && KINDS[m] === KIND.LIQUID && DENS[t] < DENS[m]) return r() < 0.3;
  return false;
}

function fall(s, x, y, i, m) {
  const { w, h, mat } = s;
  const r = s.rand;
  if (y + 1 >= h) return;
  const below = i + w;
  if (sinksInto(m, mat[below], r)) {
    swap(s, i, below);
    return;
  }
  const kind = KINDS[m];
  if (kind === KIND.POWDER && r() >= SLIDE[m]) return;
  const d = r() < 0.5 ? -1 : 1;
  for (const dx of [d, -d]) {
    const nx = x + dx;
    if (nx < 0 || nx >= w) continue;
    const j = below + dx;
    const side = mat[i + dx];
    if (KINDS[side] === KIND.SOLID) continue; // no squeezing through a wall's corner
    if (sinksInto(m, mat[j], r)) {
      swap(s, i, j);
      return;
    }
  }
  if (kind !== KIND.LIQUID) return;
  // Flow sideways to the furthest free cell within reach, so pools level out.
  if (m === M.MOLTEN && r() < 0.25) return;
  const reach = SPREAD[m];
  for (const dx of [d, -d]) {
    let free = 0;
    for (let k = 1; k <= reach; k++) {
      const nx = x + dx * k;
      if (nx < 0 || nx >= w) break;
      const t = mat[i + dx * k];
      const tk = KINDS[t];
      if (tk === KIND.AIR || tk === KIND.GAS) free = k;
      else break;
      if (y + 1 < h && sinksInto(m, mat[i + dx * k + w], () => 0)) break; // found a drop: stop at its edge
    }
    if (free) {
      swap(s, i, i + dx * free);
      return;
    }
  }
}

function rise(s, x, y, i, m) {
  const { w, mat } = s;
  const r = s.rand;
  if (m === M.FIRE && r() < 0.25) return; // flames hang and flicker a little
  const up = i - w;
  if (y > 0) {
    const t = mat[up];
    if (t === M.EMPTY || (m === M.STEAM && KINDS[t] === KIND.LIQUID && r() < 0.6)) {
      swap(s, i, up);
      return;
    }
  }
  const d = r() < 0.5 ? -1 : 1;
  for (const dx of [d, -d]) {
    const nx = x + dx;
    if (nx < 0 || nx >= w) continue;
    if (y > 0 && mat[up + dx] === M.EMPTY && KINDS[mat[i + dx]] !== KIND.SOLID) {
      swap(s, i, up + dx);
      return;
    }
  }
  const nx = x + d;
  if (nx >= 0 && nx < w && mat[i + d] === M.EMPTY && r() < 0.5) swap(s, i, i + d);
}

function move(s) {
  const { w, h, mat, moved } = s;
  moved.fill(0);
  for (let y = h - 1; y >= 0; y--) {
    const ltr = ((y + s.tick) & 1) === 0;
    for (let n = 0; n < w; n++) {
      const x = ltr ? n : w - 1 - n;
      const i = y * w + x;
      if (moved[i]) continue;
      const m = mat[i];
      const k = KINDS[m];
      if (k === KIND.POWDER || k === KIND.LIQUID) fall(s, x, y, i, m);
      else if (k === KIND.GAS) rise(s, x, y, i, m);
    }
  }
}

/** Heat flows between every pair of neighbours; the borders are insulated. */
export function diffuse(s) {
  const { w, h, mat, temp, delta } = s;
  for (let y = 0; y < h; y++) {
    const row = y * w;
    for (let x = 0; x < w; x++) {
      const i = row + x;
      const a = mat[i];
      const ta = temp[i];
      const ia = INV_CAP[a];
      const pa = a * MAT_COUNT;
      if (x + 1 < w) {
        const j = i + 1;
        const b = mat[j];
        const f = PAIR[pa + b] * (temp[j] - ta);
        delta[i] += f * ia;
        delta[j] -= f * INV_CAP[b];
      }
      if (y + 1 < h) {
        const j = i + w;
        const b = mat[j];
        const f = PAIR[pa + b] * (temp[j] - ta);
        delta[i] += f * ia;
        delta[j] -= f * INV_CAP[b];
      }
    }
  }
  const amb = s.ambient;
  for (let i = 0; i < delta.length; i++) {
    let t = temp[i] + delta[i];
    delta[i] = 0;
    const m = mat[i];
    if (m === M.EMPTY) t += (amb - t) * 0.006; // open air carries heat away
    else if (m === M.STEAM) t += (amb - t) * 0.004;
    temp[i] = t < T_MIN ? T_MIN : t > T_MAX ? T_MAX : t;
  }
}

function hasNeighbour(s, i, x, y, want) {
  const { w, h, mat } = s;
  return (
    (x > 0 && mat[i - 1] === want) ||
    (x + 1 < w && mat[i + 1] === want) ||
    (y > 0 && mat[i - w] === want) ||
    (y + 1 < h && mat[i + w] === want)
  );
}

function quench(s, i, j) {
  // j is water or ice touching molten iron at i
  s.mat[j] = M.STEAM;
  s.temp[j] = 130;
  s.life[j] = 0;
  s.flash[j] = 1;
  s.flash[i] = 1;
  s.temp[i] -= 260;
  if (s.mat[i] === M.MOLTEN) {
    // a drip that meets water bursts into beads of iron shot
    s.mat[i] = M.SHOT;
    s.events.quenched++;
  }
}

function react(s) {
  const { w, h, mat, temp, life, flash } = s;
  const r = s.rand;
  const P = POINTS;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      if (flash[i] > 0.01) flash[i] *= 0.9;
      else flash[i] = 0;
      const m = mat[i];
      if (m === M.EMPTY || m === M.STONE) continue;
      const t = temp[i];
      switch (m) {
        case M.WATER:
          if (t > P.boil) {
            mat[i] = M.STEAM;
            s.events.boiled++;
          } else if (t < P.freeze) mat[i] = M.ICE;
          break;
        case M.ICE:
          // melting takes heat: a warm face gives way a grain at a time
          if (t > P.thaw && r() < 0.0006 * (t - P.thaw)) {
            mat[i] = M.WATER;
            temp[i] = 0.5;
          }
          break;
        case M.STEAM:
          if (t < P.condense && r() < 0.02) mat[i] = M.WATER;
          break;
        case M.ORE:
          if (t > P.oreMelt) {
            // a melt runs hot: that is what lets a pour reach the trough
            mat[i] = M.MOLTEN;
            temp[i] = Math.max(t, P.superheat);
            s.events.melted++;
          }
          break;
        case M.IRON:
        case M.SHOT:
          if (t > P.ironMelt) mat[i] = M.MOLTEN;
          break;
        case M.SAND:
          if (t > P.sandFuse) {
            mat[i] = M.GLASS;
            flash[i] = 0.6;
            s.events.glassed++;
          }
          break;
        case M.MOLTEN: {
          for (const j of [i - 1, i + 1, i - w, i + w]) {
            if (j < 0 || j >= mat.length) continue;
            if ((j === i - 1 && x === 0) || (j === i + 1 && x === w - 1)) continue;
            if (mat[j] === M.WATER || mat[j] === M.ICE) {
              quench(s, i, j);
              break;
            }
          }
          if (mat[i] === M.MOLTEN && temp[i] < P.ironFreeze && r() < 0.03) mat[i] = M.IRON;
          break;
        }
        case M.COAL:
          // coal catches when hot and breathing, or creeps alight from a live neighbour
          if (
            t > P.coalIgnite &&
            (hasNeighbour(s, i, x, y, M.EMPTY) ||
              hasNeighbour(s, i, x, y, M.FIRE) ||
              (r() < 0.004 && hasNeighbour(s, i, x, y, M.EMBER)))
          ) {
            mat[i] = M.EMBER;
            life[i] = lifeFor(M.EMBER, r);
            s.events.lit++;
          }
          break;
        case M.WOOD:
          if (t > P.woodIgnite && r() < 0.02) {
            if (r() < 0.45) {
              mat[i] = M.FIRE;
              life[i] = 40 + ((r() * 60) | 0);
              temp[i] = Math.max(t, 900);
            } else {
              mat[i] = M.EMBER;
              life[i] = 300 + ((r() * 300) | 0);
            }
          }
          break;
        case M.EMBER:
          ember(s, i, x, y, r);
          break;
        case M.FIRE:
          if (hasNeighbour(s, i, x, y, M.WATER)) {
            mat[i] = M.EMPTY;
            break;
          }
          temp[i] = Math.max(t, 1050 + r() * 350);
          if (life[i] <= 1) mat[i] = M.EMPTY;
          else life[i]--;
          break;
      }
    }
  }
}

function ember(s, i, x, y, r) {
  const { w, mat, temp, life } = s;
  for (const j of [i - 1, i + 1, i - w, i + w]) {
    if (j < 0 || j >= mat.length) continue;
    if ((j === i - 1 && x === 0) || (j === i + 1 && x === s.w - 1)) continue;
    if (mat[j] === M.WATER) {
      mat[j] = M.STEAM;
      temp[j] = 120;
      mat[i] = M.COAL;
      temp[i] = Math.min(temp[i], 180);
      s.flash[j] = 0.5;
      return;
    }
  }
  const breathes = hasNeighbour(s, i, x, y, M.EMPTY) || hasNeighbour(s, i, x, y, M.FIRE);
  if (breathes) {
    temp[i] += (POINTS.emberHeat - temp[i]) * 0.07;
    if (y > 0 && mat[i - w] === M.EMPTY && r() < 0.07) {
      place(s, i - w, M.FIRE);
    }
    life[i] = life[i] > 0 ? life[i] - 1 : 0;
  } else {
    // smothered: it smoulders, cooler and slower
    temp[i] += (POINTS.emberHeat * 0.75 - temp[i]) * 0.03;
    if (r() < 0.25) life[i] = life[i] > 0 ? life[i] - 1 : 0;
  }
  if (life[i] === 0) {
    mat[i] = r() < 0.5 ? M.EMPTY : M.FIRE;
    life[i] = mat[i] === M.FIRE ? 10 : 0;
  }
}

/** One deterministic step of the world. */
export function step(s) {
  move(s);
  diffuse(s);
  react(s);
  s.tick++;
}

export function stepN(s, n) {
  for (let k = 0; k < n; k++) step(s);
}

/** Tools besides the materials: they act on heat or clear cells. */
export const TOOLS = { TORCH: "torch", FROST: "frost", ERASE: "erase" };

/**
 * Paint a disc of radius r at (cx, cy). tool is a material id or one of TOOLS.
 * Materials only fill air, fire and steam (so a stroke never deletes what is
 * there); powders and liquids are sprinkled, not poured solid. Returns the
 * number of cells changed.
 */
export function paint(s, cx, cy, radius, tool) {
  const { w, h, mat, temp } = s;
  const rr = radius * radius + radius * 0.6;
  let changed = 0;
  const x0 = Math.max(0, Math.floor(cx - radius));
  const x1 = Math.min(w - 1, Math.ceil(cx + radius));
  const y0 = Math.max(0, Math.floor(cy - radius));
  const y1 = Math.min(h - 1, Math.ceil(cy + radius));
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const dx = x - cx;
      const dy = y - cy;
      const d2 = dx * dx + dy * dy;
      if (d2 > rr) continue;
      const i = y * w + x;
      if (tool === TOOLS.TORCH) {
        const fall = 1 - Math.sqrt(d2) / (radius + 1);
        temp[i] = Math.min(T_MAX, temp[i] + 60 * fall + 6);
        changed++;
      } else if (tool === TOOLS.FROST) {
        const fall = 1 - Math.sqrt(d2) / (radius + 1);
        temp[i] = Math.max(T_MIN, temp[i] - 30 * fall - 3);
        changed++;
      } else if (tool === TOOLS.ERASE) {
        if (mat[i] !== M.EMPTY) {
          place(s, i, M.EMPTY, s.ambient);
          changed++;
        }
      } else if (typeof tool === "number" && tool > 0 && tool < MAT_COUNT) {
        const here = KINDS[mat[i]];
        if (here !== KIND.AIR && here !== KIND.GAS) continue;
        const k = KINDS[tool];
        if ((k === KIND.POWDER || k === KIND.LIQUID || k === KIND.GAS) && s.rand() > 0.5) continue;
        place(s, i, tool);
        changed++;
      }
    }
  }
  return changed;
}

/**
 * Paint along the segment from (x0, y0) to (x1, y1), the start excluded (the
 * previous dab already covered it). Dabs sit at most half a brush apart, so
 * a fast stroke between two pointer events leaves no gaps.
 */
export function stroke(s, x0, y0, x1, y1, radius, tool) {
  const len = Math.hypot(x1 - x0, y1 - y0);
  const gap = Math.max(0.5, radius * 0.5);
  const n = Math.max(1, Math.ceil(len / gap));
  let changed = 0;
  for (let k = 1; k <= n; k++) {
    const f = k / n;
    changed += paint(s, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, radius, tool);
  }
  return changed;
}

/** Fill every cell of a rectangle (inclusive) with m; used by scene builders. */
export function fillRect(s, x0, y0, x1, y1, m, t) {
  for (let y = Math.max(0, y0); y <= Math.min(s.h - 1, y1); y++) {
    for (let x = Math.max(0, x0); x <= Math.min(s.w - 1, x1); x++) place(s, y * s.w + x, m, t);
  }
}

export function setCell(s, x, y, m, t) {
  if (inside(s, x, y)) place(s, y * s.w + x, m, t);
}

/** How many cells hold each material. */
export function census(s) {
  const out = new Array(MAT_COUNT).fill(0);
  for (let i = 0; i < s.mat.length; i++) out[s.mat[i]]++;
  return out;
}

/** Total heat (temperature times heat capacity) over the grid. */
export function energy(s) {
  let e = 0;
  for (let i = 0; i < s.mat.length; i++) e += s.temp[i] * MATERIALS[s.mat[i]].cap;
  return e;
}
