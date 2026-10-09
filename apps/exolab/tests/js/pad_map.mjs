// Runs the game's real static/game/pad.js in node on fake DualSense states
// read through the real controls.json, then feeds what it returns into the
// real sim (sim.js, level.js, stub.json) to check a press does what the
// pause menu says. Prints "ok N" and exits 0 when every check holds, else
// names each failed one on stderr and exits 1.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const game = new URL("../../static/game/", import.meta.url);
const reg = JSON.parse(readFileSync(new URL("controls.json", game), "utf8"));
const { layoutFor, listPads, choosePad, menuMove, deadzone, createPad, lockMenu, stepPad, rumbleFor, labelsFor, padHelp } =
  await import(
    new URL("pad.js", game)
  );
const { createSim, step, STEP, MODES } = await import(new URL("sim.js", game));
const { testRange } = await import(new URL("level.js", game));
const { Hud } = await import(new URL("hud.js", game));
const stub = JSON.parse(readFileSync(new URL("stub.json", game), "utf8"));

let passed = 0;
const failed = [];
function check(name, fn) {
  try {
    fn();
    passed += 1;
  } catch (err) {
    failed.push(`${name}: ${err.message}`);
  }
}
const near = (a, b, tol = 1e-9) => Math.abs(a - b) <= tol;

const STD = reg.layouts.find((l) => l.id === "standard");
const RAW = reg.layouts.find((l) => l.id === "dualsense_raw");
const CHROME_ID = "DualSense Wireless Controller (STANDARD GAMEPAD Vendor: 054c Product: 0ce6)";

// A fake Gamepad: buttons by PS5 name with a value 0..1 (pressed from 0.1,
// as Chrome reports triggers), sticks as [x, y] with y down positive.
function pad({ held = {}, left = [0, 0], right = [0, 0], mapping = "standard", id = CHROME_ID, axes = null } = {}) {
  const lay = mapping === "standard" ? STD : RAW;
  const n = mapping === "standard" ? 18 : 13;
  const buttons = Array.from({ length: n }, () => ({ pressed: false, value: 0 }));
  for (const [name, v] of Object.entries(held)) {
    const val = v === true ? 1 : v;
    buttons[lay.buttons[name]] = { pressed: val >= 0.1, value: val };
  }
  const ax = axes || new Array(mapping === "standard" ? 4 : 8).fill(0);
  if (!axes) {
    [ax[lay.axes.lx], ax[lay.axes.ly]] = left;
    [ax[lay.axes.rx], ax[lay.axes.ry]] = right;
  }
  return { id, mapping, connected: true, buttons, axes: ax, timestamp: 0 };
}
const DT = 1 / 60;
const run = (st, gp, paused = false, dt = DT) => stepPad(st, gp, reg, dt, paused);
// A let-go long enough to open a locked menu (pad.menu_rest_s and a frame).
// A let-go as the game sees it: frames of DT until the menu stick has been
// seen resting for pad.menu_rest_s (the frame it comes in counts nothing).
const REST_FRAMES = Math.ceil((reg.pad.menu_rest_s ?? 0) / DT) + 1;
const letGo = (st, gp = pad(), paused = true) => {
  for (let i = 0; i < REST_FRAMES; i++) run(st, gp, paused);
};

// --- the registry itself -------------------------------------------------

const KINDS = new Set(["jump", "dash", "crouch", "punch", "use", "repair", "respawn", "pause"]);
check("every binding names a real button and a known action", () => {
  for (const b of reg.bindings) {
    assert.ok(b.button in STD.buttons, `${b.button} not in the standard layout`);
    assert.ok(b.button in reg.names, `${b.button} has no display name`);
    assert.ok(typeof b.does === "string" && b.does.length > 3, `${b.button} has no help text`);
    const [kind, arg] = b.do.split(":");
    if (kind === "mode") assert.ok(MODES.includes(arg), `unknown mode ${arg}`);
    else if (kind === "hold" || kind === "latch") assert.ok(["walk", "sprint"].includes(arg), `unknown held ${arg}`);
    else assert.ok(KINDS.has(kind), `unknown action ${b.do}`);
  }
});
check("each button is bound once and all four modes are reachable", () => {
  const buttons = reg.bindings.map((b) => b.button);
  assert.equal(new Set(buttons).size, buttons.length);
  for (const m of MODES) assert.ok(reg.bindings.some((b) => b.do === `mode:${m}`), m);
  for (const k of ["jump", "dash", "crouch", "punch", "use", "repair", "respawn", "pause", "hold:walk", "latch:sprint"])
    assert.ok(reg.bindings.some((b) => b.do === k), k);
});
check("menu buttons exist in both layouts or come from the hat", () => {
  for (const names of [reg.menu.prev, reg.menu.next, reg.menu.press, reg.menu.back])
    for (const n of names) {
      assert.ok(n in STD.buttons, n);
      assert.ok(n in RAW.buttons || ["up", "down", "left", "right"].includes(n), n);
    }
});

check("game.html has the hooks main.js fills: list, status line, menu buttons", () => {
  const html = readFileSync(new URL("../game.html", game), "utf8");
  assert.match(html, /id="padkeys"/);
  assert.match(html, /id="padline"/);
  const row = html.match(/<div class="buttons">([\s\S]*?)<\/div>/);
  assert.ok(row, "the pause menu's button row");
  assert.match(row[1], /<button id="resume">/, "Play is a button main.js knows by id");
  assert.equal((row[1].match(/<(button|a)\b/g) || []).length, 3, "three menu items");
  const main = readFileSync(new URL("main.js", game), "utf8");
  assert.match(main, /getJSON\("game\/controls\.json"\)/, "main.js loads the registry");
});

