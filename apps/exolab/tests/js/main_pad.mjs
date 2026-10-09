// Runs the game's real static/game/main.js pad wiring (pollPad, menuKey,
// padToHub, padLine and the listeners bindInput and bindPad add) in a node
// vm with a fake window, document, canvas and clock, on the real pad.js and
// controls.json. Its imports are swapped for those and for inert stubs
// (three.js, the sim, the view, the HUD) and boot() is not run. Prints
// "ok N" and exits 0 when every check holds, else names each failed one on
// stderr and exits 1. The harness was first written by the second critic of
// Relay task 115 (2026-10-08).

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const game = new URL("../../static/game/", import.meta.url);
const reg = JSON.parse(readFileSync(new URL("controls.json", game), "utf8"));
const padjs = await import(new URL("pad.js", game));
const MAIN = readFileSync(new URL("main.js", game), "utf8");
const STD = reg.layouts.find((l) => l.id === "standard");
const DS_ID = "DualSense Wireless Controller (STANDARD GAMEPAD Vendor: 054c Product: 0ce6)";
const X360 = "Microsoft X-Box 360 pad (STANDARD GAMEPAD Vendor: 28de Product: 11ff)";
// A let-go long enough to open a locked menu (pad.menu_rest_s and a frame).
// Frames of 1/60 s until the menu stick has been seen resting for
// pad.menu_rest_s (the frame it comes in counts nothing).
const REST_FRAMES = Math.ceil((reg.pad.menu_rest_s ?? 0) * 60) + 1;

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

// A fake standard-mapping Gamepad: buttons by PS5 name (value 0..1), sticks
// as [x, y] with y down positive.
function pad({ held = {}, left = [0, 0], right = [0, 0], index = 0 } = {}) {
  const buttons = Array.from({ length: 18 }, () => ({ pressed: false, value: 0 }));
  for (const [name, v] of Object.entries(held)) {
    const val = v === true ? 1 : v;
    buttons[STD.buttons[name]] = { pressed: val >= 0.1, value: val };
  }
  return { id: DS_ID, mapping: "standard", index, connected: true, buttons, axes: [...left, ...right], timestamp: 0 };
}

