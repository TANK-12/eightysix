/* Headless smoke test: pull each game/experiment module out of the file, give it
   canvas/audio/FX stubs, and run begin()+many frames with synthetic input so a
   reference error or bad-shape bug throws here instead of in the browser. */
"use strict";
const fs = require("fs");
const FILE = "/home/ejb/Forge/apps/arcade/static/index.html";
const html = fs.readFileSync(FILE, "utf8");

// shared globals the modules close over
const VW = 1280, VH = 800, TAU = Math.PI * 2;
const REDUCED = false;
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const lerp = (a, b, t) => a + (b - a) * t;
const smoothstep = (e0, e1, x) => { const t = clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); };
const fmtTime = (s) => { s = Math.max(0, s | 0); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
const fmtNum = (n) => Math.floor(n).toLocaleString();
const pick = (a) => a[Math.floor(Math.random() * a.length)];
const esc = (s) => String(s);
let uiPhase = "play";
let audioEl = { play: () => Promise.resolve(), pause() {}, currentTime: 0, volume: 1 };
global._dbBeats = null;
global._dbFor = null;
global.bedActive = false;

function fakeCtx() {
  return new Proxy({}, {
    get: (o, k) => {
      if (k === "canvas") return { width: 300, height: 150 };
      if (k === "createLinearGradient" || k === "createRadialGradient")
        return () => ({ addColorStop() {} });
      if (k === "createImageData" || k === "getImageData")
        return (w, h) => ({ data: new Uint8ClampedArray(4 * (w | 0 || 1) * (h | 0 || 1)), width: w, height: h });
      if (k === "measureText") return () => ({ width: 10 });
      if (k === "getContext") return () => fakeCtx();
      return () => {};
    },
    set: () => true,
  });
}
const ctx = fakeCtx();
function elStub() {
  const e = {
    style: {}, dataset: {}, innerHTML: "", textContent: "", hidden: false, className: "",
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    appendChild() {}, removeChild() {}, remove() {}, setAttribute() {}, addEventListener() {},
    querySelector: () => elStub(), querySelectorAll: () => [], getContext: () => fakeCtx(),
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 100 }),
    focus() {}, click() {}, width: 300, height: 150,
  };
  return e;
}
global.$ = () => elStub();
global.document = {
  createElement: () => elStub(),
  querySelector: () => elStub(),
  addEventListener() {},
};
const glow = () => {};
const GLOW = { white: {}, amber: {}, cyan: {} };
const FX = {
  shake: 0, sparks: [], rings: [], texts: [],
  spark() {}, burst() {}, ring() {}, text() {}, kick() {}, clear() {}, update() {}, render() {},
};
const S = {
  W: 1280, H: 800, DPR: 1, scale: 1, ox: 0, oy: 0, backend: false, jan: false,
  px: (v) => v, py: (v) => v, pd: (v) => v, vx: (p) => p, vy: (p) => p,
  phase: () => uiPhase,
  gameOver: (r) => { S._over = r; },
  exitToMenu: () => {},
  makePanel: (mods, footer) => {
    const v = {};
    for (const m of mods) for (const k of m.keys) v[k.k] = k.value;
    return { el: {}, v, reads: {}, set() {}, destroy() {} };
  },
};
const audioParam = () => ({ value: 0, setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {}, setTargetAtTime() {} });
const audioNode = () => ({ connect: () => audioNode(), disconnect() {}, start() {}, stop() {}, frequency: audioParam(), detune: audioParam(), gain: audioParam(), Q: audioParam(), delayTime: audioParam(), type: "sine", buffer: null });
const AUDIO = {
  ac: {
    state: "running", sampleRate: 44100, currentTime: 0, destination: audioNode(),
    resume: () => Promise.resolve(), suspend: () => Promise.resolve(),
    createGain: audioNode, createOscillator: audioNode, createBiquadFilter: audioNode,
    createBufferSource: audioNode, createAnalyser: audioNode, createDelay: audioNode,
    createBuffer: (ch, len) => ({ getChannelData: () => new Float32Array(len) }),
  },
  analyser: { fftSize: 1024, frequencyBinCount: 512, getByteFrequencyData(a) { for (let i = 0; i < a.length; i++) a[i] = (Math.random() * 120) | 0; }, getByteTimeDomainData(a) { for (let i = 0; i < a.length; i++) a[i] = 128 + ((Math.random() * 40) | 0) - 20; } },
  freq: new Uint8Array(512).map(() => (Math.random() * 120) | 0),
  active: true, kind: "demo", name: "smoke tone", lastFile: null, pos: 0,
  bands: new Float32Array(8).fill(0.4), sub: 0.2, beat: false, pulse: 0.3,
  ensure() {}, file() {}, demoTone() {}, none() {}, duck() {}, suspend() {}, resume() {}, restart() { this.pos = 0; }, tick() {},
};
AUDIO.ac.decodeAudioData = () => Promise.resolve({ sampleRate: 44100, duration: 120, getChannelData: () => new Float32Array(44100 * 4) });