// --- layouts and sticks --------------------------------------------------

check("layout: standard, raw DualSense, unknown pads and empty slots", () => {
  assert.equal(layoutFor(pad(), reg).id, "standard");
  assert.equal(layoutFor(pad({ mapping: "", id: "054c-0ce6-DualSense Wireless Controller" }), reg).id, "dualsense_raw");
  assert.equal(layoutFor(pad({ mapping: "", id: "Sony Interactive Entertainment DualSense Wireless Controller" }), reg).id, "dualsense_raw");
  assert.equal(layoutFor(pad({ mapping: "", id: "045e-028e-Some other pad" }), reg), null);
  assert.equal(layoutFor(null, reg), null);
  assert.equal(layoutFor({ ...pad(), connected: false }, reg), null);
});
check("deadzone: rest reads zero, full tilt reads one, NaN is ignored", () => {
  assert.deepEqual(deadzone(0.1, -0.05, 0.15), [0, 0]);
  const [x, y] = deadzone(0, -1, 0.15);
  assert.ok(near(x, 0) && near(y, -1));
  const [a, b] = deadzone(0.6, 0.8, 0.15);
  assert.ok(near(Math.hypot(a, b), 1));
  assert.ok(Math.hypot(...deadzone(0.2, 0, 0.15)) < 0.1, "just past the edge starts small");
  assert.deepEqual(deadzone(NaN, Infinity, 0.15), [0, 0]);
});
check("left stick: up is forward, analog length kept, drift ignored", () => {
  const st = createPad();
  let o = run(st, pad({ left: [0, -1] }));
  assert.ok(near(o.move[0], 0) && near(o.move[1], 1), JSON.stringify(o.move));
  o = run(st, pad({ left: [0.5, 0] }));
  assert.ok(o.move[0] > 0.3 && o.move[0] < 0.5, "half tilt walks right");
  o = run(st, pad({ left: [0.08, 0.1], right: [0.1, 0.05] }));
  assert.deepEqual(o.move, [0, 0]);
  assert.deepEqual(o.look, [0, 0]);
  assert.equal(o.active, false);
});
check("right stick: look speed from the registry, curve, invert", () => {
  const st = createPad();
  let o = run(st, pad({ right: [1, 0] }), false, 0.1);
  assert.ok(near(o.look[0], reg.pad.look_speed[0] * 0.1, 1e-6), String(o.look));
  o = run(st, pad({ right: [0, 1] }), false, 0.1);
  assert.ok(near(o.look[1], reg.pad.look_speed[1] * 0.1, 1e-6), "stick down looks down (positive)");
  o = run(st, pad({ right: [0.5, 0] }), false, 0.1);
  const linear = ((0.5 - reg.pad.deadzone) / (1 - reg.pad.deadzone)) * reg.pad.look_speed[0] * 0.1;
  assert.ok(o.look[0] > 0 && o.look[0] < linear, "half tilt turns slower than linear");
  const inv = { ...reg, pad: { ...reg.pad, invert_y: true } };
  o = stepPad(createPad(), pad({ right: [0, 1] }), inv, 0.1, false);
  assert.ok(o.look[1] < 0, "invert_y flips");
});

// --- buttons -------------------------------------------------------------

check("cross: one jump per press, none while held", () => {
  const st = createPad();
  assert.deepEqual(run(st, pad({ held: { cross: 1 } })).actions, [{ type: "jump" }]);
  assert.deepEqual(run(st, pad({ held: { cross: 1 } })).actions, []);
  assert.deepEqual(run(st, pad()).actions, []);
  assert.deepEqual(run(st, pad({ held: { cross: 1 } })).actions, [{ type: "jump" }]);
});
check("face buttons, bumpers and create do what the registry says", () => {
  const want = { circle: "crouch", square: "use", triangle: "repair", l1: "dash", r1: "punch", create: "respawn" };
  for (const [b, type] of Object.entries(want)) {
    const o = run(createPad(), pad({ held: { [b]: 1 } }));
    assert.deepEqual(o.actions, [{ type }], b);
  }
});
check("R2: a light touch under the threshold does not punch, a pull does", () => {
  const st = createPad();
  assert.deepEqual(run(st, pad({ held: { r2: 0.2 } })).actions, []);
  assert.deepEqual(run(st, pad({ held: { r2: 0.8 } })).actions, [{ type: "punch" }]);
  assert.deepEqual(run(st, pad({ held: { r2: 1 } })).actions, []);
});
check("d-pad picks the four suit modes", () => {
  const want = { up: "armour", right: "strength", down: "speed", left: "cloak" };
  for (const [b, mode] of Object.entries(want))
    assert.deepEqual(run(createPad(), pad({ held: { [b]: 1 } })).actions, [{ type: "mode", mode }], b);
});
check("L2 walks while held", () => {
  const st = createPad();
  assert.equal(run(st, pad({ held: { l2: 0.9 }, left: [0, -1] })).walk, true);
  assert.equal(run(st, pad({ left: [0, -1] })).walk, false);
});
check("L3 sprint stays on until the stick rests a moment or L3 is pressed again mid-run", () => {
  const st = createPad();
  assert.equal(run(st, pad({ held: { l3: 1 }, left: [0, -1] })).sprint, true);
  assert.equal(run(st, pad({ left: [0, -1] })).sprint, true, "released L3, still sprinting");
  assert.equal(run(st, pad({ left: [0.3, -0.9] })).sprint, true);
  assert.equal(run(st, pad()).sprint, false, "not moving: no sprint");
  assert.equal(run(st, pad({ left: [0, 1] })).sprint, true, "a flick through the centre keeps it");
  run(st, pad(), false, reg.pad.latch_rest_s + 0.05);
  assert.equal(run(st, pad({ left: [0, -1] })).sprint, false, "after a rest it does not come back by itself");
  run(st, pad({ held: { l3: 1 }, left: [0, -1] }));
  run(st, pad({ left: [0, -1] }), false, reg.pad.latch_rest_s + 0.05);
  assert.equal(run(st, pad({ held: { l3: 1 }, left: [0, -1] })).sprint, false, "pressed again mid-run stops it");
  assert.equal(run(st, pad({ held: { l3: 1 }, left: [0, -1] }), false, 0.5).sprint, false, "and held, it stays off");
});