// main.js loaded into a fresh vm. topLevel: the page is its own window.parent
// (a pop-out or a plain tab) instead of sitting in the hub's frame.
function loadMain({ topLevel = false } = {}) {
  let src = MAIN.split("\n")
    .filter((l) => !/^import /.test(l))
    .join("\n");
  const cut = src.indexOf("\nboot().catch(");
  if (cut < 0) throw new Error("boot() call not found in main.js");
  src = src.slice(0, cut);
  src += `
globalThis.__T = {
  pollPad, padLine, setPaused, readKeys, bindInput, bindPad, padState, input, cam,
  get paused() { return paused; }, get device() { return device; }, get menuIdx() { return menuIdx; },
  setControls(v) { controls = v; }, setHud(v) { hud = v; },
};`;

  const log = [];
  let pads = [];
  const clock = { t: 0 };
  const on = (tbl) => (t, f) => (tbl[t] ||= []).push(f);
  const fire = (tbl) => (t, e = {}) => {
    for (const f of tbl[t] || []) f(e);
  };
  const doc = {
    activeElement: null,
    pointerLockElement: null,
    body: null,
    addEventListener() {},
    exitPointerLock() {
      doc.pointerLockElement = null;
    },
  };
  class El {
    constructor(id, inPause = false) {
      this.id = id;
      this.inPause = inPause;
      this.hidden = false;
      this.textContent = "";
      this.innerHTML = "";
      this.l = {};
      this.classList = { toggle() {} };
    }
    addEventListener(t, f) {
      (this.l[t] ||= []).push(f);
    }
    fire(t, e = {}) {
      for (const f of this.l[t] || []) f(e);
    }
    focus() {
      doc.activeElement = this;
    }
    blur() {
      if (doc.activeElement === this) doc.activeElement = doc.body;
    }
    click() {
      log.push(`CLICK ${this.id}`);
      this.fire("click", {});
    }
    closest(sel) {
      return sel === "#pause" && this.inPause ? els["#pause"] : null;
    }
  }
  doc.body = new El("body");
  const items = [new El("resume", true), new El("restart", true), new El("back", true)];
  const els = { "#resume": items[0] };
  for (const id of ["pause", "padline", "padkeys", "notes", "fps", "loading"]) els[`#${id}`] = new El(id);
  doc.querySelector = (s) => els[s] || null;
  doc.querySelectorAll = (s) => (s === "#pause .buttons > *" ? items : []);

  const listeners = {};
  const win = {
    addEventListener: on(listeners),
    fire: fire(listeners),
    postMessage: (data) => log.push(`self ${JSON.stringify(data)}`),
  };
  const hub = { postMessage: (data) => log.push(`parent ${JSON.stringify(data)}`) };
  win.parent = topLevel ? win : hub;
  const canvas = new El("canvas");
  canvas.requestPointerLock = () => {
    log.push("requestPointerLock");
    doc.pointerLockElement = canvas;
  };

  const ctx = {
    console,
    URLSearchParams,
    performance: { now: () => clock.t },
    location: { search: "" },
    window: win,
    document: doc,
    navigator: { getGamepads: () => pads },
    THREE: { Vector3: class {} },
    ...padjs,
    STEP: 1 / 120,
  };
  for (const k of ["createSim", "step", "testRange", "rayBoxes", "loadCharacter", "runDemo", "fetch"]) ctx[k] = () => {};
  ctx.View = ctx.Hud = class {};
  vm.createContext(ctx);
  vm.runInContext(src, ctx, { filename: "main.js" });
  const T = ctx.__T;
  T.setControls(reg);
  T.setHud({ setLabels() {} });
  T.bindInput(canvas);
  T.bindPad({ messages: [], t: 0 });
  return {
    T,
    log,
    win,
    hub,
    doc,
    canvas,
    items,
    els,
    clock,
    setPads(p) {
      pads = p;
    },
    // One frame of main.js's frame(): pollPad and, in play, readKeys and the
    // actions the sim would take (drained here). dt in seconds; the clock
    // moves with it.
    frame(dt = 1 / 60) {
      clock.t += dt * 1000;
      T.pollPad(dt);
      let actions = [];
      if (!T.paused) {
        T.readKeys();
        // Copied out of the vm: its arrays have their own Array.prototype,
        // so a strict deepEqual with [] would never hold.
        actions = JSON.parse(JSON.stringify(T.input.actions.splice(0)));
      }
      return { paused: T.paused, menuIdx: T.menuIdx, actions, sprint: T.input.sprint };
    },
    // A let-go: REST_FRAMES frames of the pads as they are now.
    rest() {
      for (let i = 0; i < REST_FRAMES; i++) this.frame();
    },
    // The pad in play: seen at rest once (its wake-up frame), then `held`.
    play(held = {}) {
      T.setPaused(false);
      pads = [pad()];
      this.frame();
      pads = [pad({ held })];
      return this.frame();
    },
    // A click as the browser sends it through #pause (capture listeners
    // first): whether anything stopped it.
    pauseClick(trusted, detail = 1) {
      const e = { isTrusted: trusted, detail, stopped: false, prevented: false };
      e.stopPropagation = () => (e.stopped = true);
      e.preventDefault = () => (e.prevented = true);
      els["#pause"].fire("click", e);
      return e;
    },
  };
}
const claims = (g) => g.log.filter((l) => l.includes('"forge":"pad"')).map((l) => l.replace(/"forge":"pad",/, ""));
const punches = (f) => f.actions.filter((a) => a.type === "punch").length;

check("Forge hears 'I read the pad' only while a pad is seen; at the top level it goes to the page itself", () => {
  const g = loadMain();
  g.frame();
  g.setPads([pad()]);
  g.frame();
  g.frame();
  g.setPads([]);
  g.frame();
  assert.deepEqual(claims(g), ['parent {"native":true}', 'parent {"native":false}']);
  const top = loadMain({ topLevel: true });
  top.setPads([pad()]);
  top.frame();
  assert.deepEqual(claims(top), ['self {"native":true}']);
});

check("keyboard and mouse with no pad: clicks punch and take the pointer", () => {
  const g = loadMain();
  g.T.setPaused(false);
  let n = 0;
  for (let i = 0; i < 3; i++) {
    g.canvas.fire("mousedown", { button: 0 });
    n += punches(g.frame());
  }
  assert.equal(n, 3);
  assert.ok(g.log.includes("requestPointerLock"));
});

check("a pad lying by with a drifting stick does not take the mouse away (G2)", () => {
  const g = loadMain();
  g.T.setPaused(false);
  g.setPads([pad({ left: [0.17, 0] })]);
  for (let i = 0; i < 5; i++) g.frame();
  let n = 0;
  for (let i = 0; i < 5; i++) {
    g.canvas.fire("mousedown", { button: 0 });
    n += punches(g.frame());
  }
  assert.equal(n, 5, "every click punches");
  assert.ok(g.log.includes("requestPointerLock"));
  assert.equal(g.T.device, "keys");
});

