const test = require("node:test");
const assert = require("node:assert");
const V = require("./forge_voice.js");

test("the mic button goes idle, listening, working, idle and ignores presses while working", () => {
  const steps = [];
  let s = "idle";
  for (const e of ["press", "press", "press", "done", "press", "error", "noise"]) steps.push((s = V.micNext(s, e)));
  assert.deepStrictEqual(steps, ["listening", "working", "working", "idle", "listening", "idle", "idle"]);
});

test("every state and event pair lands on a known state", () => {
  for (const s of ["idle", "listening", "working"])
    for (const e of ["press", "done", "error", "other"])
      assert.ok(["idle", "listening", "working"].includes(V.micNext(s, e)), `${s} ${e}`);
});

test("dictated words go in at the cursor with sensible spaces", () => {
  const cases = [
    ["", 0, 0, "hello", "hello", 5],
    ["ask ", 4, 4, "it", "ask it", 6],
    ["ask", 3, 3, " it ", "ask it", 6],
    ["ab", 1, 1, "x", "a x b", 3],
    ["hello world", 6, 11, "there", "hello there", 11],
    ["end.", 3, 3, "ing", "end ing.", 7],
    ["keep", 2, 2, "   ", "keep", 2],
    ["text", null, null, "more", "text more", 9],
    ["abc", 99, 99, "z", "abc z", 5],
  ];
  for (const [value, a, b, words, out, cursor] of cases) {
    const got = V.insertText(value, a, b, words);
    assert.deepStrictEqual(got, { value: out, cursor }, JSON.stringify([value, a, b, words]));
  }
});

test("the speak toggle key is per app", () => {
  assert.equal(V.speakKey("claude"), "forge.voice.speak.claude");
  assert.equal(V.speakKey(""), "forge.voice.speak.anywhere");
  assert.equal(V.BASE, "http://127.0.0.1:8467");
});

// --- the widgets and the service calls, with a fake browser -------------------

function fakeBrowser() {
  const calls = [];
  const store = {};
  class El {
    constructor() { this.listeners = {}; this.dataset = {}; this.attrs = {}; this.classes = new Set(); this.classList = { toggle: (c, on) => (on ? this.classes.add(c) : this.classes.delete(c)) }; }
    addEventListener(k, f) { this.listeners[k] = f; }
    setAttribute(k, v) { this.attrs[k] = v; }
    async click() { await this.listeners.click(); }
  }
  const audios = [];
  global.document = { createElement: () => new El() };
  global.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } };
  global.URL.createObjectURL = () => "blob:x";
  global.URL.revokeObjectURL = () => {};
  global.Audio = class { constructor(url) { this.url = url; audios.push(this); } play() { setTimeout(() => this.onended && this.onended(), 5); return Promise.resolve(); } pause() { this.paused = true; } };
  global.fetch = async (url, init) => {
    calls.push({ url, init });
    if (url.includes("/api/stt")) return { ok: true, json: async () => ({ text: " world " }) };
    if (url.includes("/api/tts")) return { ok: true, blob: async () => "wav" };
    return { ok: false, status: 503, json: async () => ({ detail: "down" }) };
  };
  const tracks = [];
  // node has a read-only navigator of its own
  Object.defineProperty(global, "navigator", { configurable: true, value: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop: () => tracks.push("stopped") }] }) } } });
  global.Blob = class { constructor(parts, o) { this.parts = parts; this.type = o.type; } };
  global.Event = class { constructor(t) { this.type = t; } };
  // the recorder (shared/forge_mic.js), already on the page
  const mic = { silent: false, opts: null };
  global.window = {
    ForgeMic: {
      start: async (o) => {
        mic.opts = o;
        return { stop: async () => { tracks.push("stopped"); return new Blob(["RIFF"], { type: "audio/wav" }); }, silent: () => mic.silent };
      },
    },
  };
  return { calls, store, audios, tracks, mic };
}

const textBox = () => ({ value: "hello", selectionStart: 5, selectionEnd: 5, focus() {}, setSelectionRange(a) { this.cursor = a; }, dispatchEvent(e) { this.fired = e.type; } });