// --- pause and the menu --------------------------------------------------

check("options pauses in play and goes back from the menu, no double toggle", () => {
  const st = createPad();
  let o = run(st, pad({ held: { options: 1 } }));
  assert.equal(o.pause, true);
  assert.deepEqual(o.actions, []);
  o = run(st, pad({ held: { options: 1 } }), true);
  assert.deepEqual(o.menu, [], "still held: nothing in the menu");
  run(st, pad(), true);
  o = run(st, pad({ held: { options: 1 } }), true);
  assert.deepEqual(o.menu, ["back"]);
  assert.equal(o.pause, false);
});
check("menu: d-pad moves once, repeats while held, cross presses, circle backs", () => {
  const st = createPad();
  assert.deepEqual(run(st, pad({ held: { down: 1 } }), true).menu, ["next"]);
  let moves = 0;
  for (let i = 0; i < 30; i++) moves += run(st, pad({ held: { down: 1 } }), true, 0.02).menu.length;
  // 0.6 s held: one repeat at 0.38 s, then every 0.14 s -> 0.38, 0.52
  assert.equal(moves, 2);
  assert.deepEqual(run(st, pad({ held: { up: 1 } }), true).menu, ["prev"]);
  run(st, pad(), true);
  assert.deepEqual(run(st, pad({ held: { right: 1 } }), true).menu, ["next"], "d-pad right moves along the row");
  assert.deepEqual(run(st, pad({ held: { left: 1 } }), true).menu, ["prev"]);
  assert.deepEqual(run(st, pad({ held: { cross: 1 } }), true).menu, ["press"]);
  assert.deepEqual(run(st, pad({ held: { circle: 1 } }), true).menu, ["back"]);
});
check("menu: a firm left stick moves, a light one does not", () => {
  assert.deepEqual(run(createPad(), pad({ left: [0, 0.9] }), true).menu, ["next"]);
  assert.deepEqual(run(createPad(), pad({ left: [0, -0.9] }), true).menu, ["prev"]);
  assert.deepEqual(run(createPad(), pad({ left: [0.9, 0] }), true).menu, ["next"]);
  assert.deepEqual(run(createPad(), pad({ left: [0, 0.4] }), true).menu, []);
});
check("the menu gives no game actions, and a cross held into play does not jump", () => {
  const st = createPad();
  const o = run(st, pad({ held: { cross: 1, r2: 1, up: 1 }, left: [0, -1], right: [1, 0] }), true);
  assert.deepEqual(o.actions, []);
  assert.deepEqual(o.move, [0, 0]);
  assert.deepEqual(o.look, [0, 0]);
  assert.deepEqual(run(st, pad({ held: { cross: 1 } })).actions, []);
});
check("unplugging mid-sprint resets; a new pad starts clean", () => {
  const st = createPad();
  run(st, pad({ held: { l3: 1 }, left: [0, -1] }));
  const o = run(st, null);
  assert.equal(o.sprint, false);
  assert.deepEqual(o.move, [0, 0]);
  assert.equal(run(st, pad({ left: [0, -1] })).sprint, false);
});

// --- the raw Linux layout ------------------------------------------------

check("raw hid-playstation layout: face buttons, hat d-pad, sticks on 0 1 3 4", () => {
  const raw = { mapping: "", id: "054c-0ce6-Sony Interactive Entertainment DualSense Wireless Controller" };
  assert.deepEqual(run(createPad(), pad({ ...raw, held: { triangle: 1 } })).actions, [{ type: "repair" }]);
  assert.deepEqual(run(createPad(), pad({ ...raw, held: { square: 1 } })).actions, [{ type: "use" }]);
  const axes = [0, -1, -1, 1, 0, -1, 0, -1];
  const o = run(createPad(), pad({ ...raw, axes }));
  assert.deepEqual(o.actions, [{ type: "mode", mode: "armour" }], "hat up is d-pad up");
  assert.ok(near(o.move[1], 1) && o.look[0] > 0, "left stick forward, right stick right");
});

// --- HUD text and rumble -------------------------------------------------

