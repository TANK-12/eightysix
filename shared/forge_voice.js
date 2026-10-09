/* Voice for every Forge page: dictation into a text box, replies spoken
   aloud, both through the Forge voice service (apps/voice, port 8467).
   Every call carries X-Forge: 1 (the service refuses calls without it).

   ForgeVoice.status()                     -> the service's /api/status, or null when it is down
   ForgeVoice.transcribe(blob, app)        -> text (POST /api/stt?app=)
   ForgeVoice.speak(text, {app, model, voice}) -> plays the wav from POST /api/tts in the page, resolves when
                                              done; model and voice are optional (a cloned voice is a profile
                                              name, mood tags such as [angry] go in the text); a newer speak()
                                              or stop() drops a line still being made
   ForgeVoice.stop()                       -> hushes what speak() is playing
   ForgeVoice.micButton(textarea, {app})   -> a button: press to record, press again to stop; the words go in at the cursor
   ForgeVoice.mic()                        -> ForgeMic (shared/forge_mic.js), loaded from beside this file on first use
   ForgeVoice.speakRepliesToggle(app)      -> a toggle button kept in localStorage forge.voice.speak.<app>
   ForgeVoice.speakReplies(app)            -> whether that toggle is on

   The pure parts (micNext, insertText, speakKey) take no browser and are
   tested with node --test (forge_voice.test.js). Loaded by pages as a plain
   script (window.ForgeVoice) and by node as a CommonJS module. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ForgeVoice = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const BASE = "http://127.0.0.1:8467";
  const HEADERS = { "X-Forge": "1" };
  // where this file came from, so forge_mic.js loads from beside it
  const HERE = typeof document !== "undefined" && document.currentScript ? document.currentScript.src : "";

  // --- pure helpers ---------------------------------------------------------

  /* The mic button's state after an event. States: idle, listening, working.
     A press while working is ignored; done and error always land on idle. */
  function micNext(state, event) {
    if (event === "done" || event === "error") return "idle";
    if (event === "press") {
      if (state === "idle") return "listening";
      if (state === "listening") return "working";
    }
    return state;
  }

  /* Put dictated words into `value` over the selection start..end, with a
     space either side where the neighbours are not already space. Returns
     {value, cursor}, the cursor just after the inserted words. */
  function insertText(value, start, end, words) {
    value = String(value || "");
    words = String(words || "").trim();
    const a = Math.max(0, Math.min(start == null ? value.length : start, value.length));
    const b = Math.max(a, Math.min(end == null ? a : end, value.length));
    if (!words) return { value, cursor: b };
    const before = value.slice(0, a);
    const after = value.slice(b);
    const lead = before && !/\s$/.test(before) ? " " : "";
    const tail = after && !/^[\s.,;:!?)]/.test(after) ? " " : "";
    const middle = lead + words + tail;
    return { value: before + middle + after, cursor: before.length + lead.length + words.length };
  }

  function speakKey(app) {
    return `forge.voice.speak.${app || "anywhere"}`;
  }

  // --- the service ------------------------------------------------------------

  async function call(path, init) {
    const res = await fetch(BASE + path, { ...(init || {}), headers: { ...HEADERS, ...((init || {}).headers || {}) } });
    if (!res.ok) {
      let why = "";
      try { why = (await res.json()).detail || ""; } catch (e) { why = ""; }
      throw new Error(why || `The voice service answered ${res.status}`);
    }
    return res;
  }

  async function status() {
    try { return await (await call("/api/status")).json(); } catch (e) { return null; }
  }

  async function transcribe(blob, app) {
    const res = await call(`/api/stt?app=${encodeURIComponent(app || "")}`, {
      method: "POST",
      headers: { "Content-Type": blob.type || "application/octet-stream" },
      body: blob,
    });
    return String((await res.json()).text || "").trim();
  }

  let playing = null; // {audio, url, done}
  let turn = 0; // bumped by every speak() and stop(): a slow line that lost its turn is not played

  function stop() {
    turn += 1;
    if (!playing) return;
    const p = playing;
    playing = null;
    try { p.audio.pause(); } catch (e) { /* already gone */ }
    URL.revokeObjectURL(p.url);
    p.done();
  }

  async function speak(text, opts) {
    const o = opts || {};
    if (!String(text || "").trim()) return;
    stop();
    const mine = turn;
    const body = { text, app: o.app || "" };
    if (o.model) body.model = o.model;
    if (o.voice) body.voice = o.voice;
    const res = await call("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const wav = await res.blob();
    if (mine !== turn) return; // stopped, or a newer line asked, while this one was made
    const url = URL.createObjectURL(wav);
    const audio = new Audio(url);
    await new Promise((resolve) => {
      const mine = { audio, url, done: resolve };
      playing = mine;
      const end = () => { if (playing === mine) stop(); else resolve(); };
      audio.onended = end;
      audio.onerror = end;
      audio.play().catch(end);
    });
  }

  // --- widgets ----------------------------------------------------------------

  /* The recorder. Pages record through ForgeMic (a WAV through Web Audio):
     MediaRecorder hands over 0 bytes for a real mic in Forge's WebKit.
     Loaded on first use, so a page needs only this one script tag. */
  let micLoading = null;
  function mic() {
    if (typeof window !== "undefined" && window.ForgeMic) return Promise.resolve(window.ForgeMic);
    if (!micLoading)
      micLoading = new Promise((resolve, reject) => {
        const tag = document.createElement("script");
        tag.src = new URL("forge_mic.js", HERE || location.href).href;
        tag.onload = () => (window.ForgeMic ? resolve(window.ForgeMic) : reject(new Error("the recorder did not load")));
        tag.onerror = () => {
          micLoading = null;
          reject(new Error("the recorder did not load"));
        };
        document.head.appendChild(tag);
      });
    return micLoading;
  }

  const LOOK = {
    idle: { text: "🎤", title: "Dictate: press to talk, press again to stop" },
    listening: { text: "⏺", title: "Listening… press to stop" },
    working: { text: "…", title: "Turning speech into text…" },
  };

  function micButton(textarea, opts) {
    const app = (opts || {}).app || "";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tool forge-voice-mic";
    let state = "idle";
    let recorder = null;
    let starting = false;
    const show = (note) => {
      button.textContent = LOOK[state].text;
      button.title = note || LOOK[state].title;
      button.dataset.state = state;
      button.setAttribute("aria-pressed", state === "listening" ? "true" : "false");
    };
    const fail = (e) => { state = micNext(state, "error"); show(`Voice: ${e.message || e}`); };

    async function finish(rec) {
      try {
        const blob = await rec.stop();
        if (rec.silent()) throw new Error("the microphone gave only silence (muted?)");
        const words = await transcribe(blob, app);
        const put = insertText(textarea.value, textarea.selectionStart, textarea.selectionEnd, words);
        textarea.value = put.value;
        textarea.focus();
        textarea.setSelectionRange(put.cursor, put.cursor);
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
        state = micNext(state, "done");
        show(words ? "" : "Heard nothing");
      } catch (e) { fail(e); }
    }

    button.addEventListener("click", async () => {
      if (starting) return; // still opening the mic
      const next = micNext(state, "press");
      if (next === state) return;
      if (next === "listening") {
        stop(); // the mic stays closed while something is speaking
        starting = true;
        try {
          recorder = await (await mic()).start({ onLimit: () => button.click() });
          state = next;
          show();
        } catch (e) { fail(e); }
        finally { starting = false; }
      } else {
        state = next;
        show();
        const rec = recorder;
        recorder = null;
        if (rec) finish(rec);
      }
    });
    show();
    return button;
  }

  function speakReplies(app) {
    try { return localStorage.getItem(speakKey(app)) === "1"; } catch (e) { return false; }
  }

  function speakRepliesToggle(app, opts) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tool forge-voice-speak";
    const show = () => {
      const on = speakReplies(app);
      button.textContent = on ? "🔊" : "🔈";
      button.title = on ? "Replies are spoken aloud (press to stop)" : "Speak replies aloud";
      button.setAttribute("aria-pressed", on ? "true" : "false");
      button.classList.toggle("on", on);
    };
    button.addEventListener("click", () => {
      const on = !speakReplies(app);
      try { localStorage.setItem(speakKey(app), on ? "1" : "0"); } catch (e) { /* private mode */ }
      if (!on) stop();
      show();
      if (opts && opts.onChange) opts.onChange(on);
    });
    show();
    return button;
  }

  return { BASE, micNext, insertText, speakKey, status, transcribe, speak, stop, mic, micButton, speakReplies, speakRepliesToggle };
});