test("the mic button records, then dictates at the cursor through /api/stt with X-Forge", async () => {
  const b = fakeBrowser();
  const area = textBox();
  const mic = V.micButton(area, { app: "claude" });
  assert.equal(mic.dataset.state, "idle");
  await mic.click();
  assert.equal(mic.dataset.state, "listening", mic.title);
  await mic.click();
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(area.value, "hello world");
  assert.equal(area.cursor, 11);
  assert.equal(area.fired, "input");
  assert.equal(mic.dataset.state, "idle");
  assert.deepStrictEqual(b.tracks, ["stopped"]);
  const stt = b.calls.find((c) => c.url.includes("/api/stt"));
  assert.equal(stt.url, "http://127.0.0.1:8467/api/stt?app=claude");
  assert.equal(stt.init.headers["X-Forge"], "1");
  assert.equal(stt.init.headers["Content-Type"], "audio/wav");
});

test("the mic button says so when the microphone gives only silence, and sends nothing", async () => {
  const b = fakeBrowser();
  b.mic.silent = true;
  const area = textBox();
  const mic = V.micButton(area, { app: "claude" });
  await mic.click();
  await mic.click();
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(mic.dataset.state, "idle");
  assert.match(mic.title, /silence/);
  assert.equal(b.calls.filter((c) => c.url.includes("/api/stt")).length, 0);
  assert.equal(area.value, "hello");
});

test("reaching the recording limit ends it like a second press", async () => {
  const b = fakeBrowser();
  const area = textBox();
  const mic = V.micButton(area, {});
  await mic.click();
  assert.equal(mic.dataset.state, "listening");
  b.mic.opts.onLimit();
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(area.value, "hello world");
  assert.equal(mic.dataset.state, "idle");
});

test("mic() hands back the recorder already on the page", async () => {
  const b = fakeBrowser();
  assert.equal(await V.mic(), global.window.ForgeMic);
  assert.ok(b);
});

test("speak plays the wav and resolves when it ends; status is null when the service is down", async () => {
  const b = fakeBrowser();
  await V.speak("Hi there", { app: "claude" });
  const tts = b.calls.find((c) => c.url.endsWith("/api/tts"));
  assert.deepStrictEqual(JSON.parse(tts.init.body), { text: "Hi there", app: "claude" });
  assert.equal(tts.init.headers["X-Forge"], "1");
  assert.equal(b.audios.length, 1);
  assert.equal(await V.status(), null);
});

test("speak passes a model and voice on, and a newer line or stop drops one still being made", async () => {
  const b = fakeBrowser();
  const slow = [];
  global.fetch = async (url, init) => {
    b.calls.push({ url, init });
    const text = JSON.parse(init.body).text;
    if (text.startsWith("slow")) await new Promise((r) => slow.push(r));
    return { ok: true, blob: async () => text };
  };
  await V.speak("[angry] Back off", { app: "claude", model: "breeze-tts-2", voice: "86-lena-en" });
  const body = JSON.parse(b.calls[0].init.body);
  assert.deepStrictEqual(body, { text: "[angry] Back off", app: "claude", model: "breeze-tts-2", voice: "86-lena-en" });
  const first = V.speak("slow one", { app: "mission" });
  await new Promise((r) => setImmediate(r));
  await V.speak("quick two", { app: "mission" }); // asked while the first was still being made
  slow.forEach((r) => r());
  await first;
  assert.equal(b.audios.length, 2); // "Back off" and "quick two"; the slow one never plays
  const third = V.speak("slow three", {});
  await new Promise((r) => setImmediate(r));
  V.stop(); // hushed while it was made
  slow.forEach((r) => r());
  await third;
  assert.equal(b.audios.length, 2);
});

test("the speak-replies toggle is stored per app in localStorage", async () => {
  const b = fakeBrowser();
  const t = V.speakRepliesToggle("claude");
  assert.equal(V.speakReplies("claude"), false);
  await t.click();
  assert.equal(b.store["forge.voice.speak.claude"], "1");
  assert.equal(V.speakReplies("claude"), true);
  assert.equal(V.speakReplies("mission"), false);
  assert.equal(t.attrs["aria-pressed"], "true");
  await t.click();
  assert.equal(V.speakReplies("claude"), false);
});