check("labels and the pause-menu list come from the registry", () => {
  const L = labelsFor(reg);
  assert.equal(L.use, "□");
  assert.equal(L.punch, "R2");
  assert.equal(L.repair, "△");
  assert.equal(L["mode:armour"], "▲");
  const rows = padHelp(reg);
  assert.deepEqual(rows[0], ["Left stick", reg.sticks[0].does]);
  assert.ok(rows.some(([b]) => b === "R2 / R1"), "R2 and R1 share a row");
  assert.equal(rows.length, reg.sticks.length + new Set(reg.bindings.map((b) => b.does)).size);
});
check("rumble: listed events give a dual-rumble effect, others none", () => {
  const fx = rumbleFor(reg, { type: "slam" });
  assert.equal(fx.duration, reg.rumble.slam[0]);
  assert.equal(fx.strongMagnitude, reg.rumble.slam[1]);
  assert.equal(rumbleFor(reg, { type: "lap" }), null);
  assert.equal(rumbleFor(reg, { type: "about" }), null);
  assert.equal(rumbleFor(reg, null), null);
  for (const [k, v] of Object.entries(reg.rumble))
    if (k !== "about") assert.ok(v[0] > 0 && v[1] >= 0 && v[1] <= 1 && v[2] >= 0 && v[2] <= 1, k);
});

// --- into the real sim ---------------------------------------------------

function newGame() {
  const level = testRange();
  const sim = createSim(structuredClone(stub), level);
  const input = { wish: [0, 0], yaw: level.spawn.yaw, pitch: 0, sprint: false, walk: false, actions: [] };
  const st = createPad();
  // Feed one pad frame as main.js does (move along the camera's yaw), then
  // run the sim for `sec`.
  const feed = (gp, sec = STEP) => {
    const o = stepPad(st, gp, reg, STEP, false);
    const fx = Math.sin(input.yaw);
    const fz = Math.cos(input.yaw);
    const [r, f] = o.move;
    input.wish = [fx * f - fz * r, fz * f + fx * r];
    input.sprint = o.sprint;
    input.walk = o.walk;
    input.actions.push(...o.actions);
    for (let t = 0; t < sec; t += STEP) step(sim, input);
    return o;
  };
  feed(pad(), 0.5);
  return { sim, feed };
}
check("in the sim: cross jumps, d-pad up turns Armour on and off", () => {
  const { sim, feed } = newGame();
  assert.ok(sim.player.onGround, "settled on the ground");
  feed(pad({ held: { cross: 1 } }), 0.1);
  assert.ok(!sim.player.onGround && sim.player.vy > 0, `vy ${sim.player.vy}`);
  feed(pad(), 1.5);
  feed(pad({ held: { up: 1 } }));
  assert.equal(sim.player.mode, "armour");
  feed(pad());
  feed(pad({ held: { up: 1 } }));
  assert.equal(sim.player.mode, null);
});
check("in the sim: full stick runs, L3 sprints at the suit's sprint speed", () => {
  const { sim, feed } = newGame();
  feed(pad({ left: [0, -1] }), 1.0);
  const run1 = Math.hypot(sim.player.vx, sim.player.vz);
  feed(pad({ left: [0, -1], held: { l3: 1 } }));
  feed(pad({ left: [0, -1] }), 1.0);
  const sprint = Math.hypot(sim.player.vx, sim.player.vz);
  assert.ok(sim.player.sprinting, "sprinting");
  assert.ok(near(sprint, stub.move.sprint_mps, 0.05), `sprint ${sprint} vs ${stub.move.sprint_mps}`);
  assert.ok(run1 < sprint * 0.8, `run ${run1} slower than sprint ${sprint}`);
});
check("in the sim: a half-tilted stick moves slower than a full one", () => {
  const a = newGame();
  a.feed(pad({ left: [0, -0.5] }), 1.0);
  const b = newGame();
  b.feed(pad({ left: [0, -1] }), 1.0);
  const va = Math.hypot(a.sim.player.vx, a.sim.player.vz);
  const vb = Math.hypot(b.sim.player.vx, b.sim.player.vz);
  assert.ok(va > 0.2 && va < vb * 0.7, `${va} vs ${vb}`);
});

// getGamepads() may throw where the page is not allowed a pad (WebKitGTK has
// this message for an iframe without allow="gamepad", though a probe with no
// pad connected did not hit it); the game must get that as `blocked`.
check("listPads: a refused getGamepads() comes back as blocked, not a throw", () => {
  const nav = {
    getGamepads() {
      const err = new Error(
        "Third-party iframes are not allowed to call getGamepads() unless explicitly allowed via Feature-Policy (gamepad)",
      );
      err.name = "SecurityError";
      throw err;
    },
  };
  const r = listPads(nav);
  assert.deepEqual(r.pads, []);
  assert.match(r.blocked, /Feature-Policy \(gamepad\)/);
});

check("listPads: called on the navigator, empty slots dropped; no API reads as blocked", () => {
  const gp = pad({});
  const nav = {
    getGamepads() {
      assert.equal(this, nav); // a detached call throws "Illegal invocation" in a browser
      return [null, gp, null, null];
    },
  };
  const r = listPads(nav);
  assert.equal(r.blocked, null);
  assert.deepEqual(r.pads, [gp]);
  assert.ok(listPads({}).blocked);
  assert.ok(listPads(undefined).blocked);
});

// --- critic fixes (Relay task 115, 2026-10-08) ------------------------------

