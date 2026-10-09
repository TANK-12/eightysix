// node --test curios/glyphs/ : the formula language on its own. The Python
// copy is held to the same answers by the agreement sweep in test_glyphs.py.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as L from "../lang.js";

const one = (src, t = 0) => L.frame(src, t, 1)[0];
const err = (src) => {
  try {
    L.parse(src);
  } catch (e) {
    assert.ok(e instanceof L.GlyphError, `${src}: ${e}`);
    return { message: e.message, col: e.col };
  }
  assert.fail(`${JSON.stringify(src)} parsed but should not`);
};

const HOSTILE = [
  "constructor", "__proto__", "prototype", "toString", "valueOf", "this",
  "globalThis", "process", "window", "import", "hasOwnProperty", "eval",
];

test("tokens carry 1-based columns and know every operator", () => {
  const toks = L.tokenize("sin(x) ** 2 >= .5e1");
  assert.deepEqual(
    toks.map((t) => [t.kind, t.text, t.col]),
    [
      ["name", "sin", 1], ["op", "(", 4], ["name", "x", 5], ["op", ")", 6],
      ["op", "**", 8], ["num", "2", 11], ["op", ">=", 13], ["num", ".5e1", 16],
      ["end", "", 20],
    ],
  );
  assert.deepEqual(err("x = y"), { message: "Use == to compare two values", col: 3 });
  assert.deepEqual(err("x $ y"), { message: "I do not know the character '$'", col: 3 });
  assert.deepEqual(err("1 + \u{1f600}"), { message: "I do not know the character '\u{1f600}'", col: 5 });
});

test("parse errors say what is wrong and where", () => {
  const cases = {
    "": ["Write a formula, for example sin(t - r)", 1],
    "x +": ["The formula ends too soon", 4],
    "sin(x": ["Missing ')' for the '(' at column 4", 6],
    "(x y": ["Expected ')' for the '(' at column 1, found 'y'", 4],
    "x ? 1": ["Missing ':' for the '?' at column 3", 6],
    "sin": ["'sin' is a function: write sin(...)", 1],
    "t(1)": ["'t' is a value, not a function", 1],
    "hypot(x)": ["'hypot' takes 2 values, got 1", 1],
    "min()": ["'min' takes at least 1 value, got 0", 1],
    "noise()": ["'noise' takes 1 to 3 values, got 0", 1],
    "x y": ["Missing an operator before 'y'", 3],
    "x)": ["Did not expect ')'", 2],
    "x +* y": ["Expected a value, found '*'", 4],
  };
  for (const [src, [message, col]] of Object.entries(cases)) {
    assert.deepEqual(err(src), { message, col }, src);
  }
});

test("precedence, unary minus and right-leaning powers", () => {
  const show = (src) => L.show(L.parse(src));
  assert.equal(show("1 + 2 * 3"), "(1 + (2 * 3))");
  assert.equal(show("1 - 2 - 3"), "((1 - 2) - 3)");
  assert.equal(show("-2 ** 2"), "(-(2 ** 2))");
  assert.equal(show("2 ** -1"), "(2 ** (-1))");
  assert.equal(show("2 ^ 3 ^ 2"), "(2 ** (3 ** 2))");
  assert.equal(show("+-x"), "(-x)");
  assert.equal(show("1 + 2 & 3 | 4 < 5 && 6 || 7"), "((((((1 + 2) & 3) | 4) < 5) && 6) || 7)");
  assert.equal(show("a ? r ? 1 : 2 : 3"), "(a ? (r ? 1 : 2) : 3)");
  assert.equal(one("-2 ** 2"), -4);
  assert.equal(one("2 ** 3 ** 2"), 512);
  assert.equal(one("1 + 2 * 3 - 4 / 2"), 5);
  assert.equal(one("- - 3"), 3);
  assert.equal(one("!0 + !5"), 1);
});

test("% keeps the dividend's sign, mod() never goes negative", () => {
  assert.equal(one("-7 % 2"), -1);
  assert.equal(one("7 % -2"), 1);
  assert.equal(one("mod(-7, 2)"), 1);
  assert.equal(one("mod(7, -2)"), -1);
});

test("& and | work on 32-bit integers", () => {
  assert.equal(one("6 & 3"), 2);
  assert.equal(one("6 | 3"), 7);
  assert.equal(one("2147483648 | 0"), -2147483648);
  assert.equal(one("4294967297 | 0"), 1);
  assert.equal(one("-1.9 | 0"), -1);
  assert.equal(one("1e20 | 0"), 1661992960);
});

test("round is floor(v + 0.5), and the other little helpers", () => {
  assert.equal(one("round(2.5)"), 3);
  assert.equal(one("round(-2.5)"), -2);
  assert.equal(one("round(-2.6)"), -3);
  assert.equal(one("fract(-1.25)"), 0.75);
  assert.equal(one("sign(-3) + sign(0) * 10"), -1);
  assert.equal(one("clamp(9, 0, 4) + mix(0, 10, 0.25)"), 6.5);
  assert.equal(one("min(3, 1, 2) + max(3, 1, 2)"), 4);
});