check("touchpad taps and brushes during pad play do nothing; after mouse_quiet_s one click hands back (G3)", () => {
  const g = loadMain();
  g.play({ r2: 1 });
  assert.equal(g.T.device, "pad");
  g.setPads([pad()]);
  g.clock.t += 500;
  g.canvas.fire("mousedown", { button: 0 });
  g.clock.t += 500;
  g.canvas.fire("mousedown", { button: 0 });
  g.doc.pointerLockElement = g.canvas; // still locked from earlier mouse play
  const yaw = g.T.cam.yaw;
  g.win.fire("mousemove", { movementX: 200, movementY: 0, buttons: 0 });
  assert.equal(g.T.cam.yaw, yaw, "a brush does not turn the camera");
  assert.deepEqual(g.frame().actions, [], "two taps: no punch");
  assert.ok(!g.log.includes("requestPointerLock"), "and no pointer grab");
  g.clock.t += reg.pad.mouse_quiet_s * 1000;
  g.frame();
  g.canvas.fire("mousedown", { button: 0 });
  assert.deepEqual(g.frame().actions, [], "the first click after pad play only hands back");
  assert.equal(g.T.device, "keys");
  g.win.fire("mousemove", { movementX: 200, movementY: 0, buttons: 0 });
  assert.notEqual(g.T.cam.yaw, yaw, "then the mouse turns the camera");
  g.canvas.fire("mousedown", { button: 0 });
  assert.equal(punches(g.frame()), 1, "and punches");
});

check("a touchpad tap on the pause menu clicks nothing while the pad is in use (G3)", () => {
  const g = loadMain();
  g.play({ options: 1 });
  assert.equal(g.T.paused, true);
  assert.equal(g.pauseClick(true).stopped, true, "a real click right after pad use");
  assert.equal(g.pauseClick(false).stopped, false, "the pad's own el.click() goes through");
  g.setPads([pad()]);
  g.clock.t += reg.pad.mouse_quiet_s * 1000 + 50;
  g.frame();
  assert.equal(g.pauseClick(true).stopped, false, "a mouse click later goes through");
});

check("Forge's window losing focus pauses pad play; a frozen stick moves nothing (G5)", () => {
  const g = loadMain();
  g.play({ r2: 1 });
  g.setPads([pad({ left: [0, -1] })]);
  g.frame();
  g.win.fire("message", { source: {}, data: { forge: "focus", focused: false } });
  assert.equal(g.T.paused, false, "a message from anything but the hub is ignored");
  g.win.fire("message", { source: g.hub, data: { forge: "focus", focused: true } });
  assert.equal(g.T.paused, false);
  g.win.fire("message", { source: g.hub, data: { forge: "focus", focused: false } });
  assert.equal(g.T.paused, true, "the hub says the window lost focus");
  for (let i = 0; i < 60; i++) g.frame();
  assert.equal(g.T.menuIdx, -1, "1 s of the frozen stick: the menu did not move");
  g.setPads([pad()]);
  g.rest();
  g.setPads([pad({ held: { down: 1 } })]);
  assert.equal(g.frame().menuIdx, 0, "let go and pushed: it moves");
});

check("the window's own blur with a d-pad held on the menu: no repeats walk it to Back (G5)", () => {
  const g = loadMain();
  g.play({ options: 1 });
  g.setPads([pad()]);
  g.frame();
  g.setPads([pad({ held: { down: 1 } })]);
  assert.equal(g.frame().menuIdx, 1, "on Restart");
  g.win.fire("blur");
  for (let i = 0; i < 60; i++) g.frame();
  assert.equal(g.T.menuIdx, 1, "1 s of the frozen d-pad: still on Restart");
  g.setPads([pad()]);
  g.rest();
  g.setPads([pad({ held: { up: 1 } })]);
  assert.equal(g.frame().menuIdx, 0, "back in focus, the d-pad moves again");
});

check("steering right as Options opens the menu leaves Play in focus; let go and Cross plays on (G1)", () => {
  const g = loadMain();
  g.play();
  g.setPads([pad({ left: [0.5, -0.85] })]);
  g.frame();
  g.setPads([pad({ held: { options: 1 }, left: [0.55, -0.8] })]);
  assert.equal(g.frame().paused, true);
  for (const left of [[0.55, -0.8], [0.7, -0.68], [0.85, -0.5], [0.92, -0.3]]) {
    g.setPads([pad({ left })]);
    for (let i = 0; i < 12; i++) g.frame(0.04);
  }
  assert.equal(g.T.menuIdx, 0, "Play");
  g.setPads([pad()]);
  g.frame();
  g.setPads([pad({ held: { cross: 1 } })]);
  assert.equal(g.frame().paused, false);
  assert.ok(!g.log.some((l) => l.startsWith("CLICK")), "nothing clicked");
});