check("registry: trigger_release under trigger, latch_rest_s a short pause", () => {
  assert.ok(reg.pad.trigger_release > 0 && reg.pad.trigger_release < reg.pad.trigger);
  assert.ok(reg.pad.latch_rest_s > 0 && reg.pad.latch_rest_s < 1);
});
check("menu: a stick or d-pad still held when the menu opens moves nothing until let go", () => {
  const st = createPad();
  run(st, pad({ left: [0, -1] }));
  assert.equal(run(st, pad({ held: { options: 1 }, left: [0, -1] })).pause, true);
  let moves = [];
  for (let i = 0; i < 40; i++) moves.push(...run(st, pad({ left: [0, -1] }), true, 0.02).menu);
  assert.deepEqual(moves, [], "0.8 s of the stick held from the run");
  letGo(st);
  assert.deepEqual(run(st, pad({ left: [0, -1] }), true).menu, ["prev"], "a fresh push moves");
  const d = createPad();
  run(d, pad({ held: { down: 1 } }));
  run(d, pad({ held: { down: 1, options: 1 } }));
  moves = [];
  for (let i = 0; i < 40; i++) moves.push(...run(d, pad({ held: { down: 1 } }), true, 0.02).menu);
  assert.deepEqual(moves, [], "the d-pad held from play");
  letGo(d);
  assert.deepEqual(run(d, pad({ held: { down: 1 } }), true).menu, ["next"]);
});
check("menuMove: no focus goes to the first item, the ends stop it, no wrap", () => {
  assert.equal(menuMove(-1, "next", 3), 0);
  assert.equal(menuMove(-1, "prev", 3), 0);
  assert.equal(menuMove(0, "prev", 3), 0, "prev from Play stays on Play");
  assert.equal(menuMove(0, "next", 3), 1);
  assert.equal(menuMove(2, "next", 3), 2);
  assert.equal(menuMove(2, "prev", 3), 1);
  assert.equal(menuMove(7, "prev", 3), 0, "an index from a longer menu starts over");
  assert.equal(menuMove(0, "next", 0), -1, "no items");
});
check("R2 resting on the threshold punches once, not every frame", () => {
  const st = createPad();
  let punches = 0;
  for (let i = 0; i < 60; i++)
    punches += run(st, pad({ held: { r2: reg.pad.trigger + (i % 2 ? 0.004 : -0.004) } })).actions.length;
  assert.equal(punches, 1);
  run(st, pad({ held: { r2: reg.pad.trigger_release - 0.05 } }));
  assert.deepEqual(run(st, pad({ held: { r2: 0.8 } })).actions, [{ type: "punch" }], "let go, pulled again");
});
check("L3 clicked just before the stick leaves the deadzone still sprints", () => {
  const st = createPad();
  assert.equal(run(st, pad({ held: { l3: 1 }, left: [0, -0.1] })).sprint, false, "stick still in the deadzone");
  assert.equal(run(st, pad({ held: { l3: 1 }, left: [0, -1] })).sprint, true, "then pushed, L3 still down");
  assert.equal(run(st, pad({ left: [0, -1] })).sprint, true);
});
check("choosePad: the pad in use, not slot 0; switches only to a pad being used", () => {
  const X360 = "Microsoft X-Box 360 pad (STANDARD GAMEPAD Vendor: 28de Product: 11ff)";
  const other = (held = {}) => ({ ...pad({ held, id: X360 }), index: 0 });
  const ds = (held = {}) => ({ ...pad({ held }), index: 1 });
  const st = createPad();
  assert.equal(choosePad([other(), ds({ cross: 1 })], reg, st).index, 1, "the pad being pressed");
  assert.equal(choosePad([other(), ds()], reg, st).index, 1, "stays while both rest");
  assert.equal(choosePad([other({ cross: 1 }), ds({ r2: 1 })], reg, st).index, 1, "both used: keeps it");
  assert.equal(choosePad([other({ cross: 1 }), ds()], reg, st).index, 0, "the other used while this one rests");
  assert.equal(choosePad([ds()], reg, st).index, 1, "unplugged: the one left");
  assert.equal(choosePad([], reg, st), null);
  const fresh = createPad();
  assert.equal(choosePad([null, other(), ds()], reg, fresh).index, 0, "nobody pressing: first known pad");
  assert.equal(choosePad([{ ...pad({ mapping: "", id: "045e-028e-Some other pad", held: { cross: 1 } }), index: 2 }], reg, createPad()), null);
  const drift = { ...pad({ left: [0.3, 0.2], id: X360 }), index: 0 };
  const used = createPad();
  assert.equal(choosePad([drift, ds({ cross: 1 })], reg, used).index, 1);
  assert.equal(choosePad([drift, ds()], reg, used).index, 1, "a stick drifting a little does not steal it");
});
check("a pad that shows up with a button down takes it as a wake-up, not an action", () => {
  const st = createPad();
  run(st, null);
  const o = run(st, pad({ held: { cross: 1 } }));
  assert.deepEqual(o.actions, [], "the waking press does not jump");
  assert.equal(o.active, true, "the HUD still switches to the pad");
  run(st, pad());
  assert.deepEqual(run(st, pad({ held: { cross: 1 } })).actions, [{ type: "jump" }], "the next press does");
  const m = createPad();
  run(m, null, true);
  assert.deepEqual(run(m, pad({ held: { cross: 1, down: 1 } }), true).menu, [], "on the menu: no press, no move");
  assert.deepEqual(run(m, pad({ held: { cross: 1, down: 1 } }), true, 0.6).menu, [], "and no repeat while held");
  run(m, pad(), true);
  assert.deepEqual(run(m, pad({ held: { cross: 1 } }), true).menu, ["press"]);
});

// --- second critic fixes (Relay task 115, 2026-10-09) -----------------------