test("NaN and Infinity never escape: 1/0 and 0/0 are 0", () => {
  for (const src of ["1/0", "0/0", "-1/0", "1e999", "1e308 * 10", "x % 0", "log(0)", "sqrt(-1)",
    "exp(1000)", "pow(-8, 1/3)", "pow(0, -1)", "hypot(1e308, 1e308) * 2", "mod(1, 0)"]) {
    assert.equal(one(src), 0, src);
  }
  assert.deepEqual(L.frame("t * x", Infinity, 2), [0, 0, 0, 0]);
  assert.deepEqual(L.frame("t", NaN, 2), [0, 0, 0, 0]);
});

test("noise and rand are deterministic and stay in range", () => {
  for (let k = 0; k < 500; k++) {
    const p = [k * 0.37, -k * 0.11, k * 1.7];
    const v = L.noise(...p);
    assert.equal(v, L.noise(...p));
    assert.ok(v >= -1 && v <= 1, `${p}: ${v}`);
    const r = L.rand(k - 250);
    assert.ok(r >= 0 && r <= 1);
  }
  assert.equal(L.rand(3), L.rand(3.9));
  assert.notEqual(L.rand(3), L.rand(4));
  assert.equal(L.noise(2, 3, 4), L.noise(2, 3, 4));
  assert.equal(L.noise(1.5), L.noise(1.5, 0, 0));
  const a = L.frame("rand()", 0, 4);
  assert.deepEqual(a, L.frame("rand(i)", 9, 4));
});

test("frame gives n*n finite numbers for every n and odd t", () => {
  for (const n of [1, 2, 7, 16, 64]) {
    for (const t of [0, -3.5, 1e6, 1e300]) {
      const v = L.frame("sin(t - r) * noise(x, y, t) / (u * v) + rand() + a ** 3", t, n);
      assert.equal(v.length, n * n);
      assert.ok(v.every(Number.isFinite), `n=${n} t=${t}`);
    }
  }
  const g = L.geometry(4);
  assert.deepEqual([g.x[5], g.y[5], g.u[5], g.v[5]], [1, 1, -0.5, -0.5]);
});

test("length and nesting limits", () => {
  const long = "x+".repeat(200) + "x";
  assert.deepEqual(err(long), { message: "Keep it under 400 characters (this one has 401)", col: 401 });
  assert.ok(L.prepare("x+".repeat(199) + "x").ok);
  assert.ok(L.prepare("(".repeat(31) + "x" + ")".repeat(31)).ok);
  for (const deep of [
    "(".repeat(33) + "x" + ")".repeat(33),
    "-".repeat(33) + "x",
    "sin(".repeat(33) + "x" + ")".repeat(33),
    "x ? ".repeat(33) + "1" + " : 0".repeat(33),
    "2 ** ".repeat(33) + "2",
  ]) {
    assert.match(err(deep).message, /^Nested too deeply/, deep.slice(0, 20));
  }
});

test("names outside the language are unknown, never looked up", () => {
  for (const name of HOSTILE) {
    for (const [src, col] of [[name, 1], [`${name}(x)`, 1], [`x + ${name}`, 5]]) {
      const e = err(src);
      assert.match(e.message, new RegExp(`^Unknown name '${name}'`), src);
      assert.equal(e.col, col, src);
    }
  }
  assert.deepEqual(err("sin.constructor"), { message: "I do not know the character '.'", col: 4 });
  assert.equal(err("x[0]").message, "I do not know the character '['");
  assert.equal(err("'a'").message, "I do not know the character '''");
});

test("typos get a suggestion, swapped letters included", () => {
  assert.equal(err("sni(t)").message, "Unknown name 'sni' (did you mean 'sin'?)");
  assert.equal(err("hypt(x, y)").message, "Unknown name 'hypt' (did you mean 'hypot'?)");
  assert.equal(err("nosie(x)").message, "Unknown name 'nosie' (did you mean 'noise'?)");
  assert.equal(err("tt").message, "Unknown name 'tt' (did you mean 't'?)");
  assert.equal(L.suggest("q"), "");
  assert.equal(L.suggest("zzzzzz"), "");
});

test("prepare wraps errors and never throws on junk", () => {
  for (const junk of [null, undefined, 42, {}, [], "\u0000", "x".repeat(10000)]) {
    const p = L.prepare(junk);
    assert.equal(typeof p.ok, "boolean");
    if (!p.ok) assert.equal(typeof p.error.col, "number");
  }
  const p = L.prepare("x + y");
  assert.ok(p.ok);
  assert.equal(p.fn({ t: 0, i: 0, x: 2, y: 3, n: 4, u: 0, v: 0, r: 0, a: 0 }), 5);
});