check("a pad that drops out mid pad-play pauses the game; a keyboard player is not paused by it (G9)", () => {
  const g = loadMain();
  g.play({ l3: 1 });
  g.setPads([pad({ left: [0, -1] })]);
  assert.equal(g.frame().sprint, true);
  g.setPads([]);
  assert.equal(g.frame().paused, true);
  const k = loadMain();
  k.T.setPaused(false);
  k.setPads([pad()]);
  k.frame();
  k.win.fire("keydown", { code: "KeyW", repeat: false, preventDefault() {} });
  k.frame();
  k.setPads([]);
  assert.equal(k.frame().paused, false);
});

check("an error in the page hands the pad back to Forge; a live frame loop claims it again (G10)", () => {
  const g = loadMain();
  g.setPads([pad()]);
  g.frame();
  g.win.fire("error", {});
  g.frame();
  assert.deepEqual(claims(g), ['parent {"native":true}', 'parent {"native":false}', 'parent {"native":true}']);
});

check("with no pad seen yet the pause menu says to wake it with a d-pad arrow (G8)", () => {
  const g = loadMain();
  g.T.padLine();
  assert.match(g.els["#padline"].textContent, /d-pad arrow/);
  g.setPads([pad()]);
  g.T.padLine();
  assert.match(g.els["#padline"].textContent, /^Controller: DualSense/);
});

// --- third critic fixes (Relay task 115, 2026-10-09) ------------------------

check("gentle stick play: touchpad brushes do not turn the camera, a tap only hands back (H1, I1)", () => {
  const g = loadMain();
  g.play({ r2: 1 });
  g.setPads([pad({ left: [0, -0.4], right: [0.3, 0] })]);
  for (let i = 0; i < 180; i++) g.frame();
  assert.equal(g.T.device, "pad");
  g.doc.pointerLockElement = g.canvas; // still locked from earlier mouse play
  const yaw = g.T.cam.yaw;
  g.win.fire("mousemove", { movementX: 200, movementY: 0, buttons: 0 });
  assert.equal(g.T.cam.yaw, yaw, "3 s of walking and aiming at half tilt: a brush does not turn the camera");
  g.canvas.fire("mousedown", { button: 0 });
  assert.equal(punches(g.frame()), 0, "a tap: no punch");
  assert.ok(!g.log.includes("requestPointerLock"), "no pointer grab");
  assert.equal(g.T.device, "keys", "it hands the controls back to the mouse");
  const k = loadMain();
  k.play({ r2: 1 });
  k.win.fire("keydown", { code: "KeyW", repeat: false, preventDefault() {} });
  k.win.fire("keyup", { code: "KeyW" });
  k.setPads([pad({ left: [0.2, 0] })]);
  for (let i = 0; i < 150; i++) k.frame();
  k.canvas.fire("mousedown", { button: 0 });
  assert.equal(punches(k.frame()), 1, "a keyboard player's drifting pad does not keep the mouse quiet");
});

check("focus lost while the pad's stick moves the soldier pauses, even after a key press (H1)", () => {
  const g = loadMain();
  g.play({ r2: 1 });
  g.win.fire("keydown", { code: "KeyW", repeat: false, preventDefault() {} });
  g.win.fire("keyup", { code: "KeyW" });
  assert.equal(g.T.device, "keys");
  g.setPads([pad({ left: [0, -0.5] })]);
  g.frame();
  g.win.fire("message", { source: g.hub, data: { forge: "focus", focused: false } });
  assert.equal(g.T.paused, true, "the frozen stick would walk on");
});

check("the pad in use dropping out pauses even with a second pad connected (H2)", () => {
  const g = loadMain();
  const idle = { ...pad(), id: X360, index: 0 };
  g.T.setPaused(false);
  g.setPads([idle, pad({ index: 1 })]);
  g.frame();
  g.setPads([idle, pad({ index: 1, held: { r2: 1 } })]);
  g.frame();
  g.setPads([idle, pad({ index: 1, left: [0, -1] })]);
  assert.equal(g.frame().paused, false);
  assert.equal(g.T.device, "pad");
  g.setPads([idle, null]);
  assert.equal(g.frame().paused, true, "slot 1 went, slot 0 still idle");
  g.T.setPaused(false);
  assert.equal(g.frame().paused, false, "resumed: the pad left plays on, no second pause");
});