check("registry: the menu stick lets go under its own line, mouse quiet time, stick roles, analog triggers", () => {
  assert.ok(reg.pad.menu_stick_release > reg.pad.deadzone && reg.pad.menu_stick_release < reg.pad.menu_stick);
  assert.ok(reg.pad.mouse_quiet_s > 0 && reg.pad.mouse_quiet_s <= 5);
  for (const role of ["move", "look"]) assert.equal(reg.sticks.filter((s) => s.do === role).length, 1, role);
  for (const s of reg.sticks) assert.ok(["left", "right"].includes(s.stick), s.stick);
  assert.deepEqual(reg.pad.analog, ["l2", "r2"]);
  for (const n of reg.pad.analog) assert.ok(n in STD.buttons, n);
});
check("menu: a direction held from play stays locked out until let go, whichever way it turns", () => {
  // A: running forward-right, Options, the left thumb keeps steering right
  const st = createPad();
  run(st, pad({ left: [0.5, -0.85] }));
  assert.equal(run(st, pad({ held: { options: 1 }, left: [0.55, -0.8] })).pause, true);
  const moves = [];
  for (const left of [[0.55, -0.8], [0.7, -0.68], [0.85, -0.5], [0.92, -0.3]])
    for (let i = 0; i < 10; i++) moves.push(...run(st, pad({ left }), true, 0.04).menu);
  assert.deepEqual(moves, [], "steering from forward-right to right with the menu open");
  run(st, pad(), true);
  assert.deepEqual(run(st, pad({ held: { cross: 1 } }), true).menu, ["press"], "let go, cross picks");
  // B: strafing right, Options, a d-pad tap, the d-pad let go with the stick still right
  const b = createPad();
  run(b, pad({ left: [1, 0] }));
  run(b, pad({ held: { options: 1 }, left: [1, 0] }));
  const mb = [...run(b, pad({ left: [1, 0] }), true).menu, ...run(b, pad({ held: { up: 1 }, left: [1, 0] }), true).menu];
  for (let i = 0; i < 15; i++) mb.push(...run(b, pad({ left: [1, 0] }), true, 0.04).menu);
  assert.deepEqual(mb, []);
  letGo(b, pad({ left: [0.2, 0] }));
  assert.deepEqual(run(b, pad({ left: [1, 0] }), true).menu, ["next"], "let go and pushed again: it moves");
});
check("menu: a stick hovering on the line moves once, not on every wobble", () => {
  const st = createPad();
  const moves = [];
  for (let i = 0; i < 30; i++)
    moves.push(...run(st, pad({ left: [0, reg.pad.menu_stick + (i % 2 ? 0.02 : -0.02)] }), true, 0.01).menu);
  assert.deepEqual(moves, ["next"]);
  run(st, pad({ left: [0, reg.pad.menu_stick_release - 0.05] }), true);
  assert.deepEqual(run(st, pad({ left: [0, 0.9] }), true).menu, ["next"], "back under the release line, then pushed: moves");
});
check("main.js can lock the menu (window focus lost): a held direction waits for a let-go", () => {
  const st = createPad();
  assert.deepEqual(run(st, pad({ held: { down: 1 } }), true).menu, ["next"]);
  lockMenu(st);
  let moves = [];
  for (let i = 0; i < 50; i++) moves.push(...run(st, pad({ held: { down: 1 } }), true, 0.02).menu);
  assert.deepEqual(moves, [], "a frozen d-pad does not repeat");
  letGo(st);
  assert.deepEqual(run(st, pad({ held: { down: 1 } }), true).menu, ["next"]);
});
check("active (what switches the HUD and the mouse guard to the pad): a button or a firm stick, not drift", () => {
  assert.equal(run(createPad(), pad({ left: [0.17, 0] })).active, false, "a stick resting at 0.17");
  assert.equal(run(createPad(), pad({ right: [0, 0.4] })).active, false);
  assert.equal(run(createPad(), pad({ left: [0, -0.9] })).active, true);
  assert.equal(run(createPad(), pad({ right: [0.8, 0] })).active, true);
  assert.equal(run(createPad(), pad({ held: { square: 1 } })).active, true);
  assert.equal(run(createPad(), pad({ held: { r2: 0.2 } })).active, false, "a trigger under its line");
});
check("L3 after a short stop turns sprint on; it does not toggle it off", () => {
  const st = createPad();
  run(st, pad({ held: { l3: 1 }, left: [0, -1] }));
  run(st, pad({ left: [0, -1] }), false, 1.0);
  assert.equal(run(st, pad({ left: [0, -1] })).sprint, true, "sprinting");
  run(st, pad(), false, reg.pad.latch_rest_s * 0.6);
  assert.equal(run(st, pad({ held: { l3: 1 }, left: [0, -1] })).sprint, true, "a stop under latch_rest_s, then push + L3");
  assert.equal(run(st, pad({ left: [0, -1] }), false, 0.5).sprint, true, "still on 0.5 s later");
  const late = createPad();
  run(late, pad(), false, 1);
  assert.equal(run(late, pad({ held: { l3: 1 }, left: [0, -1] })).sprint, true, "from a stand, push + L3");
});
check("registry edits: latch_rest_s 0 or missing still sprints; a release line above the press line does not flap", () => {
  const noRest = { ...reg.pad };
  delete noRest.latch_rest_s;
  for (const p of [{ ...reg.pad, latch_rest_s: 0 }, noRest]) {
    const r = { ...reg, pad: p };
    const st = createPad();
    const name = `latch_rest_s ${p.latch_rest_s}`;
    assert.equal(stepPad(st, pad({ held: { l3: 1 }, left: [0, -1] }), r, DT, false).sprint, true, `${name}: the press frame`);
    assert.equal(stepPad(st, pad({ left: [0, -1] }), r, DT, false).sprint, true, `${name}: the next frame`);
    stepPad(st, pad(), r, DT, false);
    assert.equal(stepPad(st, pad({ left: [0, -1] }), r, DT, false).sprint, false, `${name}: a stop ends it`);
  }
  const r = { ...reg, pad: { ...reg.pad, trigger: 0.3, trigger_release: 0.4 } };
  const st = createPad();
  let punches = 0;
  for (let i = 0; i < 60; i++) punches += stepPad(st, pad({ held: { r2: 0.35 } }), r, DT, false).actions.length;
  assert.equal(punches, 1, "R2 held still at 0.35");
});
check("sticks: which one moves and which looks comes from the registry", () => {
  const sticks = [
    { stick: "left", do: "look", does: "look" },
    { stick: "right", do: "move", does: "move" },
  ];
  const swapped = { ...reg, sticks };
  const o = stepPad(createPad(), pad({ left: [0, -1] }), swapped, 0.1, false);
  assert.deepEqual(o.move, [0, 0]);
  assert.ok(o.look[1] < 0, "the left stick looks up");
  assert.ok(near(stepPad(createPad(), pad({ right: [0, -1] }), swapped, DT, false).move[1], 1), "the right stick runs");
  assert.deepEqual(padHelp(swapped).slice(0, 2), [["Left stick", "look"], ["Right stick", "move"]]);
  const digital = { ...reg, pad: { ...reg.pad, analog: [] } };
  const a = stepPad(createPad(), pad({ held: { r2: 0.2 } }), digital, DT, false).actions;
  assert.deepEqual(a, [{ type: "punch" }], "a trigger not listed as analog is a plain button");
});