function grab(name) {
  const start = html.indexOf("function " + name + "(S,FX,AUDIO,GLOW)");
  if (start < 0) throw new Error("not found: " + name);
  // find matching close brace
  let depth = 0, i = html.indexOf("{", start);
  for (let j = i; j < html.length; j++) {
    const c = html[j];
    if (c === "{") depth++;
    else if (c === "}") { depth--; if (depth === 0) return html.slice(start, j + 1); }
  }
  throw new Error("unbalanced: " + name);
}

// Read the module list off the GAMES registry rather than repeating it here:
// every entry declares `create:(...a)=>Name(...a)`, so adding a game to the
// registry is all it takes to have it smoke-tested. This used to be a hand-kept
// array, which is exactly the kind of second list the registry exists to avoid.
const MODULES = [...new Set(
  [...html.matchAll(/create:\(\.\.\.a\)=>(\w+)\(\.\.\.a\)/g)].map((m) => m[1])
)];
if (MODULES.length < 8) {
  console.log("FAIL  could not read the GAMES registry (found " + MODULES.length + ")");
  process.exit(1);
}
let failures = 0;

// --- generated music beds ---
try {
  const slice = html.slice(html.indexOf("const BED_VOL="), html.indexOf("/* menu ambient */"));
  const factory = new Function("AUDIO", "pick", "let bedActive=false;\n" + slice + "\nreturn { MUSICBED, BEDS };");
  const { MUSICBED, BEDS } = factory(AUDIO, pick);
  for (const style of Object.keys(BEDS)) {
    MUSICBED.start(style);
    MUSICBED.start(style); // idempotent
    MUSICBED.stop();
  }
  MUSICBED.start("orbit");
  MUSICBED.start("station"); // switch styles
  MUSICBED.stop();
  console.log("ok    MUSICBED (" + Object.keys(BEDS).join(", ") + ")");
} catch (e) {
  failures++;
  console.log("FAIL  MUSICBED  ->  " + e.message);
}
for (const name of MODULES) {
  try {
    const fn = eval("(" + grab(name) + ")");
    const inst = fn(S, FX, AUDIO, GLOW);
    if (inst.onEnter) inst.onEnter();
    inst.begin && inst.begin();
    S._over = null;
    for (let f = 0; f < 3000; f++) {
      AUDIO.beat = Math.random() < 0.12;
      AUDIO.pulse = Math.random();
      AUDIO.sub = Math.random() * 0.4;
      AUDIO.pos += 1 / 60;
      for (let b = 0; b < 8; b++) AUDIO.bands[b] = Math.random();
      if (inst.pointer && Math.random() < 0.08) inst.pointer(pick(["down", "move", "up"]), Math.random() * VW, Math.random() * VH);
      if (inst.key && Math.random() < 0.08) inst.key(pick([" ", "arrowup", "w", "a", "d", "m"]), Math.random() < 0.5);
      inst.frame(1 / 60, f / 60);
      if (S._over) { inst.begin && inst.begin(); S._over = null; }
    }
    if (inst.setPaused) inst.setPaused(true), inst.setPaused(false);
    if (inst.onExit) inst.onExit();
    console.log("ok    " + name);
  } catch (e) {
    failures++;
    console.log("FAIL  " + name + "  ->  " + e.message + "\n" + (e.stack || "").split("\n").slice(1, 4).join("\n"));
  }
}
process.exit(failures ? 1 : 0);