check("the browser's disconnect event coming before the next frame does not hide the loss (H2)", () => {
  const g = loadMain();
  const idle = { ...pad(), id: X360, index: 0 };
  g.T.setPaused(false);
  g.setPads([idle, pad({ index: 1 })]);
  g.frame();
  g.setPads([idle, pad({ index: 1, held: { r2: 1 } })]);
  g.frame();
  g.setPads([idle, pad({ index: 1, left: [0, -1] })]);
  assert.equal(g.frame().paused, false);
  g.setPads([idle, null]);
  g.win.fire("gamepaddisconnected", { gamepad: pad({ index: 1 }) });
  assert.equal(g.frame().paused, true, "the event's menu line did not eat the loss");
});

// The vm above gets every pad.js export whatever main.js imports, so a name
// main.js imports and a module does not export (a SyntaxError that stops the
// whole game in a browser) is checked here, on the source.
check("every name main.js imports from the game's own modules is exported there", () => {
  const missing = [];
  const files = [];
  for (const [, names, file] of MAIN.matchAll(/^import \{([^}]*)\} from "\.\/([\w.]+)";$/gm)) {
    files.push(file);
    const src = readFileSync(new URL(file, game), "utf8");
    const listed = [...src.matchAll(/^export \{([^}]*)\}/gm)].flatMap((m) => m[1].split(",").map((n) => n.trim()));
    for (const name of names.split(",").map((n) => n.trim())) {
      const declared = new RegExp(`^export (async )?(function\\*?|const|let|class) ${name}\\b`, "m").test(src);
      if (!declared && !listed.includes(name)) missing.push(`${name} from ${file}`);
    }
  }
  assert.deepEqual(missing, []);
  assert.ok(files.includes("pad.js") && files.length >= 5, `import lines read: ${files}`);
});

check("Enter on the pause menu right after pad use still clicks; a real mouse click is held back", () => {
  const g = loadMain();
  g.play({ options: 1 });
  assert.equal(g.pauseClick(true, 0).stopped, false, "a click the keyboard made (detail 0) goes through");
  assert.equal(g.pauseClick(true, 1).stopped, true, "a real click within mouse_quiet_s does not");
});
check("a stick drifting past the deadzone after pad play: one click hands back, then the mouse works (I1)", () => {
  const g = loadMain();
  g.play({ r2: 1 });
  g.setPads([pad({ left: [0.17, 0] })]);
  for (let i = 0; i < 600; i++) g.frame();
  g.canvas.fire("mousedown", { button: 0 });
  assert.equal(punches(g.frame()), 0, "10 s on: the first click only hands back");
  assert.equal(g.T.device, "keys");
  g.canvas.fire("mousedown", { button: 0 });
  assert.equal(punches(g.frame()), 1, "the next one punches");
  assert.ok(g.log.includes("requestPointerLock"), "and takes the pointer");
  const yaw = g.T.cam.yaw;
  g.win.fire("mousemove", { movementX: 200, movementY: 0, buttons: 0 });
  assert.notEqual(g.T.cam.yaw, yaw, "and the mouse turns the camera");
});

check("focus coming back locks the menu again: a stick already held on return moves nothing (I5)", () => {
  for (const how of ["hub", "window"]) {
    const g = loadMain();
    g.play({ options: 1 });
    g.setPads([pad()]);
    g.rest();
    assert.equal(g.T.menuIdx, 0);
    if (how === "hub") g.win.fire("message", { source: g.hub, data: { forge: "focus", focused: false } });
    else g.win.fire("blur");
    for (let i = 0; i < 60; i++) g.frame(); // 1 s away, the pad frozen at rest
    if (how === "hub") g.win.fire("message", { source: g.hub, data: { forge: "focus", focused: true } });
    else g.win.fire("focus");
    g.setPads([pad({ left: [0, 1] })]);
    for (let i = 0; i < 40; i++) g.frame();
    assert.equal(g.T.menuIdx, 0, `${how}: the stick held on return did not walk the menu`);
    g.setPads([pad()]);
    g.rest();
    g.setPads([pad({ left: [0, 1] })]);
    assert.equal(g.frame().menuIdx, 1, `${how}: let go and pushed, it moves`);
  }
});

if (failed.length) {
  for (const f of failed) console.error(`FAIL ${f}`);
  console.error(`${passed} passed, ${failed.length} failed`);
  process.exit(1);
}
console.log(`ok ${passed}`);