check("a sim message names the repair key or button for the device in use", () => {
  const fill = (labels, text) => Hud.prototype.fill.call({ labels }, text);
  assert.equal(fill({ repair: "R" }, "Arms broken: press {repair} to repair"), "Arms broken: press R to repair");
  assert.equal(fill(labelsFor(reg), "Arms broken: press {repair} to repair"), "Arms broken: press △ to repair");
  assert.equal(fill({ repair: "<b>" }, "{repair} {nothing}"), "&#60;b&#62; {nothing}");
  const sim = readFileSync(new URL("sim.js", game), "utf8");
  assert.doesNotMatch(sim, /press R\b|\bR repairs/, "no keyboard key written into a sim message");
  assert.match(sim, /\{repair\}/);
});

// --- third critic fixes (Relay task 115, 2026-10-09) ------------------------

check("registry: a locked menu opens after a short rest, not on one frame", () => {
  assert.ok(reg.pad.menu_rest_s >= 0.05 && reg.pad.menu_rest_s <= 0.3, String(reg.pad.menu_rest_s));
});
check("menu: a dodge swinging through the centre after Options stays locked; a real let-go opens it (H3)", () => {
  const st = createPad();
  run(st, pad({ left: [-1, 0] }));
  assert.equal(run(st, pad({ held: { options: 1 }, left: [-1, 0] })).pause, true);
  const moves = [];
  for (const left of [[-0.5, 0], [-0.1, 0], [0.2, 0], [0.7, 0]]) moves.push(...run(st, pad({ left }), true).menu);
  for (let i = 0; i < 30; i++) moves.push(...run(st, pad({ left: [1, 0] }), true).menu);
  assert.deepEqual(moves, [], "the swing through the centre is not a let-go");
  for (let i = 0; i < 3; i++) run(st, pad(), true);
  assert.deepEqual(run(st, pad({ left: [1, 0] }), true).menu, [], "let go for 50 ms, pushed: still locked");
  letGo(st);
  assert.deepEqual(run(st, pad({ left: [1, 0] }), true).menu, ["next"], "let go for menu_rest_s, pushed: it moves");
  lockMenu(st);
  run(st, pad(), true);
  assert.equal(st.menuLock, true, "locked again after a push: one frame of rest is not enough");
});
check("menu: Options pressed as the stick swings through the centre stays locked too (H3)", () => {
  const st = createPad();
  run(st, pad({ left: [-1, 0] }));
  assert.equal(run(st, pad({ held: { options: 1 }, left: [0.1, 0] })).pause, true);
  const moves = [];
  for (let i = 0; i < 30; i++) moves.push(...run(st, pad({ left: [1, 0] }), true).menu);
  assert.deepEqual(moves, []);
});
check("menu: a d-pad let go is a let-go: a quick second tap after the waking press moves (H3)", () => {
  const st = createPad();
  run(st, null, true);
  assert.deepEqual(run(st, pad({ held: { down: 1 } }), true).menu, [], "the waking press");
  for (let i = 0; i < 3; i++) run(st, pad(), true);
  assert.deepEqual(run(st, pad({ held: { down: 1 } }), true).menu, ["next"], "let go 50 ms, pressed again");
});
check("menu: a d-pad held from play with the stick at rest opens on its let-go (H3)", () => {
  const st = createPad();
  letGo(st, pad(), false);
  run(st, pad({ held: { down: 1 } }));
  assert.equal(run(st, pad({ held: { down: 1, options: 1 } })).pause, true);
  assert.deepEqual(run(st, pad({ held: { down: 1 } }), true).menu, [], "still held: locked");
  run(st, pad(), true);
  assert.deepEqual(run(st, pad({ held: { down: 1 } }), true).menu, ["next"], "one frame let go, pressed: it moves");
});
check("registry edit: menu_rest_s 0 or missing, a stick held from play still moves nothing", () => {
  const { menu_rest_s, ...noRest } = reg.pad;
  for (const p of [{ ...reg.pad, menu_rest_s: 0 }, noRest]) {
    const r = { ...reg, pad: p };
    const st = createPad();
    stepPad(st, pad({ left: [1, 0] }), r, DT, false);
    stepPad(st, pad({ held: { options: 1 }, left: [1, 0] }), r, DT, false);
    const moves = [];
    for (let i = 0; i < 30; i++) moves.push(...stepPad(st, pad({ left: [1, 0] }), r, DT, true).menu);
    assert.deepEqual(moves, [], `menu_rest_s ${p.menu_rest_s}`);
    stepPad(st, pad(), r, DT, true);
    assert.deepEqual(stepPad(st, pad({ left: [1, 0] }), r, DT, true).menu, ["next"], `menu_rest_s ${p.menu_rest_s}`);
  }
});
check("choosePad: the pad being read going away is told once, also when another pad is left (H2)", () => {
  const X360 = "Microsoft X-Box 360 pad (STANDARD GAMEPAD Vendor: 28de Product: 11ff)";
  const idle = { ...pad({ id: X360 }), index: 0 };
  const ds = (held = {}) => ({ ...pad({ held }), index: 1 });
  const st = createPad();
  assert.equal(choosePad([idle, ds({ cross: 1 })], reg, st).index, 1);
  assert.equal(st.padLost, false);
  assert.equal(choosePad([idle, null], reg, st).index, 0, "the idle pad is read now");
  assert.equal(st.padLost, true, "but the pad in use went away");
  choosePad([idle, null], reg, st);
  assert.equal(st.padLost, false, "told once");
  const off = createPad();
  choosePad([idle, ds({ cross: 1 })], reg, off);
  choosePad([idle, { ...ds(), connected: false }], reg, off);
  assert.equal(off.padLost, true, "a pad reported as not connected is gone too");
  const one = createPad();
  choosePad([ds()], reg, one);
  assert.equal(choosePad([], reg, one), null);
  assert.equal(one.padLost, true, "the last pad going counts too");
  const swap = createPad();
  assert.equal(choosePad([idle, ds()], reg, swap).index, 0);
  assert.equal(choosePad([idle, ds({ cross: 1 })], reg, swap).index, 1);
  assert.equal(swap.padLost, false, "switching to a pad being used is not a loss");
  const none = createPad();
  choosePad([], reg, none);
  assert.equal(none.padLost, false, "no pad yet is not a loss");
});
check("menu: a long frame as the stick comes into the centre counts no rest (I3)", () => {
  const st = createPad();
  run(st, pad({ left: [-1, 0] }));
  assert.equal(run(st, pad({ held: { options: 1 }, left: [-1, 0] })).pause, true);
  // The first frame on the menu is a long one (the overlay's first paint),
  // and the stick is already swinging through the centre.
  const moves = [...run(st, pad({ left: [-0.3, 0] }), true, 0.1).menu];
  for (const left of [[-0.1, 0], [0.1, 0]]) moves.push(...run(st, pad({ left }), true).menu);
  for (let i = 0; i < 15; i++) moves.push(...run(st, pad({ left: [1, 0] }), true).menu);
  assert.deepEqual(moves, [], "two frames of the swing after a 0.1 s frame are not a rest");
  letGo(st);
  assert.deepEqual(run(st, pad({ left: [1, 0] }), true).menu, ["next"], "a real let-go opens it");
});
check("menu: Options mid-walk under the let-go line, the thumb running on after it: nothing moves (I4)", () => {
  const st = createPad();
  for (let i = 0; i < 30; i++) run(st, pad({ left: [0, -0.35] }));
  assert.equal(run(st, pad({ held: { options: 1 }, left: [0, -0.35] })).pause, true);
  const moves = [...run(st, pad({ left: [0, -0.35] }), true).menu];
  for (let i = 0; i < 6; i++) moves.push(...run(st, pad({ left: [0, -0.8] }), true).menu);
  assert.deepEqual(moves, [], "a gentle walk is not a rest: Play stays");
  letGo(st);
  assert.deepEqual(run(st, pad({ left: [0, -0.8] }), true).menu, ["prev"], "let go, then pushed: it moves");
});
check("menu: a stick drifting past the deadzone holds the menu only until it has sat still (I4)", () => {
  const st = createPad();
  const drift = { left: [0.17, 0] };
  for (let i = 0; i < 30; i++) run(st, pad(drift));
  run(st, pad({ ...drift, held: { options: 1 } }));
  assert.equal(st.menuLock, true, "it moves the soldier, so Options locks the menu");
  letGo(st, pad(drift));
  assert.deepEqual(run(st, pad({ ...drift, held: { down: 1 } }), true).menu, ["next"], "then the d-pad works");
});
check("main.js locks the menu again when the window gets focus back: the rest seen before does not count (I5)", () => {
  const st = createPad();
  letGo(st);
  lockMenu(st, true);
  for (let i = 0; i < 3; i++) run(st, pad(), true);
  assert.deepEqual(run(st, pad({ left: [0, 1] }), true).menu, [], "50 ms at rest after the return is not enough");
  letGo(st);
  assert.deepEqual(run(st, pad({ left: [0, 1] }), true).menu, ["next"]);
  const away = createPad();
  letGo(away);
  lockMenu(away);
  run(away, pad(), true);
  assert.equal(away.menuLock, false, "a plain lock (wake, focus lost) counts the rest already seen");
});

if (failed.length) {
  for (const f of failed) console.error(`FAIL ${f}`);
  console.error(`${passed} passed, ${failed.length} failed`);
  process.exit(1);
}
console.log(`ok ${passed}`);
