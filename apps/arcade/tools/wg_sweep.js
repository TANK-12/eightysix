/* Waveguide solvability sweep — extracts the generator from static/index.html
   and hammers it. Asserts: at the intended solution every receiver lights, and
   the board is never shipped already solved. */
"use strict";
const fs = require("fs");
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const REDUCED = false;

// Pull the Waveguide function source straight out of the file and eval it in a
// sandbox that provides the globals it closes over.
const html = fs.readFileSync("/home/ejb/Forge/apps/arcade/static/index.html", "utf8");
const start = html.indexOf("function Waveguide(");
const endMarker = "\n/* ==================== GAME 7 · DOWNBEAT";
const end = html.indexOf(endMarker);
let fnSrc = html.slice(start, end).trim();
// strip trailing so it's exactly the function
fnSrc = fnSrc.replace(/\}\s*$/, "}");

// globals Waveguide closes over
const VW = 1280, VH = 800, TAU = Math.PI * 2;
const ctx = new Proxy({}, { get: () => () => {} });
const glow = () => {};
const fmtNum = (n) => String(Math.floor(n));
let uiPhase = "play";
const FX = { ring() {}, burst() {}, text() {}, render() {} };
const S = {
  px: (v) => v, py: (v) => v, pd: (v) => v,
};

const Waveguide = eval("(" + fnSrc + ")");

// We need access to the module internals. Re-create a thin driver by calling the
// returned object's begin()/frame() and reading the board through a hook: easier
// to just re-implement the check using trace via the same grid. Instead, expose
// internals by lightly patching: run begin(), then advance levels via frame().
// begin() builds L1; to test L=k we bump level by calling frame with solved.
// Simpler: instrument by monkeypatching Math.random off and calling build paths.

// The cleanest approach: eval a variant that returns internals for testing.
const testSrc = fnSrc.replace(
  "return {\n    begin(){",
  "return {\n    __t(){ return { trace, build, setSol, get grid(){return grid;}, get recvs(){return recvs;} }; },\n    begin(){"
);
const WaveguideT = eval("(" + testSrc + ")");

const inst = WaveguideT(S, FX, FX, {});
const T = inst.__t();

let boards = 0, unsolvable = 0, preSolved = 0, splitLevels = 0, wallLevels = 0, multiRecv = 0;
const perL = {};

for (let L = 1; L <= 20; L++) {
  perL[L] = { n: 0, unsolvable: 0, preSolved: 0, split: 0, recvHist: {} };
  for (let i = 0; i < 1500; i++) {
    T.build(L);
    boards++;
    perL[L].n++;
    const { grid, recvs } = T;

    // is it shipped already solved?
    const shipped = T.trace().lit.size;
    if (shipped >= recvs.length) { preSolved++; perL[L].preSolved++; }

    // does the intended solution light every receiver?
    T.setSol();
    const solLit = T.trace().lit.size;
    if (solLit !== recvs.length) { unsolvable++; perL[L].unsolvable++; }

    const hasSplit = grid.some((g) => g && g.kind === "split");
    const hasWall = grid.some((g) => g && g.kind === "block");
    if (hasSplit) { splitLevels++; perL[L].split++; }
    if (hasWall) wallLevels++;
    if (recvs.length > 1) multiRecv++;
    perL[L].recvHist[recvs.length] = (perL[L].recvHist[recvs.length] || 0) + 1;
  }
}

console.log(`boards:            ${boards}`);
console.log(`unsolvable:        ${unsolvable}`);
console.log(`shipped pre-solved:${preSolved}`);
console.log(`levels w/ splitter:${splitLevels}`);
console.log(`levels w/ wall:    ${wallLevels}`);
console.log(`multi-receiver:    ${multiRecv}`);
console.log("");
for (let L = 1; L <= 20; L++) {
  const p = perL[L];
  const rh = Object.entries(p.recvHist).map(([k, v]) => `${k}r:${v}`).join(" ");
  console.log(
    `L${String(L).padStart(2)}  n=${p.n}  unsolvable=${p.unsolvable}  preSolved=${p.preSolved}  split=${p.split}  [${rh}]`
  );
}
process.exit(unsolvable === 0 && preSolved === 0 ? 0 : 1);
