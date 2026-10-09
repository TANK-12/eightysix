const test = require("node:test");
const assert = require("node:assert");
const M = require("./forge_mic.js");

const wavSamples = (buf) => {
  const v = new DataView(buf);
  const out = [];
  for (let at = 44; at < buf.byteLength; at += 2) out.push(v.getInt16(at, true));
  return out;
};
const text = (buf, at, n) => String.fromCharCode(...new Uint8Array(buf, at, n));

test("encodeWav writes a mono 16-bit PCM header with the right sizes and rate", () => {
  const buf = M.encodeWav(new Float32Array(10), 16000);
  const v = new DataView(buf);
  assert.strictEqual(buf.byteLength, 44 + 20);
  assert.strictEqual(text(buf, 0, 4), "RIFF");
  assert.strictEqual(v.getUint32(4, true), 36 + 20);
  assert.strictEqual(text(buf, 8, 8), "WAVEfmt ");
  assert.deepStrictEqual(
    [v.getUint32(16, true), v.getUint16(20, true), v.getUint16(22, true), v.getUint32(24, true), v.getUint32(28, true), v.getUint16(32, true), v.getUint16(34, true)],
    [16, 1, 1, 16000, 32000, 2, 16]
  );
  assert.strictEqual(text(buf, 36, 4), "data");
  assert.strictEqual(v.getUint32(40, true), 20);
});

test("encodeWav maps -1..1 onto the full 16-bit range and clamps anything louder", () => {
  const buf = M.encodeWav(Float32Array.from([0, 1, -1, 0.5, -0.5, 2, -3]), 8000);
  assert.deepStrictEqual(wavSamples(buf), [0, 32767, -32768, 16384, -16384, 32767, -32768]);
});

test("an empty recording is still a valid wav with no samples", () => {
  const buf = M.encodeWav(new Float32Array(0), 16000);
  assert.strictEqual(buf.byteLength, 44);
  assert.strictEqual(new DataView(buf).getUint32(40, true), 0);
});

test("downsample 48 kHz to 16 kHz averages each run of three, across chunk edges", () => {
  const { samples, rate } = M.downsample([Float32Array.from([1, 2]), Float32Array.from([3, 4, 5, 6, 7])], 48000, 16000);
  assert.strictEqual(rate, 16000);
  assert.deepStrictEqual(Array.from(samples), [2, 5]); // the 7 is a partial run and is dropped
});

test("downsample 44.1 kHz to 16 kHz gives the right length and keeps a 1 kHz tone", () => {
  const from = 44100, n = from; // one second
  const tone = new Float32Array(n);
  for (let i = 0; i < n; i++) tone[i] = 0.8 * Math.sin((2 * Math.PI * 1000 * i) / from);
  const { samples, rate } = M.downsample([tone.subarray(0, 1000), tone.subarray(1000)], from, M.RATE);
  assert.strictEqual(rate, 16000);
  assert.strictEqual(samples.length, Math.floor(n / (from / 16000)));
  const peak = samples.reduce((a, x) => Math.max(a, Math.abs(x)), 0);
  assert.ok(peak > 0.75 && peak <= 0.8, `peak ${peak}`); // the box filter barely touches 1 kHz
});

test("a rate at or below 16 kHz is only joined, never stretched", () => {
  for (const from of [16000, 8000]) {
    const { samples, rate } = M.downsample([Float32Array.from([0.1, 0.2]), Float32Array.from([0.3])], from, 16000);
    assert.strictEqual(rate, from);
    assert.deepStrictEqual(Array.from(samples, (x) => Math.round(x * 10)), [1, 2, 3]);
  }
});

test("no chunks gives no samples", () => {
  assert.strictEqual(M.downsample([], 48000, 16000).samples.length, 0);
});

test("level is the loudest sample, capped at 1", () => {
  assert.strictEqual(M.level(Float32Array.from([0.1, -0.6, 0.3])), Float32Array.from([0.6])[0]);
  assert.strictEqual(M.level(Float32Array.from([0, -2])), 1);
  assert.strictEqual(M.level(new Float32Array(0)), 0);
});

test("outside a browser it says it cannot record, and start refuses plainly", async () => {
  assert.strictEqual(M.supported(), false);
  await assert.rejects(M.start(), /cannot record/);
});

// --- start() with a fake page: every failure lets go of the microphone -------

function fakePage({ throwProc = false, resumeHangs = false, closeHangs = false } = {}) {
  const tracks = [{ stopped: false, stop() { this.stopped = true; } }];
  const page = { tracks, ctx: null };
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => tracks }) } },
  });
  class Ctx {
    constructor() { this.sampleRate = 48000; this.state = resumeHangs ? "suspended" : "running"; this.closed = false; page.ctx = this; }
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
    createScriptProcessor() { if (throwProc) throw new Error("no ScriptProcessor"); return { connect() {}, disconnect() {} }; }
    resume() { return new Promise(() => {}); }
    close() { this.closed = true; return closeHangs ? new Promise(() => {}) : Promise.resolve(); }
    get destination() { return {}; }
  }
  global.window = { AudioContext: Ctx };
  return page;
}

test("a recorder that cannot be set up lets go of the microphone and says why", async () => {
  const page = fakePage({ throwProc: true });
  await assert.rejects(M.start(), /no ScriptProcessor/);
  assert.equal(page.tracks[0].stopped, true);
  assert.equal(page.ctx.closed, true);
});

test("a sound system that never starts gives up after startSeconds and closes the mic", async () => {
  const page = fakePage({ resumeHangs: true });
  await assert.rejects(M.start({ startSeconds: 0.05 }), /did not start/);
  assert.equal(page.tracks[0].stopped, true);
  assert.equal(page.ctx.closed, true);
});

test("a recorder that starts records and stops once", async () => {
  const page = fakePage();
  const rec = await M.start();
  assert.equal(page.tracks[0].stopped, false);
  rec.cancel();
  rec.cancel();
  assert.equal(page.tracks[0].stopped, true);
  delete global.window;
});


test("a sound system that never starts nor closes still lets the button work again", async () => {
  const page = fakePage({ resumeHangs: true, closeHangs: true });
  await assert.rejects(M.start({ startSeconds: 0.05, closeSeconds: 0.05 }), /did not start/);
  assert.equal(page.tracks[0].stopped, true);
});
